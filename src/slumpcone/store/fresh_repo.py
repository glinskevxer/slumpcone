"""Reading and writing fresh property tests.

The uniqueness key is the ticket, the method, the time and whether it was a
retest. That combination is what a field sheet actually identifies a test by,
and it means a technician who enters the same test twice gets a refusal rather
than a duplicate that quietly doubles a load's sample count.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.identity import normalize_ticket_number
from slumpcone.percent import Percent
from slumpcone.store.db import Database
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from slumpcone.units.temperature import Temperature


def _from_row(row: sqlite3.Row) -> FreshTest:
    return FreshTest(
        ticket_number=str(row["ticket_number"]),
        kind=FreshTestKind(str(row["kind"])),
        taken_at=datetime.fromisoformat(str(row["taken_at"])),
        slump=None if row["slump_in"] is None else Quantity(float(row["slump_in"]), "in"),
        air=None if row["air_pct"] is None else Percent(float(row["air_pct"])),
        temperature=(
            None
            if row["temperature_f"] is None
            else Temperature(float(row["temperature_f"]), "F")
        ),
        unit_weight=(
            None
            if row["unit_weight_lb_ft3"] is None
            else MassPerVolume(float(row["unit_weight_lb_ft3"]), "lb", "ft3")
        ),
        discharged_before_sample=(
            None
            if row["discharged_before_yd3"] is None
            else Quantity(float(row["discharged_before_yd3"]), "yd3")
        ),
        technician=None if row["technician"] is None else str(row["technician"]),
        is_retest=bool(row["is_retest"]),
        notes=str(row["notes"]),
    )


class FreshTestRepository:
    """Fresh property tests, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, test: FreshTest) -> FreshTest:
        """File one test. Refuses an exact duplicate."""
        existing = self._db.query_one(
            "SELECT 1 FROM fresh_test WHERE ticket_number = ? AND kind = ? "
            "AND taken_at = ? AND is_retest = ?",
            (
                test.ticket_number,
                test.kind.value,
                test.taken_at.isoformat(),
                int(test.is_retest),
            ),
        )
        if existing is not None:
            raise ConflictError(
                "fresh test", f"{test.ticket_number} {test.kind} {test.taken_at.isoformat()}"
            )
        self._db.execute(
            "INSERT INTO fresh_test (ticket_number, kind, taken_at, slump_in, air_pct, "
            "temperature_f, unit_weight_lb_ft3, discharged_before_yd3, technician, "
            "is_retest, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                test.ticket_number,
                test.kind.value,
                test.taken_at.isoformat(),
                None if test.slump is None else test.slump.to("in").value,
                None if test.air is None else test.air.value,
                None if test.temperature is None else test.temperature.fahrenheit,
                None if test.unit_weight is None else test.unit_weight.to("lb", "ft3").value,
                (
                    None
                    if test.discharged_before_sample is None
                    else test.discharged_before_sample.to("yd3").value
                ),
                test.technician,
                int(test.is_retest),
                test.notes,
            ),
        )
        return test

    def save_all(self, tests: list[FreshTest]) -> None:
        """File several tests in one transaction."""
        with self._db.transaction():
            for test in tests:
                self.save(test)

    def for_ticket(self, ticket_number: str) -> tuple[FreshTest, ...]:
        """Every test on one load, oldest first."""
        key = normalize_ticket_number(ticket_number)
        rows = self._db.query(
            "SELECT * FROM fresh_test WHERE ticket_number = ? ORDER BY taken_at, is_retest, id",
            (key,),
        )
        return tuple(_from_row(row) for row in rows)

    def of_kind(self, kind: FreshTestKind, start: date, end: date) -> tuple[FreshTest, ...]:
        """Every test of one method in a window, oldest first."""
        rows = self._db.query(
            "SELECT * FROM fresh_test WHERE kind = ? AND taken_at >= ? AND taken_at < ? "
            "ORDER BY taken_at, id",
            (kind.value, start.isoformat(), f"{end.isoformat()}T23:59:59.999999"),
        )
        return tuple(_from_row(row) for row in rows)

    def between(self, start: date, end: date) -> tuple[FreshTest, ...]:
        """Every test in a window, oldest first."""
        rows = self._db.query(
            "SELECT * FROM fresh_test WHERE taken_at >= ? AND taken_at < ? "
            "ORDER BY taken_at, id",
            (start.isoformat(), f"{end.isoformat()}T23:59:59.999999"),
        )
        return tuple(_from_row(row) for row in rows)

    def tickets_tested(self, start: date, end: date) -> tuple[str, ...]:
        """Which loads were tested at all in a window."""
        rows = self._db.query(
            "SELECT DISTINCT ticket_number FROM fresh_test WHERE taken_at >= ? "
            "AND taken_at < ? ORDER BY ticket_number",
            (start.isoformat(), f"{end.isoformat()}T23:59:59.999999"),
        )
        return tuple(str(row["ticket_number"]) for row in rows)

    def count(self) -> int:
        """How many tests are on file."""
        return int(self._db.scalar("SELECT count(*) FROM fresh_test") or 0)

    def delete_for_ticket(self, ticket_number: str) -> int:
        """Remove every test on one load, returning how many went."""
        key = normalize_ticket_number(ticket_number)
        cursor = self._db.execute("DELETE FROM fresh_test WHERE ticket_number = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("fresh test for ticket", key)
        return int(cursor.rowcount)
