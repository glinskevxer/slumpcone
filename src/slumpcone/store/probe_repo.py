"""Reading and writing moisture probe calibration checks.

Checks are keyed on the plant as well as the probe, because a probe code is a
bin number and every plant has a bin one. Reading MP-1's history across two
plants would blend two different sensors into one drift figure, and the figure
would look fine.

Nothing here computes a standing. The rules live in the probe module and this
gathers the rows and hands back a history, so the answer the batch panel would
get and the answer a report prints come from the same code.
"""

from __future__ import annotations

from datetime import date

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.plant.probe import ProbeCheck, ProbeHistory, probes_needing_attention
from slumpcone.store.db import Database
from slumpcone.store.guards import require_one
from slumpcone.store.rows import day_range


class ProbeRepository:
    """Moisture probe checks, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(
        self, check: ProbeCheck, plant_code: str, *, notes: str = "", replace: bool = False
    ) -> ProbeCheck:
        """File a check. One per probe per day."""
        plant = normalize_code(plant_code, field="plant_code")
        key = (plant, check.probe_code, check.checked_on.isoformat())
        existing = self._db.query_one(
            "SELECT 1 FROM probe_check WHERE plant_code = ? AND probe_code = ? "
            "AND checked_on = ?",
            key,
        )
        if existing and not replace:
            raise ConflictError(
                "probe check", f"{plant} {check.probe_code} on {check.checked_on}"
            )
        if existing:
            self._db.execute(
                "DELETE FROM probe_check WHERE plant_code = ? AND probe_code = ? "
                "AND checked_on = ?",
                key,
            )
        self._db.execute(
            "INSERT INTO probe_check (probe_code, plant_code, checked_on, "
            "probe_percent, oven_percent, technician, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                check.probe_code,
                plant,
                check.checked_on.isoformat(),
                check.probe_reading.value,
                check.oven_reading.value,
                check.technician,
                notes,
            ),
        )
        return check

    def get(self, plant_code: str, probe_code: str, checked_on: date) -> ProbeCheck:
        """One check."""
        plant = normalize_code(plant_code, field="plant_code")
        probe = normalize_code(probe_code, field="probe_code")
        row = require_one(
            self._db,
            "SELECT * FROM probe_check WHERE plant_code = ? AND probe_code = ? "
            "AND checked_on = ?",
            (plant, probe, checked_on.isoformat()),
            "probe check",
            f"{plant} {probe} on {checked_on}",
        )
        return self._from_row(row)

    @staticmethod
    def _from_row(row: object) -> ProbeCheck:
        """One row back as a check."""
        mapping = dict(row)  # type: ignore[call-overload]
        return ProbeCheck(
            str(mapping["probe_code"]),
            date.fromisoformat(str(mapping["checked_on"])),
            Percent(float(mapping["probe_percent"])),
            Percent(float(mapping["oven_percent"])),
            str(mapping["technician"]),
        )

    def history(self, plant_code: str, probe_code: str) -> ProbeHistory:
        """Every check on one probe at one plant, oldest first."""
        plant = normalize_code(plant_code, field="plant_code")
        probe = normalize_code(probe_code, field="probe_code")
        rows = self._db.query(
            "SELECT * FROM probe_check WHERE plant_code = ? AND probe_code = ? "
            "ORDER BY checked_on",
            (plant, probe),
        )
        return ProbeHistory(probe, tuple(self._from_row(row) for row in rows))

    def probes(self, plant_code: str) -> tuple[str, ...]:
        """Every probe with a check on file at one plant, sorted."""
        plant = normalize_code(plant_code, field="plant_code")
        rows = self._db.query(
            "SELECT DISTINCT probe_code FROM probe_check WHERE plant_code = ? "
            "ORDER BY probe_code",
            (plant,),
        )
        return tuple(str(row["probe_code"]) for row in rows)

    def histories(self, plant_code: str) -> tuple[ProbeHistory, ...]:
        """Every probe at one plant, with its checks."""
        return tuple(self.history(plant_code, probe) for probe in self.probes(plant_code))

    def needing_attention(self, plant_code: str, on: date) -> tuple[ProbeHistory, ...]:
        """The probes the plant should not be batching off, worst first."""
        return probes_needing_attention(self.histories(plant_code), on)

    def checks_between(self, plant_code: str, start: date, end: date) -> tuple[ProbeCheck, ...]:
        """Every check in a window."""
        plant = normalize_code(plant_code, field="plant_code")
        rows = self._db.query(
            "SELECT * FROM probe_check WHERE plant_code = ? AND checked_on >= ? "
            "AND checked_on < ? ORDER BY checked_on, probe_code",
            (plant, *day_range(start, end)),
        )
        return tuple(self._from_row(row) for row in rows)

    def forget(self, plant_code: str, probe_code: str, checked_on: date) -> None:
        """Drop one check."""
        plant = normalize_code(plant_code, field="plant_code")
        probe = normalize_code(probe_code, field="probe_code")
        cursor = self._db.execute(
            "DELETE FROM probe_check WHERE plant_code = ? AND probe_code = ? "
            "AND checked_on = ?",
            (plant, probe, checked_on.isoformat()),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("probe check", f"{plant} {probe} on {checked_on}")
