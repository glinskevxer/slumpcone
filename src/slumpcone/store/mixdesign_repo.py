"""Reading and writing mix designs.

Every revision is its own row and nothing is ever overwritten in place. A
cylinder broken in six weeks has to be attributable to the proportions that
were actually batched, and a repository that lets a revision be edited destroys
that link without leaving a trace.
"""

from __future__ import annotations

import sqlite3

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.store.db import Database
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def _band_columns(band: Band | None, target: float | None = None) -> tuple[float | None, ...]:
    if band is None:
        return (target, None, None)
    return (band.target, band.minus, band.plus)


def _band_from(target: float | None, minus: float | None, plus: float | None) -> Band | None:
    if target is None or (minus is None and plus is None):
        return None
    return Band(target, minus, plus)


class MixDesignRepository:
    """Mix designs, on disk, one row per revision."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, design: MixDesign) -> MixDesign:
        """Write a revision. Refuses to overwrite one that is already on file."""
        existing = self._db.query_one(
            "SELECT 1 FROM mix_design WHERE code = ? AND revision = ?",
            (design.code, design.revision),
        )
        if existing is not None:
            raise ConflictError("mix design revision", design.identity)
        slump_target, slump_minus, slump_plus = _band_columns(
            design.slump_band, design.slump_target.to("in").value
        )
        air_target, air_minus, air_plus = _band_columns(design.air_band)
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO mix_design (code, revision, name, plant_code, "
                "specified_strength_psi, test_age_days, nominal_max_size_mm, "
                "slump_target_in, slump_band_target_in, slump_minus_in, slump_plus_in, "
                "air_target_pct, "
                "air_minus_pct, air_plus_pct, design_air_pct, mass_unit, volume_unit, "
                "exposure, notes) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    design.code,
                    design.revision,
                    design.name,
                    design.plant_code,
                    design.specified_strength.to("psi").value,
                    design.test_age_days,
                    design.nominal_max_size.to("mm").value,
                    design.slump_target.to("in").value,
                    slump_target,
                    slump_minus,
                    slump_plus,
                    air_target,
                    air_minus,
                    air_plus,
                    design.proportions.design_air.value,
                    design.proportions.mass_unit,
                    design.proportions.volume_unit,
                    str(design.exposure),
                    design.notes,
                ),
            )
            for position, charge in enumerate(design.proportions.charges):
                self._db.execute(
                    "INSERT INTO mix_design_charge (code, revision, position, material_code, "
                    "material_class, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        design.code,
                        design.revision,
                        position,
                        charge.material_code,
                        charge.material_class.value,
                        charge.content.value,
                    ),
                )
            for position, admixture in enumerate(design.proportions.admixtures):
                self._db.execute(
                    "INSERT INTO mix_design_admixture (code, revision, position, "
                    "material_code, dose_floz_cwt) VALUES (?, ?, ?, ?, ?)",
                    (
                        design.code,
                        design.revision,
                        position,
                        admixture.material_code,
                        admixture.dose_per_cwt.to("floz").value,
                    ),
                )
        return design

    def _proportions(self, row: sqlite3.Row) -> Proportions:
        code = str(row["code"])
        revision = int(row["revision"])
        mass_unit = str(row["mass_unit"])
        volume_unit = str(row["volume_unit"])
        charge_rows = self._db.query(
            "SELECT * FROM mix_design_charge WHERE code = ? AND revision = ? ORDER BY position",
            (code, revision),
        )
        charges = tuple(
            Charge(
                str(charge["material_code"]),
                MaterialClass(str(charge["material_class"])),
                MassPerVolume(float(charge["content"]), mass_unit, volume_unit),
            )
            for charge in charge_rows
        )
        admix_rows = self._db.query(
            "SELECT * FROM mix_design_admixture WHERE code = ? AND revision = ? "
            "ORDER BY position",
            (code, revision),
        )
        admixtures = tuple(
            AdmixtureCharge(
                str(admix["material_code"]), Quantity(float(admix["dose_floz_cwt"]), "floz")
            )
            for admix in admix_rows
        )
        return Proportions(charges, admixtures, Percent(float(row["design_air_pct"])))

    def _from_row(self, row: sqlite3.Row) -> MixDesign:
        return MixDesign(
            code=str(row["code"]),
            name=str(row["name"]),
            proportions=self._proportions(row),
            specified_strength=Quantity(float(row["specified_strength_psi"]), "psi"),
            nominal_max_size=Quantity(float(row["nominal_max_size_mm"]), "mm"),
            slump_target=Quantity(float(row["slump_target_in"]), "in"),
            test_age_days=int(row["test_age_days"]),
            slump_band=_band_from(
                (
                    None
                    if row["slump_band_target_in"] is None
                    else float(row["slump_band_target_in"])
                ),
                None if row["slump_minus_in"] is None else float(row["slump_minus_in"]),
                None if row["slump_plus_in"] is None else float(row["slump_plus_in"]),
            ),
            air_band=_band_from(
                None if row["air_target_pct"] is None else float(row["air_target_pct"]),
                None if row["air_minus_pct"] is None else float(row["air_minus_pct"]),
                None if row["air_plus_pct"] is None else float(row["air_plus_pct"]),
            ),
            exposure=ExposureSet.parse(str(row["exposure"])),
            revision=int(row["revision"]),
            plant_code=None if row["plant_code"] is None else str(row["plant_code"]),
            notes=str(row["notes"]),
        )

    def get(self, code: str, revision: int) -> MixDesign:
        """One revision by code and number."""
        key = normalize_code(code, field="mix_code")
        row = self._db.query_one(
            "SELECT * FROM mix_design WHERE code = ? AND revision = ?", (key, revision)
        )
        if row is None:
            raise NotFoundError("mix design revision", f"{key} r{revision}")
        return self._from_row(row)

    def latest(self, code: str) -> MixDesign:
        """The highest revision on file for a code."""
        key = normalize_code(code, field="mix_code")
        row = self._db.query_one(
            "SELECT * FROM mix_design WHERE code = ? ORDER BY revision DESC LIMIT 1", (key,)
        )
        if row is None:
            raise NotFoundError("mix design", key)
        return self._from_row(row)

    def revisions(self, code: str) -> tuple[MixDesign, ...]:
        """Every revision of one design, oldest first."""
        key = normalize_code(code, field="mix_code")
        rows = self._db.query(
            "SELECT * FROM mix_design WHERE code = ? ORDER BY revision", (key,)
        )
        return tuple(self._from_row(row) for row in rows)

    def codes(self) -> tuple[str, ...]:
        """Every design code on file, sorted."""
        rows = self._db.query("SELECT DISTINCT code FROM mix_design ORDER BY code")
        return tuple(str(row["code"]) for row in rows)

    def latest_all(self) -> tuple[MixDesign, ...]:
        """The newest revision of every design, in code order."""
        return tuple(self.latest(code) for code in self.codes())

    def for_plant(self, plant_code: str) -> tuple[MixDesign, ...]:
        """The newest revision of every design tied to one plant."""
        key = normalize_code(plant_code, field="plant_code")
        return tuple(d for d in self.latest_all() if d.plant_code == key)

    def delete(self, code: str, revision: int) -> None:
        """Remove one revision."""
        key = normalize_code(code, field="mix_code")
        cursor = self._db.execute(
            "DELETE FROM mix_design WHERE code = ? AND revision = ?", (key, revision)
        )
        if cursor.rowcount == 0:
            raise NotFoundError("mix design revision", f"{key} r{revision}")
