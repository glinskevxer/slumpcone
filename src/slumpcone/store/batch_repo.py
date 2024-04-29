"""Reading and writing delivery tickets.

Tickets are append only in practice: a plant that reprints a ticket gets the
same serial number and the same content, and a plant that needs to change one
voids it and issues another. The repository enforces that by refusing a second
save under the same number rather than quietly updating.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from slumpcone.batching.ticket import BatchTicket, TicketAdmixture, TicketLine
from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code, normalize_ticket_number
from slumpcone.materials.kinds import MaterialClass
from slumpcone.store.db import Database
from slumpcone.units.quantity import Quantity


def _line_from_row(row: sqlite3.Row) -> TicketLine:
    return TicketLine(
        str(row["material_code"]),
        MaterialClass(str(row["material_class"])),
        Quantity(float(row["required_lb"]), "lb"),
        Quantity(float(row["actual_lb"]), "lb"),
        Quantity(float(row["allowance_lb"]), "lb"),
    )


def _admixture_from_row(row: sqlite3.Row) -> TicketAdmixture:
    return TicketAdmixture(
        str(row["material_code"]),
        Quantity(float(row["called_floz"]), "floz"),
        Quantity(float(row["dispensed_floz"]), "floz"),
    )


class BatchRepository:
    """Delivery tickets, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, ticket: BatchTicket) -> BatchTicket:
        """File a ticket. Refuses a serial number that is already on file."""
        existing = self._db.query_one(
            "SELECT 1 FROM batch_ticket WHERE number = ?", (ticket.number,)
        )
        if existing is not None:
            raise ConflictError("ticket", ticket.number)
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO batch_ticket (number, plant_code, mix_code, mix_revision, "
                "batched_at, volume_yd3, truck_code, purchaser, project, cumulative_yd3, "
                "revolution_counter, water_held_back_lb, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticket.number,
                    ticket.plant_code,
                    ticket.mix_code,
                    ticket.mix_revision,
                    ticket.batched_at.isoformat(),
                    ticket.volume.to("yd3").value,
                    ticket.truck_code,
                    ticket.purchaser,
                    ticket.project,
                    None
                    if ticket.cumulative_volume is None
                    else ticket.cumulative_volume.to("yd3").value,
                    ticket.revolution_counter,
                    None
                    if ticket.water_held_back is None
                    else ticket.water_held_back.to("lb").value,
                    ticket.notes,
                ),
            )
            for position, line in enumerate(ticket.lines):
                self._db.execute(
                    "INSERT INTO batch_ticket_line (ticket_number, position, material_code, "
                    "material_class, required_lb, actual_lb, allowance_lb) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        ticket.number,
                        position,
                        line.material_code,
                        line.material_class.value,
                        line.required.to("lb").value,
                        line.actual.to("lb").value,
                        line.allowance.to("lb").value,
                    ),
                )
            for position, dose in enumerate(ticket.admixtures):
                self._db.execute(
                    "INSERT INTO batch_ticket_admixture (ticket_number, position, "
                    "material_code, called_floz, dispensed_floz) VALUES (?, ?, ?, ?, ?)",
                    (
                        ticket.number,
                        position,
                        dose.material_code,
                        dose.called_for.to("floz").value,
                        dose.dispensed.to("floz").value,
                    ),
                )
        return ticket

    def _from_row(self, row: sqlite3.Row) -> BatchTicket:
        number = str(row["number"])
        lines = self._db.query(
            "SELECT * FROM batch_ticket_line WHERE ticket_number = ? ORDER BY position",
            (number,),
        )
        doses = self._db.query(
            "SELECT * FROM batch_ticket_admixture WHERE ticket_number = ? ORDER BY position",
            (number,),
        )
        return BatchTicket(
            number=number,
            plant_code=str(row["plant_code"]),
            mix_code=str(row["mix_code"]),
            mix_revision=int(row["mix_revision"]),
            batched_at=datetime.fromisoformat(str(row["batched_at"])),
            volume=Quantity(float(row["volume_yd3"]), "yd3"),
            lines=tuple(_line_from_row(line) for line in lines),
            admixtures=tuple(_admixture_from_row(dose) for dose in doses),
            truck_code=None if row["truck_code"] is None else str(row["truck_code"]),
            purchaser=None if row["purchaser"] is None else str(row["purchaser"]),
            project=None if row["project"] is None else str(row["project"]),
            cumulative_volume=(
                None
                if row["cumulative_yd3"] is None
                else Quantity(float(row["cumulative_yd3"]), "yd3")
            ),
            revolution_counter=(
                None if row["revolution_counter"] is None else int(row["revolution_counter"])
            ),
            water_held_back=(
                None
                if row["water_held_back_lb"] is None
                else Quantity(float(row["water_held_back_lb"]), "lb")
            ),
            notes=str(row["notes"]),
        )

    def get(self, number: str) -> BatchTicket:
        """One ticket by serial number."""
        key = normalize_ticket_number(number)
        row = self._db.query_one("SELECT * FROM batch_ticket WHERE number = ?", (key,))
        if row is None:
            raise NotFoundError("ticket", key)
        return self._from_row(row)

    def between(self, start: date, end: date) -> tuple[BatchTicket, ...]:
        """Every ticket batched on or between two dates, oldest first."""
        rows = self._db.query(
            "SELECT * FROM batch_ticket WHERE batched_at >= ? AND batched_at < ? "
            "ORDER BY batched_at, number",
            (start.isoformat(), f"{end.isoformat()}T23:59:59.999999"),
        )
        return tuple(self._from_row(row) for row in rows)

    def for_plant(self, plant_code: str, start: date, end: date) -> tuple[BatchTicket, ...]:
        """Every ticket one plant wrote in a window."""
        key = normalize_code(plant_code, field="plant_code")
        return tuple(t for t in self.between(start, end) if t.plant_code == key)

    def for_mix(self, mix_code: str) -> tuple[BatchTicket, ...]:
        """Every ticket written against one mix design, oldest first."""
        key = normalize_code(mix_code, field="mix_code")
        rows = self._db.query(
            "SELECT * FROM batch_ticket WHERE mix_code = ? ORDER BY batched_at, number", (key,)
        )
        return tuple(self._from_row(row) for row in rows)

    def for_project(self, project: str) -> tuple[BatchTicket, ...]:
        """Every ticket written against one job, oldest first."""
        rows = self._db.query(
            "SELECT * FROM batch_ticket WHERE project = ? ORDER BY batched_at, number",
            (project,),
        )
        return tuple(self._from_row(row) for row in rows)

    def count(self) -> int:
        """How many tickets are on file."""
        return int(self._db.scalar("SELECT count(*) FROM batch_ticket") or 0)

    def delete(self, number: str) -> None:
        """Remove a ticket and its lines. Used only to void a misprint."""
        key = normalize_ticket_number(number)
        cursor = self._db.execute("DELETE FROM batch_ticket WHERE number = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("ticket", key)
