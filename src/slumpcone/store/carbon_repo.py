"""Reading and writing emission factors and benchmark tables.

A factor is filed under its material and there is only ever one current, because
a footprint that could have been computed two ways is not a footprint. Replacing
one is an ordinary write rather than a conflict: a supplier publishing a new EPD
is the normal case, not an exception.

A benchmark table is the opposite. Tables are published documents and a plant
usually holds several, one per programme it reports to, so they are filed by
name and a name collision is refused.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from slumpcone.carbon.benchmark import BenchmarkClass, BenchmarkTable
from slumpcone.carbon.factors import EmissionFactor, FactorBook, Provenance, Stage
from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.materials.kinds import MaterialClass
from slumpcone.store.db import Database
from slumpcone.store.guards import refuse_existing, require_one
from slumpcone.store.rows import day, text
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


class CarbonRepository:
    """Emission factors, admixture densities and benchmark tables, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save_factor(self, factor: EmissionFactor) -> EmissionFactor:
        """File a factor, replacing any earlier one for the same material."""
        self._db.execute(
            "INSERT INTO emission_factor (material_code, material_class, "
            "kg_co2e_per_kg, stage, provenance, source, published_on) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(material_code) DO UPDATE SET "
            "material_class = excluded.material_class, "
            "kg_co2e_per_kg = excluded.kg_co2e_per_kg, "
            "stage = excluded.stage, provenance = excluded.provenance, "
            "source = excluded.source, published_on = excluded.published_on",
            (
                factor.material_code,
                factor.material_class.value,
                factor.kg_co2e_per_kg,
                factor.stage.value,
                factor.provenance.value,
                factor.source,
                None if factor.published_on is None else factor.published_on.isoformat(),
            ),
        )
        return factor

    def factor(self, material_code: str) -> EmissionFactor:
        """One factor by material."""
        key = normalize_code(material_code, field="material_code")
        row = require_one(
            self._db,
            "SELECT * FROM emission_factor WHERE material_code = ?",
            (key,),
            "emission factor",
            key,
        )
        return EmissionFactor(
            str(row["material_code"]),
            MaterialClass(str(row["material_class"])),
            float(row["kg_co2e_per_kg"]),
            Stage(str(row["stage"])),
            Provenance(str(row["provenance"])),
            text(row["source"]) or "",
            day(row["published_on"]),
        )

    def book(self) -> FactorBook:
        """Every factor on file, as a book ready to compute against."""
        rows = self._db.query(
            "SELECT material_code FROM emission_factor ORDER BY material_code"
        )
        return FactorBook(self.factor(str(row["material_code"])) for row in rows)

    def load_defaults(self) -> int:
        """Seed the shipped industry averages, leaving anything already filed alone."""
        added = 0
        for factor in FactorBook.defaults().as_mapping().values():
            if self._db.query_one(
                "SELECT 1 FROM emission_factor WHERE material_code = ?",
                (factor.material_code,),
            ):
                continue
            self.save_factor(factor)
            added += 1
        return added

    def forget_factor(self, material_code: str) -> None:
        """Drop a factor."""
        key = normalize_code(material_code, field="material_code")
        cursor = self._db.execute("DELETE FROM emission_factor WHERE material_code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("emission factor", key)

    def save_density(self, material_code: str, density: MassPerVolume) -> MassPerVolume:
        """File the density an admixture is counted through."""
        key = normalize_code(material_code, field="material_code")
        self._db.execute(
            "INSERT INTO admixture_density (material_code, value, mass_unit, volume_unit) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(material_code) DO UPDATE SET "
            "value = excluded.value, mass_unit = excluded.mass_unit, "
            "volume_unit = excluded.volume_unit",
            (key, density.value, density.mass_unit, density.volume_unit),
        )
        return density

    def densities(self) -> dict[str, MassPerVolume]:
        """Every admixture density on file."""
        rows = self._db.query("SELECT * FROM admixture_density ORDER BY material_code")
        return {
            str(row["material_code"]): MassPerVolume(
                float(row["value"]), str(row["mass_unit"]), str(row["volume_unit"])
            )
            for row in rows
        }

    def save_table(
        self,
        name: str,
        classes: Iterable[BenchmarkClass],
        *,
        published: str = "",
        notes: str = "",
    ) -> BenchmarkTable:
        """File a benchmark table under a name. Refuses to overwrite one."""
        label = normalize_name(name, field="table_name")
        rows = tuple(classes)
        # Built before anything is written, so a table with no rows is refused
        # rather than leaving a header on file that can never be read back.
        table = BenchmarkTable(rows, label)
        refuse_existing(
            self._db,
            "SELECT 1 FROM benchmark_table WHERE name = ?",
            (label,),
            "benchmark table",
            label,
        )
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO benchmark_table (name, published, notes) VALUES (?, ?, ?)",
                (label, published, notes),
            )
            for row in rows:
                self._db.execute(
                    "INSERT INTO benchmark_class (table_name, floor_psi, "
                    "limit_kg_per_m3, label) VALUES (?, ?, ?, ?)",
                    (label, row.floor.to("psi").value, row.limit_kg_per_m3, row.label),
                )
        return table

    def table(self, name: str) -> BenchmarkTable:
        """One benchmark table by name."""
        label = normalize_name(name, field="table_name")
        require_one(
            self._db,
            "SELECT 1 FROM benchmark_table WHERE name = ?",
            (label,),
            "benchmark table",
            label,
        )
        rows = self._db.query(
            "SELECT * FROM benchmark_class WHERE table_name = ? ORDER BY floor_psi DESC",
            (label,),
        )
        return BenchmarkTable(
            [
                BenchmarkClass(
                    Quantity(float(row["floor_psi"]), "psi"),
                    float(row["limit_kg_per_m3"]),
                    str(row["label"]),
                )
                for row in rows
            ],
            label,
        )

    def table_names(self) -> tuple[str, ...]:
        """Every benchmark table on file, sorted."""
        rows = self._db.query("SELECT name FROM benchmark_table ORDER BY name")
        return tuple(str(row["name"]) for row in rows)

    def load_default_table(self, name: str = "national average") -> BenchmarkTable:
        """File the shipped table shape under a name."""
        return self.save_table(
            name,
            BenchmarkTable.defaults().classes,
            notes="shipped shape, replace with the programme's own",
        )

    def stale_factors(self, on: date, *, years: int = 5) -> tuple[EmissionFactor, ...]:
        """Every factor whose declaration has aged out."""
        return self.book().stale(on, years=years)
