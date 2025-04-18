"""Reading and writing mixer uniformity tests.

A test is the pair of samples, never one of them. Storing a sample on its own
would let a caller ask for a verdict off half a test, and the verdict would look
exactly like a real one. So the pair goes in together and comes back together,
and the repository refuses a test that is not two samples.

The samples keep their labels rather than being numbered first and second. C94
pulls them at fifteen and eighty five percent of discharge and the label is the
only place that survives on the sheet.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from slumpcone.batching.uniformity import (
    UniformityError,
    UniformityResult,
    UniformitySample,
    compare,
)
from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range, number
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


@dataclass(frozen=True, slots=True)
class UniformityRecord:
    """A filed test: who ran it, on what, and the pair it pulled."""

    mixer: str
    tested_on: date
    plant_code: str
    technician: str
    notes: str
    first: UniformitySample
    second: UniformitySample

    def judge(self) -> UniformityResult:
        """Run C94 Table A1.1 on the pair."""
        return compare(self.mixer, self.first, self.second)


class UniformityRepository:
    """Mixer uniformity tests, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(
        self,
        mixer: str,
        tested_on: date,
        first: UniformitySample,
        second: UniformitySample,
        *,
        plant_code: str = "",
        technician: str = "",
        notes: str = "",
    ) -> UniformityRecord:
        """File a test with both its samples."""
        code = normalize_code(mixer, field="mixer")
        if first.label == second.label:
            raise UniformityError(
                "UNIFORMITY_SAME_SAMPLE", "the two samples have to be told apart by label"
            )
        key = (code, tested_on.isoformat())
        if self._db.query_one(
            "SELECT 1 FROM uniformity_test WHERE mixer = ? AND tested_on = ?", key
        ):
            raise ConflictError("uniformity test", f"{code} on {tested_on}")
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO uniformity_test (mixer, tested_on, plant_code, "
                "technician, notes) VALUES (?, ?, ?, ?, ?)",
                (*key, plant_code, technician, notes),
            )
            for sample in (first, second):
                self._db.execute(
                    "INSERT INTO uniformity_sample (mixer, tested_on, label, "
                    "unit_weight_lb_ft3, air_percent, slump_in, coarse_retained_pct, "
                    "coarse_gravity, sample_volume_ft3, coarse_mass_lb, "
                    "strength_7day_psi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        *key,
                        sample.label,
                        sample.unit_weight.to("lb", "ft3").value,
                        sample.air.value,
                        sample.slump.to("in").value,
                        sample.coarse_retained.value,
                        sample.coarse_specific_gravity,
                        sample.sample_volume.to("ft3").value,
                        sample.coarse_mass.to("lb").value,
                        None
                        if sample.strength_7day is None
                        else sample.strength_7day.to("psi").value,
                    ),
                )
        return UniformityRecord(code, tested_on, plant_code, technician, notes, first, second)

    def get(self, mixer: str, tested_on: date) -> UniformityRecord:
        """One test, with both samples."""
        code = normalize_code(mixer, field="mixer")
        key = (code, tested_on.isoformat())
        row = self._db.query_one(
            "SELECT * FROM uniformity_test WHERE mixer = ? AND tested_on = ?", key
        )
        if row is None:
            raise NotFoundError("uniformity test", f"{code} on {tested_on}")
        samples = self._db.query(
            "SELECT * FROM uniformity_sample WHERE mixer = ? AND tested_on = ? ORDER BY label",
            key,
        )
        if len(samples) != 2:
            raise UniformityError(
                "UNIFORMITY_HALF_A_TEST",
                f"{code} on {tested_on} has {len(samples)} sample(s) on file, not two",
            )
        first, second = (self._sample(sample) for sample in samples)
        return UniformityRecord(
            code,
            tested_on,
            str(row["plant_code"]),
            str(row["technician"]),
            str(row["notes"]),
            first,
            second,
        )

    def _sample(self, row: sqlite3.Row) -> UniformitySample:
        """One row back as a sample."""
        strength = number(row["strength_7day_psi"])
        return UniformitySample(
            str(row["label"]),
            MassPerVolume(float(str(row["unit_weight_lb_ft3"])), "lb", "ft3"),
            Percent(float(str(row["air_percent"]))),
            Quantity(float(str(row["slump_in"])), "in"),
            Percent(float(str(row["coarse_retained_pct"]))),
            float(str(row["coarse_gravity"])),
            Quantity(float(str(row["sample_volume_ft3"])), "ft3"),
            Quantity(float(str(row["coarse_mass_lb"])), "lb"),
            None if strength is None else Quantity(strength, "psi"),
        )

    def for_mixer(self, mixer: str) -> tuple[UniformityRecord, ...]:
        """Every test on one mixer, oldest first."""
        code = normalize_code(mixer, field="mixer")
        rows = self._db.query(
            "SELECT tested_on FROM uniformity_test WHERE mixer = ? ORDER BY tested_on",
            (code,),
        )
        return tuple(self.get(code, date.fromisoformat(str(row["tested_on"]))) for row in rows)

    def between(
        self, start: date, end: date, *, plant_code: str | None = None
    ) -> tuple[UniformityRecord, ...]:
        """Every test in a window, optionally at one plant."""
        window = day_range(start, end)
        if plant_code is None:
            rows = self._db.query(
                "SELECT mixer, tested_on FROM uniformity_test "
                "WHERE tested_on >= ? AND tested_on < ? ORDER BY tested_on, mixer",
                window,
            )
        else:
            rows = self._db.query(
                "SELECT mixer, tested_on FROM uniformity_test "
                "WHERE tested_on >= ? AND tested_on < ? AND plant_code = ? "
                "ORDER BY tested_on, mixer",
                (*window, normalize_code(plant_code, field="plant_code")),
            )
        return tuple(
            self.get(str(row["mixer"]), date.fromisoformat(str(row["tested_on"])))
            for row in rows
        )

    def latest(self, mixer: str) -> UniformityRecord | None:
        """The most recent test on one mixer, or nothing if it has never been tested."""
        tests = self.for_mixer(mixer)
        return tests[-1] if tests else None

    def due(
        self, mixers: tuple[str, ...], on: date, *, every_days: int = 365
    ) -> tuple[str, ...]:
        """The mixers whose last uniformity test has run out, or that never had one.

        C94 does not set the interval. Plants pick one and most pick a year, so
        that is the default and it is an argument rather than a constant.
        """
        overdue = []
        for mixer in mixers:
            last = self.latest(mixer)
            if last is None or (on - last.tested_on).days > every_days:
                overdue.append(normalize_code(mixer, field="mixer"))
        return tuple(overdue)
