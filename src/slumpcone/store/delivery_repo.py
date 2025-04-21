"""Reading and writing trucks and deliveries.

A delivery is written once when the load is batched and updated as the stages
come in, which is the opposite of how a ticket behaves. The truck tracking
system reports arrival ten minutes after departure and discharge an hour after
that, so the row has to grow rather than be written whole.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from slumpcone.delivery.record import Delivery
from slumpcone.delivery.truck import Truck
from slumpcone.delivery.water import RequestedBy, WaterAddition
from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code, normalize_ticket_number
from slumpcone.store.db import Database
from slumpcone.store.guards import require_one
from slumpcone.store.rows import day, day_range, moment, quantity, text, whole
from slumpcone.units.quantity import Quantity


def _truck_from_row(row: sqlite3.Row) -> Truck:
    return Truck(
        code=str(row["code"]),
        drum_volume=Quantity(float(row["drum_volume_yd3"]), "yd3"),
        fleet=text(row["fleet"]),
        last_uniformity_test=(day(row["last_uniformity_test"])),
        uniformity_test_days=int(row["uniformity_test_days"]),
        notes=str(row["notes"]),
    )


def _addition_from_row(row: sqlite3.Row) -> WaterAddition:
    return WaterAddition(
        ticket_number=str(row["ticket_number"]),
        added_at=datetime.fromisoformat(str(row["added_at"])),
        amount=Quantity(float(row["amount_gal"]), "gal"),
        requested_by=RequestedBy(str(row["requested_by"])),
        revolutions_after=int(row["revolutions_after"]),
        discharged_before=(quantity(row["discharged_before_yd3"], "yd3")),
    )


class DeliveryRepository:
    """Trucks, deliveries and jobsite water, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save_truck(self, truck: Truck) -> Truck:
        """Insert or update a truck by code."""
        self._db.execute(
            "INSERT INTO truck (code, drum_volume_yd3, fleet, last_uniformity_test, "
            "uniformity_test_days, notes) VALUES (:code, :drum, :fleet, :tested, "
            ":days, :notes) ON CONFLICT(code) DO UPDATE SET drum_volume_yd3 = :drum, "
            "fleet = :fleet, last_uniformity_test = :tested, "
            "uniformity_test_days = :days, notes = :notes",
            {
                "code": truck.code,
                "drum": truck.drum_volume.to("yd3").value,
                "fleet": truck.fleet,
                "tested": (
                    None
                    if truck.last_uniformity_test is None
                    else truck.last_uniformity_test.isoformat()
                ),
                "days": truck.uniformity_test_days,
                "notes": truck.notes,
            },
        )
        return truck

    def truck(self, code: str) -> Truck:
        """One truck by code."""
        key = normalize_code(code, field="truck_code")
        row = require_one(self._db, "SELECT * FROM truck WHERE code = ?", (key,), "truck", key)
        return _truck_from_row(row)

    def trucks(self) -> tuple[Truck, ...]:
        """Every truck, in code order."""
        rows = self._db.query("SELECT * FROM truck ORDER BY code")
        return tuple(_truck_from_row(row) for row in rows)

    def save(self, delivery: Delivery) -> Delivery:
        """Insert or update a delivery, replacing its water additions."""
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO delivery (ticket_number, truck_code, batched_at, "
                "left_plant_at, arrived_at, discharge_started_at, discharge_finished_at, "
                "revolutions_on_arrival, revolutions_at_discharge, returned_yd3, notes) "
                "VALUES (:ticket, :truck, :batched, :left, :arrived, :started, :finished, "
                ":rev_arrival, :rev_discharge, :returned, :notes) "
                "ON CONFLICT(ticket_number) DO UPDATE SET truck_code = :truck, "
                "batched_at = :batched, left_plant_at = :left, arrived_at = :arrived, "
                "discharge_started_at = :started, discharge_finished_at = :finished, "
                "revolutions_on_arrival = :rev_arrival, "
                "revolutions_at_discharge = :rev_discharge, returned_yd3 = :returned, "
                "notes = :notes",
                {
                    "ticket": delivery.ticket_number,
                    "truck": delivery.truck_code,
                    "batched": delivery.batched_at.isoformat(),
                    "left": (
                        None
                        if delivery.left_plant_at is None
                        else delivery.left_plant_at.isoformat()
                    ),
                    "arrived": (
                        None if delivery.arrived_at is None else delivery.arrived_at.isoformat()
                    ),
                    "started": (
                        None
                        if delivery.discharge_started_at is None
                        else delivery.discharge_started_at.isoformat()
                    ),
                    "finished": (
                        None
                        if delivery.discharge_finished_at is None
                        else delivery.discharge_finished_at.isoformat()
                    ),
                    "rev_arrival": delivery.revolutions_on_arrival,
                    "rev_discharge": delivery.revolutions_at_discharge,
                    "returned": (
                        None
                        if delivery.returned_volume is None
                        else delivery.returned_volume.to("yd3").value
                    ),
                    "notes": delivery.notes,
                },
            )
            self._db.execute(
                "DELETE FROM water_addition WHERE ticket_number = ?", (delivery.ticket_number,)
            )
            for position, addition in enumerate(delivery.water_additions):
                self._db.execute(
                    "INSERT INTO water_addition (ticket_number, position, added_at, "
                    "amount_gal, requested_by, revolutions_after, discharged_before_yd3) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        delivery.ticket_number,
                        position,
                        addition.added_at.isoformat(),
                        addition.amount.to("gal").value,
                        addition.requested_by.value,
                        addition.revolutions_after,
                        (
                            None
                            if addition.discharged_before is None
                            else addition.discharged_before.to("yd3").value
                        ),
                    ),
                )
        return delivery

    def _from_row(self, row: sqlite3.Row) -> Delivery:
        ticket = str(row["ticket_number"])
        additions = self._db.query(
            "SELECT * FROM water_addition WHERE ticket_number = ? ORDER BY position", (ticket,)
        )
        return Delivery(
            ticket_number=ticket,
            truck_code=str(row["truck_code"]),
            batched_at=datetime.fromisoformat(str(row["batched_at"])),
            left_plant_at=moment(row["left_plant_at"]),
            arrived_at=moment(row["arrived_at"]),
            discharge_started_at=moment(row["discharge_started_at"]),
            discharge_finished_at=moment(row["discharge_finished_at"]),
            revolutions_on_arrival=(whole(row["revolutions_on_arrival"])),
            revolutions_at_discharge=(whole(row["revolutions_at_discharge"])),
            water_additions=tuple(_addition_from_row(entry) for entry in additions),
            returned_volume=(quantity(row["returned_yd3"], "yd3")),
            notes=str(row["notes"]),
        )

    def get(self, ticket_number: str) -> Delivery:
        """One delivery by ticket number."""
        key = normalize_ticket_number(ticket_number)
        row = require_one(
            self._db, "SELECT * FROM delivery WHERE ticket_number = ?", (key,), "delivery", key
        )
        return self._from_row(row)

    def between(self, start: date, end: date) -> tuple[Delivery, ...]:
        """Every delivery batched in a window, oldest first."""
        rows = self._db.query(
            "SELECT * FROM delivery WHERE batched_at >= ? AND batched_at < ? "
            "ORDER BY batched_at, ticket_number",
            day_range(start, end),
        )
        return tuple(self._from_row(row) for row in rows)

    def for_truck(self, truck_code: str, start: date, end: date) -> tuple[Delivery, ...]:
        """Every delivery one truck made in a window."""
        key = normalize_code(truck_code, field="truck_code")
        return tuple(d for d in self.between(start, end) if d.truck_code == key)

    def unfinished(self, start: date, end: date) -> tuple[Delivery, ...]:
        """Loads in a window that never recorded the end of discharge."""
        return tuple(d for d in self.between(start, end) if not d.is_complete)

    def delete(self, ticket_number: str) -> None:
        """Remove a delivery and its water additions."""
        key = normalize_ticket_number(ticket_number)
        cursor = self._db.execute("DELETE FROM delivery WHERE ticket_number = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("delivery", key)
