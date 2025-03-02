"""Reading and writing beams and cores.

Both are kept apart from the cylinder tables on purpose. A beam is not a
cylinder with a different shape: it is broken differently, judged differently
and bought against a different specified strength. A core is not a specimen at
all, it is a piece of the structure. Filing all three in one table would mean a
column that only applies to one of them in every second row.

Cores carry the specified strength they are being judged against, because that
is a property of the investigation rather than of the core, and one location can
be cored against a different number than the mixture was sold as.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.store.db import Database
from slumpcone.strength.cores import Core, CoreCondition, CoreInvestigation
from slumpcone.strength.flexural import FlexuralBreak
from slumpcone.units.quantity import Quantity


def _beam_from_row(row: sqlite3.Row) -> FlexuralBreak:
    return FlexuralBreak(
        specimen_code=str(row["specimen_code"]),
        span=Quantity(float(row["span_in"]), "in"),
        width=Quantity(float(row["width_in"]), "in"),
        depth=Quantity(float(row["depth_in"]), "in"),
        max_load=Quantity(float(row["max_load_lbf"]), "lbf"),
        fracture_from_support=Quantity(float(row["fracture_from_support_in"]), "in"),
        age_days=float(row["age_days"]),
    )


def _core_from_row(row: sqlite3.Row) -> Core:
    return Core(
        code=str(row["code"]),
        diameter=Quantity(float(row["diameter_in"]), "in"),
        length=Quantity(float(row["length_in"]), "in"),
        max_load=Quantity(float(row["max_load_lbf"]), "lbf"),
        condition=CoreCondition(str(row["condition"])),
        has_reinforcement=bool(row["has_reinforcement"]),
    )


class HardenedRepository:
    """Beams and cores, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save_beam(
        self,
        beam: FlexuralBreak,
        set_code: str,
        mix_code: str,
        tested_at: datetime,
        notes: str = "",
    ) -> FlexuralBreak:
        """File one beam. A beam breaks once."""
        if self._db.query_one(
            "SELECT 1 FROM flexural_break WHERE specimen_code = ?", (beam.specimen_code,)
        ):
            raise ConflictError("beam", beam.specimen_code)
        self._db.execute(
            "INSERT INTO flexural_break (specimen_code, set_code, mix_code, tested_at, "
            "age_days, span_in, width_in, depth_in, max_load_lbf, "
            "fracture_from_support_in, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                beam.specimen_code,
                normalize_code(set_code, field="set_code"),
                normalize_code(mix_code, field="mix_code"),
                tested_at.isoformat(),
                beam.age_days,
                beam.span.to("in").value,
                beam.width.to("in").value,
                beam.depth.to("in").value,
                beam.max_load.to("lbf").value,
                beam.fracture_from_support.to("in").value,
                notes,
            ),
        )
        return beam

    def beam(self, specimen_code: str) -> FlexuralBreak:
        """One beam by specimen code."""
        key = normalize_code(specimen_code, field="specimen_code")
        row = self._db.query_one("SELECT * FROM flexural_break WHERE specimen_code = ?", (key,))
        if row is None:
            raise NotFoundError("beam", key)
        return _beam_from_row(row)

    def beams_in(self, set_code: str) -> tuple[FlexuralBreak, ...]:
        """Every beam in one set, in specimen order."""
        key = normalize_code(set_code, field="set_code")
        rows = self._db.query(
            "SELECT * FROM flexural_break WHERE set_code = ? ORDER BY specimen_code",
            (key,),
        )
        return tuple(_beam_from_row(row) for row in rows)

    def beams_for_mix(self, mix_code: str) -> tuple[FlexuralBreak, ...]:
        """Every beam broken on one mixture, oldest first."""
        key = normalize_code(mix_code, field="mix_code")
        rows = self._db.query(
            "SELECT * FROM flexural_break WHERE mix_code = ? ORDER BY tested_at, specimen_code",
            (key,),
        )
        return tuple(_beam_from_row(row) for row in rows)

    def save_core(
        self,
        core: Core,
        location: str,
        specified: Quantity,
        taken_at: datetime,
        notes: str = "",
    ) -> Core:
        """File one core against a location and the strength it is judged on."""
        if self._db.query_one("SELECT 1 FROM concrete_core WHERE code = ?", (core.code,)):
            raise ConflictError("core", core.code)
        self._db.execute(
            "INSERT INTO concrete_core (code, location, specified_psi, taken_at, "
            "diameter_in, length_in, max_load_lbf, condition, has_reinforcement, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                core.code,
                location.strip(),
                specified.to("psi").value,
                taken_at.isoformat(),
                core.diameter.to("in").value,
                core.length.to("in").value,
                core.max_load.to("lbf").value,
                core.condition.value,
                int(core.has_reinforcement),
                notes,
            ),
        )
        return core

    def core(self, code: str) -> Core:
        """One core by code."""
        key = normalize_code(code, field="core_code")
        row = self._db.query_one("SELECT * FROM concrete_core WHERE code = ?", (key,))
        if row is None:
            raise NotFoundError("core", key)
        return _core_from_row(row)

    def locations(self) -> tuple[str, ...]:
        """Every location that has been cored, sorted."""
        rows = self._db.query("SELECT DISTINCT location FROM concrete_core ORDER BY location")
        return tuple(str(row["location"]) for row in rows)

    def investigation(self, location: str) -> CoreInvestigation:
        """The cores from one location, as an investigation."""
        rows = self._db.query(
            "SELECT * FROM concrete_core WHERE location = ? ORDER BY code",
            (location.strip(),),
        )
        if not rows:
            raise NotFoundError("cores at", location.strip())
        specified = Quantity(float(rows[0]["specified_psi"]), "psi")
        return CoreInvestigation(
            location.strip(), specified, tuple(_core_from_row(row) for row in rows)
        )

    def delete_core(self, code: str) -> None:
        """Remove a core."""
        key = normalize_code(code, field="core_code")
        cursor = self._db.execute("DELETE FROM concrete_core WHERE code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("core", key)
