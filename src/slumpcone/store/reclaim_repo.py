"""Reading and writing wash water readings and returned loads.

A tank reading is keyed on the day as well as the tank, because the density of a
wash tank is not a property of the tank. It is a measurement, it changes every
time somebody washes out, and a plant that overwrites yesterday's reading has
thrown away the only evidence about what went into yesterday's concrete.

A returned load is keyed on its ticket, because there is exactly one of it. What
happens to it afterwards is a separate write: it either goes into a later load,
in which case the ticket that took it is recorded, or it is dumped, in which
case the day it was dumped is. A load with neither is still sitting on the yard,
and finding those is the whole reason this table exists.
"""

from __future__ import annotations

from datetime import date, timedelta

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.materials.wash_water import ReturnedConcrete, WashWater, usable_tanks
from slumpcone.store.db import Database
from slumpcone.store.guards import refuse_existing, require_one
from slumpcone.store.rows import day, day_range, text
from slumpcone.units.quantity import Quantity


class ReclaimRepository:
    """Wash tank readings and returned loads, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save_reading(
        self,
        tank: WashWater,
        plant_code: str,
        measured_on: date,
        *,
        notes: str = "",
        replace: bool = False,
    ) -> WashWater:
        """File a density reading for one tank on one day."""
        plant = normalize_code(plant_code, field="plant_code")
        key = (plant, tank.tank, measured_on.isoformat())
        if replace:
            self._db.execute(
                "DELETE FROM wash_tank WHERE plant_code = ? AND tank = ? AND measured_on = ?",
                key,
            )
        else:
            refuse_existing(
                self._db,
                "SELECT 1 FROM wash_tank WHERE plant_code = ? AND tank = ? AND measured_on = ?",
                key,
                "wash tank reading",
                f"{plant} {tank.tank} on {measured_on}",
            )
        self._db.execute(
            "INSERT INTO wash_tank (tank, plant_code, measured_on, specific_gravity, "
            "volume, volume_unit, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tank.tank,
                plant,
                measured_on.isoformat(),
                tank.specific_gravity,
                tank.volume.value,
                tank.volume.unit,
                notes,
            ),
        )
        return tank

    def reading(self, plant_code: str, tank: str, measured_on: date) -> WashWater:
        """One reading."""
        plant = normalize_code(plant_code, field="plant_code")
        name = normalize_code(tank, field="tank")
        row = require_one(
            self._db,
            "SELECT * FROM wash_tank WHERE plant_code = ? AND tank = ? AND measured_on = ?",
            (plant, name, measured_on.isoformat()),
            "wash tank reading",
            f"{plant} {name} on {measured_on}",
        )
        return WashWater(
            str(row["tank"]),
            float(row["specific_gravity"]),
            Quantity(float(row["volume"]), str(row["volume_unit"])),
        )

    def readings_on(self, plant_code: str, measured_on: date) -> tuple[WashWater, ...]:
        """Every tank read on one day at one plant, in tank order."""
        plant = normalize_code(plant_code, field="plant_code")
        rows = self._db.query(
            "SELECT tank FROM wash_tank WHERE plant_code = ? AND measured_on = ? ORDER BY tank",
            (plant, measured_on.isoformat()),
        )
        return tuple(self.reading(plant, str(row["tank"]), measured_on) for row in rows)

    def usable_on(self, plant_code: str, measured_on: date) -> tuple[WashWater, ...]:
        """The tanks clean enough to batch from, cleanest first."""
        return usable_tanks(self.readings_on(plant_code, measured_on))

    def latest_reading(self, plant_code: str, tank: str) -> WashWater | None:
        """The most recent reading for one tank, or nothing."""
        plant = normalize_code(plant_code, field="plant_code")
        name = normalize_code(tank, field="tank")
        row = self._db.query_one(
            "SELECT measured_on FROM wash_tank WHERE plant_code = ? AND tank = ? "
            "ORDER BY measured_on DESC LIMIT 1",
            (plant, name),
        )
        if row is None:
            return None
        return self.reading(plant, name, date.fromisoformat(str(row["measured_on"])))

    def save_returned(self, load: ReturnedConcrete, returned_on: date) -> ReturnedConcrete:
        """File a load that came back."""
        if self._db.query_one(
            "SELECT 1 FROM returned_concrete WHERE ticket_number = ?",
            (load.ticket_number,),
        ):
            raise ConflictError("returned load", load.ticket_number)
        self._db.execute(
            "INSERT INTO returned_concrete (ticket_number, mix_code, returned_on, "
            "volume, volume_unit, age_minutes) VALUES (?, ?, ?, ?, ?, ?)",
            (
                load.ticket_number,
                load.mix_code,
                returned_on.isoformat(),
                load.volume.value,
                load.volume.unit,
                load.age_at_return.total_seconds() / 60,
            ),
        )
        return load

    def returned(self, ticket_number: str) -> ReturnedConcrete:
        """One returned load."""
        key = normalize_code(ticket_number, field="ticket_number")
        row = require_one(
            self._db,
            "SELECT * FROM returned_concrete WHERE ticket_number = ?",
            (key,),
            "returned load",
            key,
        )
        return ReturnedConcrete(
            str(row["ticket_number"]),
            str(row["mix_code"]),
            Quantity(float(row["volume"]), str(row["volume_unit"])),
            timedelta(minutes=float(row["age_minutes"])),
        )

    def returned_between(self, start: date, end: date) -> tuple[ReturnedConcrete, ...]:
        """Every load that came back in a window."""
        rows = self._db.query(
            "SELECT ticket_number FROM returned_concrete "
            "WHERE returned_on >= ? AND returned_on < ? ORDER BY returned_on, ticket_number",
            day_range(start, end),
        )
        return tuple(self.returned(str(row["ticket_number"])) for row in rows)

    def use_in(self, ticket_number: str, new_ticket: str) -> None:
        """Record that a returned load went into a later one."""
        key = normalize_code(ticket_number, field="ticket_number")
        self.returned(key)
        self._db.execute(
            "UPDATE returned_concrete SET used_in = ?, disposed_of = NULL "
            "WHERE ticket_number = ?",
            (normalize_code(new_ticket, field="ticket_number"), key),
        )

    def dispose(self, ticket_number: str, on: date) -> None:
        """Record that a returned load was dumped."""
        key = normalize_code(ticket_number, field="ticket_number")
        self.returned(key)
        self._db.execute(
            "UPDATE returned_concrete SET disposed_of = ?, used_in = NULL "
            "WHERE ticket_number = ?",
            (on.isoformat(), key),
        )

    def fate_of(self, ticket_number: str) -> tuple[str | None, date | None]:
        """What became of a returned load: the ticket that took it, or the day it went."""
        key = normalize_code(ticket_number, field="ticket_number")
        row = require_one(
            self._db,
            "SELECT used_in, disposed_of FROM returned_concrete WHERE ticket_number = ?",
            (key,),
            "returned load",
            key,
        )
        return (text(row["used_in"]), day(row["disposed_of"]))

    def still_on_the_yard(self, on: date) -> tuple[ReturnedConcrete, ...]:
        """Loads that came back and have neither been used nor dumped.

        This is the one query the table is for. A yard with three of these has
        three drums it cannot fill.
        """
        rows = self._db.query(
            "SELECT ticket_number FROM returned_concrete WHERE used_in IS NULL "
            "AND disposed_of IS NULL AND returned_on <= ? ORDER BY returned_on",
            (on.isoformat(),),
        )
        return tuple(self.returned(str(row["ticket_number"])) for row in rows)

    def forget(self, ticket_number: str) -> None:
        """Drop a returned load."""
        key = normalize_code(ticket_number, field="ticket_number")
        cursor = self._db.execute(
            "DELETE FROM returned_concrete WHERE ticket_number = ?", (key,)
        )
        if cursor.rowcount == 0:
            raise NotFoundError("returned load", key)
