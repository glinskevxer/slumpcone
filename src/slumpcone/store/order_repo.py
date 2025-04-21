"""Reading and writing orders, and adding tickets up against them.

The progress figure is computed on read rather than kept on the order. A
running total maintained as tickets land is one write away from being wrong
forever, and the ticket table already knows the answer.
"""

from __future__ import annotations

import sqlite3
from datetime import date, time

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.project.order import Order, OrderProgress, OrderStatus, progress_of
from slumpcone.store.batch_repo import BatchRepository
from slumpcone.store.db import Database
from slumpcone.store.guards import require_one
from slumpcone.store.rows import quantity, text
from slumpcone.units.quantity import Quantity


def _from_row(row: sqlite3.Row) -> Order:
    return Order(
        number=str(row["number"]),
        project_code=str(row["project_code"]),
        class_code=str(row["class_code"]),
        volume=Quantity(float(row["volume_yd3"]), "yd3"),
        placement_date=date.fromisoformat(str(row["placement_date"])),
        mix_code=text(row["mix_code"]),
        start_time=(
            None if row["start_time"] is None else time.fromisoformat(str(row["start_time"]))
        ),
        rate=quantity(row["rate_yd3"], "yd3"),
        placement=text(row["placement"]),
        status=OrderStatus(str(row["status"])),
        notes=str(row["notes"]),
    )


class OrderRepository:
    """Orders, on disk, with their progress computed from the tickets."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._batches = BatchRepository(database)

    def save(self, order: Order) -> Order:
        """Insert or update an order by number."""
        self._db.execute(
            "INSERT INTO concrete_order (number, project_code, class_code, volume_yd3, "
            "placement_date, mix_code, start_time, rate_yd3, placement, status, notes) "
            "VALUES (:number, :project, :class_code, :volume, :placed, :mix, :start, "
            ":rate, :where, :status, :notes) ON CONFLICT(number) DO UPDATE SET "
            "project_code = :project, class_code = :class_code, volume_yd3 = :volume, "
            "placement_date = :placed, mix_code = :mix, start_time = :start, "
            "rate_yd3 = :rate, placement = :where, status = :status, notes = :notes",
            {
                "number": order.number,
                "project": order.project_code,
                "class_code": order.class_code,
                "volume": order.volume.to("yd3").value,
                "placed": order.placement_date.isoformat(),
                "mix": order.mix_code,
                "start": None if order.start_time is None else order.start_time.isoformat(),
                "rate": None if order.rate is None else order.rate.to("yd3").value,
                "where": order.placement,
                "status": order.status.value,
                "notes": order.notes,
            },
        )
        return order

    def get(self, number: str) -> Order:
        """One order by number."""
        key = normalize_code(number, field="order_number")
        row = require_one(
            self._db, "SELECT * FROM concrete_order WHERE number = ?", (key,), "order", key
        )
        return _from_row(row)

    def for_project(self, project_code: str) -> tuple[Order, ...]:
        """Every order on one job, earliest placement first."""
        key = normalize_code(project_code, field="project_code")
        rows = self._db.query(
            "SELECT * FROM concrete_order WHERE project_code = ? "
            "ORDER BY placement_date, number",
            (key,),
        )
        return tuple(_from_row(row) for row in rows)

    def on_date(self, placement_date: date) -> tuple[Order, ...]:
        """Every order booked for one day, in number order."""
        rows = self._db.query(
            "SELECT * FROM concrete_order WHERE placement_date = ? ORDER BY number",
            (placement_date.isoformat(),),
        )
        return tuple(_from_row(row) for row in rows)

    def open_orders(self, on: date) -> tuple[Order, ...]:
        """Orders for a day that a plant may still batch against."""
        return tuple(order for order in self.on_date(on) if order.status.accepts_loads)

    def progress(self, number: str) -> OrderProgress:
        """One order against the tickets written on it."""
        order = self.get(number)
        tickets = [
            ticket
            for ticket in self._batches.for_project(order.placement or "")
            if ticket.mix_code == order.mix_code
        ]
        if order.placement is None:
            tickets = []
        return progress_of(order, [ticket.volume for ticket in tickets])

    def progress_from_tickets(self, number: str, ticket_numbers: list[str]) -> OrderProgress:
        """One order against a named list of tickets.

        Used where the tie between order and ticket is recorded elsewhere,
        which on most plants means the dispatch system rather than this one.
        """
        order = self.get(number)
        volumes = [self._batches.get(ticket).volume for ticket in ticket_numbers]
        return progress_of(order, volumes)

    def delete(self, number: str) -> None:
        """Remove an order."""
        key = normalize_code(number, field="order_number")
        cursor = self._db.execute("DELETE FROM concrete_order WHERE number = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("order", key)
