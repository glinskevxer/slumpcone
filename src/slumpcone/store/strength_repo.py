"""Reading and writing specimens, sets and breaks.

A set is stored separately from the cylinders in it because the set is what
carries the mix, the ticket and the job, and those have to survive a cylinder
being written off. A break is stored against its cylinder, one to one, since a
cylinder can only be broken once.

Strength tests are not stored at all. They are the average of whatever breaks
exist for a set, and materialising them would mean keeping a derived number in
step with the breaks under it forever.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code, normalize_ticket_number
from slumpcone.store.db import Database
from slumpcone.store.guards import refuse_existing, require_one
from slumpcone.store.rows import text
from slumpcone.strength.breaks import BreakResult, FractureType
from slumpcone.strength.specimen import (
    CureCondition,
    Specimen,
    SpecimenPurpose,
    SpecimenSize,
)
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity


def _specimen_from_row(row: sqlite3.Row) -> Specimen:
    return Specimen(
        code=str(row["code"]),
        set_code=str(row["set_code"]),
        ticket_number=str(row["ticket_number"]),
        cast_at=datetime.fromisoformat(str(row["cast_at"])),
        size=SpecimenSize(str(row["size"])),
        cure=CureCondition(str(row["cure"])),
        purpose=SpecimenPurpose(str(row["purpose"])),
        age_days=int(row["age_days"]),
        notes=str(row["notes"]),
    )


def _break_from_row(row: sqlite3.Row) -> BreakResult:
    return BreakResult(
        specimen_code=str(row["specimen_code"]),
        tested_at=datetime.fromisoformat(str(row["tested_at"])),
        age_days=float(row["age_days"]),
        diameter_one=Quantity(float(row["diameter_one_in"]), "in"),
        diameter_two=Quantity(float(row["diameter_two_in"]), "in"),
        length=Quantity(float(row["length_in"]), "in"),
        max_load=Quantity(float(row["max_load_lbf"]), "lbf"),
        fracture=FractureType(str(row["fracture"])),
        tested_by=text(row["tested_by"]),
        notes=str(row["notes"]),
    )


class StrengthRepository:
    """Specimen sets, cylinders and breaks, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def open_set(
        self,
        set_code: str,
        mix_code: str,
        mix_revision: int,
        sampled_at: datetime,
        *,
        size: SpecimenSize = SpecimenSize.CYL_4X8,
        cure: CureCondition = CureCondition.STANDARD,
        purpose: SpecimenPurpose = SpecimenPurpose.ACCEPTANCE,
        ticket_number: str | None = None,
        project: str | None = None,
        notes: str = "",
    ) -> str:
        """Open a set of specimens against a mix design."""
        key = normalize_code(set_code, field="set_code")
        refuse_existing(
            self._db,
            "SELECT 1 FROM specimen_set WHERE set_code = ?",
            (key,),
            "specimen set",
            key,
        )
        self._db.execute(
            "INSERT INTO specimen_set (set_code, mix_code, mix_revision, ticket_number, "
            "project, size, cure, purpose, sampled_at, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                normalize_code(mix_code, field="mix_code"),
                mix_revision,
                None if ticket_number is None else normalize_ticket_number(ticket_number),
                project,
                size.value,
                cure.value,
                purpose.value,
                sampled_at.isoformat(),
                notes,
            ),
        )
        return key

    def save_specimen(self, specimen: Specimen) -> Specimen:
        """File one cylinder against a set that already exists."""
        if not self._db.query_one(
            "SELECT 1 FROM specimen_set WHERE set_code = ?", (specimen.set_code,)
        ):
            raise NotFoundError("specimen set", specimen.set_code)
        refuse_existing(
            self._db,
            "SELECT 1 FROM specimen WHERE code = ?",
            (specimen.code,),
            "specimen",
            specimen.code,
        )
        self._db.execute(
            "INSERT INTO specimen (code, set_code, ticket_number, cast_at, size, cure, "
            "purpose, age_days, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                specimen.code,
                specimen.set_code,
                specimen.ticket_number,
                specimen.cast_at.isoformat(),
                specimen.size.value,
                specimen.cure.value,
                specimen.purpose.value,
                specimen.age_days,
                specimen.notes,
            ),
        )
        return specimen

    def save_break(self, result: BreakResult) -> BreakResult:
        """File a break against a cylinder. A cylinder breaks only once."""
        if not self._db.query_one(
            "SELECT 1 FROM specimen WHERE code = ?", (result.specimen_code,)
        ):
            raise NotFoundError("specimen", result.specimen_code)
        refuse_existing(
            self._db,
            "SELECT 1 FROM break_result WHERE specimen_code = ?",
            (result.specimen_code,),
            "break",
            result.specimen_code,
        )
        self._db.execute(
            "INSERT INTO break_result (specimen_code, tested_at, age_days, diameter_one_in, "
            "diameter_two_in, length_in, max_load_lbf, fracture, tested_by, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                result.specimen_code,
                result.tested_at.isoformat(),
                result.age_days,
                result.diameter_one.to("in").value,
                result.diameter_two.to("in").value,
                result.length.to("in").value,
                result.max_load.to("lbf").value,
                result.fracture.value,
                result.tested_by,
                result.notes,
            ),
        )
        return result

    def specimens_in(self, set_code: str) -> tuple[Specimen, ...]:
        """Every cylinder in one set, in code order."""
        key = normalize_code(set_code, field="set_code")
        rows = self._db.query("SELECT * FROM specimen WHERE set_code = ? ORDER BY code", (key,))
        return tuple(_specimen_from_row(row) for row in rows)

    def breaks_in(self, set_code: str) -> tuple[BreakResult, ...]:
        """Every break in one set, in specimen order."""
        key = normalize_code(set_code, field="set_code")
        rows = self._db.query(
            "SELECT b.* FROM break_result b JOIN specimen s ON s.code = b.specimen_code "
            "WHERE s.set_code = ? ORDER BY b.specimen_code",
            (key,),
        )
        return tuple(_break_from_row(row) for row in rows)

    def pending_breaks(self, on: date) -> tuple[Specimen, ...]:
        """Cylinders that are due or overdue and have not been broken."""
        rows = self._db.query(
            "SELECT s.* FROM specimen s LEFT JOIN break_result b ON b.specimen_code = s.code "
            "WHERE b.specimen_code IS NULL ORDER BY s.cast_at, s.code"
        )
        specimens = tuple(_specimen_from_row(row) for row in rows)
        return tuple(s for s in specimens if s.due_at.date() <= on)

    def strength_test(self, set_code: str) -> StrengthTest:
        """The strength test one set adds up to."""
        key = normalize_code(set_code, field="set_code")
        row = require_one(
            self._db,
            "SELECT * FROM specimen_set WHERE set_code = ?",
            (key,),
            "specimen set",
            key,
        )
        breaks = self.breaks_in(key)
        if not breaks:
            raise NotFoundError("break for set", key)
        return StrengthTest(
            set_code=key,
            mix_code=str(row["mix_code"]),
            breaks=breaks,
            size=SpecimenSize(str(row["size"])),
            cure=CureCondition(str(row["cure"])),
            purpose=SpecimenPurpose(str(row["purpose"])),
            ticket_number=text(row["ticket_number"]),
            project=text(row["project"]),
        )

    def tests_for_mix(self, mix_code: str) -> tuple[StrengthTest, ...]:
        """Every set for one mix that has at least one break, oldest first."""
        key = normalize_code(mix_code, field="mix_code")
        rows = self._db.query(
            "SELECT set_code FROM specimen_set WHERE mix_code = ? "
            "ORDER BY sampled_at, set_code",
            (key,),
        )
        tests: list[StrengthTest] = []
        for row in rows:
            if self.breaks_in(str(row["set_code"])):
                tests.append(self.strength_test(str(row["set_code"])))
        return tuple(tests)

    def tests_for_project(self, project: str) -> tuple[StrengthTest, ...]:
        """Every set for one job that has at least one break, oldest first."""
        rows = self._db.query(
            "SELECT set_code FROM specimen_set WHERE project = ? ORDER BY sampled_at, set_code",
            (project,),
        )
        tests: list[StrengthTest] = []
        for row in rows:
            if self.breaks_in(str(row["set_code"])):
                tests.append(self.strength_test(str(row["set_code"])))
        return tuple(tests)

    def delete_set(self, set_code: str) -> None:
        """Remove a set, its cylinders and their breaks."""
        key = normalize_code(set_code, field="set_code")
        cursor = self._db.execute("DELETE FROM specimen_set WHERE set_code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("specimen set", key)
