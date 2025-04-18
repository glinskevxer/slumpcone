"""Reading and writing bleeding and segregation results.

A bleeding test is keyed on the ticket and the day rather than on the ticket
alone. Two labs sample the same load on a disputed pour more often than anyone
would like, and the second test is not a correction of the first.

The draws are written whole every time. A part filed test is worse than none:
the total and the rate both divide by figures that only mean something if every
draw is present.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.fresh.bleeding import (
    BleedReading,
    BleedTest,
    ColumnSegregation,
    VisualStability,
)
from slumpcone.identity import normalize_code
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range, whole
from slumpcone.units.quantity import Quantity


class BleedingRepository:
    """Bleeding tests and column segregation results, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(
        self, test: BleedTest, tested_on: date, *, technician: str = "", replace: bool = False
    ) -> BleedTest:
        """File a bleeding test with every draw it took."""
        key = (test.ticket_number, tested_on.isoformat())
        existing = self._db.query_one(
            "SELECT 1 FROM bleed_test WHERE ticket_number = ? AND tested_on = ?", key
        )
        if existing and not replace:
            raise ConflictError("bleed test", f"{test.ticket_number} on {tested_on}")
        with self._db.transaction():
            if existing:
                self._db.execute(
                    "DELETE FROM bleed_test WHERE ticket_number = ? AND tested_on = ?", key
                )
                self._db.execute(
                    "DELETE FROM bleed_reading WHERE ticket_number = ? AND tested_on = ?", key
                )
            self._db.execute(
                "INSERT INTO bleed_test (ticket_number, tested_on, technician, "
                "sample_mass_lb, batch_mass_lb, batch_water_lb, area_in2) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    *key,
                    technician,
                    test.sample_mass.to("lb").value,
                    test.batch_mass.to("lb").value,
                    test.batch_water.to("lb").value,
                    test.surface_area.to("in2").value,
                ),
            )
            for reading in test.readings:
                self._db.execute(
                    "INSERT INTO bleed_reading (ticket_number, tested_on, "
                    "elapsed_minutes, water_lb) VALUES (?, ?, ?, ?)",
                    (*key, reading.elapsed_minutes, reading.water.to("lb").value),
                )
        return test

    def get(self, ticket_number: str, tested_on: date) -> BleedTest:
        """One bleeding test, with its draws in the order they were taken."""
        number = normalize_code(ticket_number, field="ticket_number")
        key = (number, tested_on.isoformat())
        row = self._db.query_one(
            "SELECT * FROM bleed_test WHERE ticket_number = ? AND tested_on = ?", key
        )
        if row is None:
            raise NotFoundError("bleed test", f"{number} on {tested_on}")
        draws = self._db.query(
            "SELECT * FROM bleed_reading WHERE ticket_number = ? AND tested_on = ? "
            "ORDER BY elapsed_minutes",
            key,
        )
        return BleedTest(
            number,
            Quantity(float(row["sample_mass_lb"]), "lb"),
            Quantity(float(row["batch_mass_lb"]), "lb"),
            Quantity(float(row["batch_water_lb"]), "lb"),
            Quantity(float(row["area_in2"]), "in2"),
            tuple(
                BleedReading(
                    float(draw["elapsed_minutes"]),
                    Quantity(float(draw["water_lb"]), "lb"),
                )
                for draw in draws
            ),
        )

    def for_ticket(self, ticket_number: str) -> tuple[BleedTest, ...]:
        """Every bleeding test on one load, oldest first."""
        number = normalize_code(ticket_number, field="ticket_number")
        rows = self._db.query(
            "SELECT tested_on FROM bleed_test WHERE ticket_number = ? ORDER BY tested_on",
            (number,),
        )
        return tuple(self.get(number, date.fromisoformat(row["tested_on"])) for row in rows)

    def between(self, start: date, end: date) -> tuple[BleedTest, ...]:
        """Every bleeding test in a window."""
        rows = self._db.query(
            "SELECT ticket_number, tested_on FROM bleed_test "
            "WHERE tested_on >= ? AND tested_on < ? ORDER BY tested_on, ticket_number",
            day_range(start, end),
        )
        return tuple(
            self.get(row["ticket_number"], date.fromisoformat(row["tested_on"])) for row in rows
        )

    def save_segregation(
        self,
        column: ColumnSegregation,
        tested_on: date,
        *,
        technician: str = "",
        visual: VisualStability | None = None,
    ) -> ColumnSegregation:
        """File a column segregation result, with the eyeball index if one was taken."""
        key = (column.ticket_number, tested_on.isoformat())
        if self._db.query_one(
            "SELECT 1 FROM column_segregation WHERE ticket_number = ? AND tested_on = ?", key
        ):
            raise ConflictError("segregation test", f"{column.ticket_number} on {tested_on}")
        self._db.execute(
            "INSERT INTO column_segregation (ticket_number, tested_on, technician, "
            "top_coarse_lb, bottom_coarse_lb, visual_index) VALUES (?, ?, ?, ?, ?, ?)",
            (
                *key,
                technician,
                column.top_coarse.to("lb").value,
                column.bottom_coarse.to("lb").value,
                None if visual is None else visual.value,
            ),
        )
        return column

    def segregation(self, ticket_number: str, tested_on: date) -> ColumnSegregation:
        """One segregation result."""
        number = normalize_code(ticket_number, field="ticket_number")
        row = self._db.query_one(
            "SELECT * FROM column_segregation WHERE ticket_number = ? AND tested_on = ?",
            (number, tested_on.isoformat()),
        )
        if row is None:
            raise NotFoundError("segregation test", f"{number} on {tested_on}")
        return ColumnSegregation(
            number,
            Quantity(float(row["top_coarse_lb"]), "lb"),
            Quantity(float(row["bottom_coarse_lb"]), "lb"),
        )

    def visual_index(self, ticket_number: str, tested_on: date) -> VisualStability | None:
        """The index a technician assigned, if anybody did."""
        number = normalize_code(ticket_number, field="ticket_number")
        row = self._db.query_one(
            "SELECT visual_index FROM column_segregation "
            "WHERE ticket_number = ? AND tested_on = ?",
            (number, tested_on.isoformat()),
        )
        if row is None:
            raise NotFoundError("segregation test", f"{number} on {tested_on}")
        raw = whole(row["visual_index"])
        return None if raw is None else VisualStability(raw)

    def segregations_between(self, start: date, end: date) -> tuple[ColumnSegregation, ...]:
        """Every segregation result in a window."""
        rows = self._db.query(
            "SELECT ticket_number, tested_on FROM column_segregation "
            "WHERE tested_on >= ? AND tested_on < ? ORDER BY tested_on, ticket_number",
            day_range(start, end),
        )
        return tuple(
            self.segregation(row["ticket_number"], date.fromisoformat(row["tested_on"]))
            for row in rows
        )

    def failing_segregations(
        self, results: Sequence[ColumnSegregation] | None = None
    ) -> tuple[ColumnSegregation, ...]:
        """The results over the ten percent cap.

        Passing the results in avoids a second read when the caller already has
        them; passing nothing reads everything on file.
        """
        pool = (
            results
            if results is not None
            else self.segregations_between(date(1900, 1, 1), date(2999, 12, 31))
        )
        return tuple(result for result in pool if not result.is_acceptable)
