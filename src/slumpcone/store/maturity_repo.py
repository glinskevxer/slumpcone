"""Reading and writing maturity curves and temperature logs.

A curve is stored under a name as well as a mixture, because a plant fits more
than one: a summer curve and a winter curve for the same mixture are different
relationships and using one for the other is the mistake the method invites.

Logger readings are keyed on the sensor and the moment, so re-uploading a
logger's whole memory after every visit is cheap and safe: the readings already
on file collide and the new ones land.
"""

from __future__ import annotations

from datetime import date, datetime

from slumpcone.errors import ConflictError, NotFoundError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range
from slumpcone.strength.maturity import (
    MaturityCurve,
    MaturityPoint,
    TemperatureReading,
)
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature


class MaturityRepository:
    """Maturity curves and temperature logs, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save_curve(
        self, curve: MaturityCurve, name: str, fitted_on: date, notes: str = ""
    ) -> MaturityCurve:
        """File a curve under a name. Refuses to overwrite one."""
        label = normalize_name(name, field="curve_name")
        if self._db.query_one(
            "SELECT 1 FROM maturity_curve WHERE mix_code = ? AND name = ?",
            (curve.mix_code, label),
        ):
            raise ConflictError("maturity curve", f"{curve.mix_code} {label}")
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO maturity_curve (mix_code, name, fitted_on, notes) "
                "VALUES (?, ?, ?, ?)",
                (curve.mix_code, label, fitted_on.isoformat(), notes),
            )
            for point in curve.points:
                self._db.execute(
                    "INSERT INTO maturity_point (mix_code, name, maturity, strength_psi) "
                    "VALUES (?, ?, ?, ?)",
                    (curve.mix_code, label, point.maturity, point.strength.to("psi").value),
                )
        return curve

    def curve(self, mix_code: str, name: str) -> MaturityCurve:
        """One curve by mixture and name."""
        key = normalize_code(mix_code, field="mix_code")
        label = normalize_name(name, field="curve_name")
        rows = self._db.query(
            "SELECT * FROM maturity_point WHERE mix_code = ? AND name = ? ORDER BY maturity",
            (key, label),
        )
        if not rows:
            raise NotFoundError("maturity curve", f"{key} {label}")
        points = tuple(
            MaturityPoint(float(row["maturity"]), Quantity(float(row["strength_psi"]), "psi"))
            for row in rows
        )
        return MaturityCurve(key, points)

    def curves_for(self, mix_code: str) -> tuple[str, ...]:
        """Every curve name on file for one mixture, sorted."""
        key = normalize_code(mix_code, field="mix_code")
        rows = self._db.query(
            "SELECT name FROM maturity_curve WHERE mix_code = ? ORDER BY name", (key,)
        )
        return tuple(str(row["name"]) for row in rows)

    def delete_curve(self, mix_code: str, name: str) -> None:
        """Remove a curve and its points."""
        key = normalize_code(mix_code, field="mix_code")
        label = normalize_name(name, field="curve_name")
        cursor = self._db.execute(
            "DELETE FROM maturity_curve WHERE mix_code = ? AND name = ?", (key, label)
        )
        if cursor.rowcount == 0:
            raise NotFoundError("maturity curve", f"{key} {label}")

    def record_reading(
        self, sensor: str, placement: str, reading: TemperatureReading
    ) -> TemperatureReading:
        """File one logger reading. A repeat of the same moment is refused."""
        code = normalize_code(sensor, field="sensor")
        where = normalize_name(placement, field="placement")
        if self._db.query_one(
            "SELECT 1 FROM temperature_log WHERE sensor = ? AND at = ?",
            (code, reading.at.isoformat()),
        ):
            raise ConflictError("reading", f"{code} at {reading.at.isoformat()}")
        self._db.execute(
            "INSERT INTO temperature_log (sensor, placement, at, temperature_f) "
            "VALUES (?, ?, ?, ?)",
            (code, where, reading.at.isoformat(), reading.temperature.fahrenheit),
        )
        return reading

    def upload(self, sensor: str, placement: str, readings: list[TemperatureReading]) -> int:
        """File a logger's memory, skipping what is already on file."""
        landed = 0
        with self._db.transaction():
            for reading in readings:
                try:
                    self.record_reading(sensor, placement, reading)
                except ConflictError:
                    continue
                landed += 1
        return landed

    def readings(self, sensor: str) -> tuple[TemperatureReading, ...]:
        """Every reading from one sensor, oldest first."""
        code = normalize_code(sensor, field="sensor")
        rows = self._db.query(
            "SELECT * FROM temperature_log WHERE sensor = ? ORDER BY at", (code,)
        )
        return tuple(
            TemperatureReading(
                datetime.fromisoformat(str(row["at"])),
                Temperature(float(row["temperature_f"]), "F"),
            )
            for row in rows
        )

    def readings_between(
        self, sensor: str, start: date, end: date
    ) -> tuple[TemperatureReading, ...]:
        """One sensor's readings over a window."""
        code = normalize_code(sensor, field="sensor")
        rows = self._db.query(
            "SELECT * FROM temperature_log WHERE sensor = ? AND at >= ? AND at < ? ORDER BY at",
            (code, *day_range(start, end)),
        )
        return tuple(
            TemperatureReading(
                datetime.fromisoformat(str(row["at"])),
                Temperature(float(row["temperature_f"]), "F"),
            )
            for row in rows
        )

    def sensors(self, placement: str) -> tuple[str, ...]:
        """Every sensor logging one placement, sorted."""
        where = normalize_name(placement, field="placement")
        rows = self._db.query(
            "SELECT DISTINCT sensor FROM temperature_log WHERE placement = ? ORDER BY sensor",
            (where,),
        )
        return tuple(str(row["sensor"]) for row in rows)

    def estimate(self, mix_code: str, name: str, sensor: str) -> Quantity:
        """The in place strength one sensor's history reads off a curve."""
        from slumpcone.strength.maturity import estimate_in_place

        readings = self.readings(sensor)
        if len(readings) < 2:
            raise ValidationError(
                f"{normalize_code(sensor)} has fewer than two readings", field="sensor"
            )
        return estimate_in_place(self.curve(mix_code, name), list(readings)).strength
