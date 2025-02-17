"""Reading and writing receipts and inventory movements.

The ledger is loaded per plant rather than whole. A plant's own movements are a
few thousand rows a year, which is nothing; every plant's movements together
over the life of the register is a table nobody wants in memory to answer "how
much cement is in silo one".
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.plant.inventory import InventoryLedger, Movement, MovementKind
from slumpcone.plant.receipt import Receipt
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range, percent, text
from slumpcone.units.quantity import Quantity


def _receipt_from_row(row: sqlite3.Row) -> Receipt:
    return Receipt(
        reference=str(row["reference"]),
        plant_code=str(row["plant_code"]),
        silo_code=str(row["silo_code"]),
        material_code=str(row["material_code"]),
        received_at=datetime.fromisoformat(str(row["received_at"])),
        quantity=Quantity(float(row["quantity_lb"]), "lb"),
        supplier=text(row["supplier"]),
        supplier_ticket=(text(row["supplier_ticket"])),
        certificate_reference=(text(row["certificate_reference"])),
        moisture=percent(row["moisture_pct"]),
        notes=str(row["notes"]),
    )


def _movement_from_row(row: sqlite3.Row) -> Movement:
    kind = MovementKind(str(row["kind"]))
    stored = float(row["quantity_lb"])
    magnitude = stored if kind.is_signed else abs(stored)
    return Movement(
        plant_code=str(row["plant_code"]),
        silo_code=str(row["silo_code"]),
        material_code=str(row["material_code"]),
        at=datetime.fromisoformat(str(row["at"])),
        kind=kind,
        quantity=Quantity(magnitude, "lb"),
        reference=text(row["reference"]),
        notes=str(row["notes"]),
    )


class InventoryRepository:
    """Receipts and movements, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save_receipt(self, receipt: Receipt) -> Receipt:
        """File a receipt. Refuses a reference that is already on file."""
        if self._db.query_one(
            "SELECT 1 FROM material_receipt WHERE reference = ?", (receipt.reference,)
        ):
            raise ConflictError("receipt", receipt.reference)
        self._db.execute(
            "INSERT INTO material_receipt (reference, plant_code, silo_code, material_code, "
            "received_at, quantity_lb, supplier, supplier_ticket, certificate_reference, "
            "moisture_pct, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt.reference,
                receipt.plant_code,
                receipt.silo_code,
                receipt.material_code,
                receipt.received_at.isoformat(),
                receipt.quantity.to("lb").value,
                receipt.supplier,
                receipt.supplier_ticket,
                receipt.certificate_reference,
                None if receipt.moisture is None else receipt.moisture.value,
                receipt.notes,
            ),
        )
        return receipt

    def receipt(self, reference: str) -> Receipt:
        """One receipt by reference."""
        key = normalize_code(reference, field="receipt_reference")
        row = self._db.query_one("SELECT * FROM material_receipt WHERE reference = ?", (key,))
        if row is None:
            raise NotFoundError("receipt", key)
        return _receipt_from_row(row)

    def receipts_between(self, plant_code: str, start: date, end: date) -> tuple[Receipt, ...]:
        """Every receipt at one plant in a window, oldest first."""
        key = normalize_code(plant_code, field="plant_code")
        rows = self._db.query(
            "SELECT * FROM material_receipt WHERE plant_code = ? AND received_at >= ? "
            "AND received_at < ? ORDER BY received_at, reference",
            (key, *day_range(start, end)),
        )
        return tuple(_receipt_from_row(row) for row in rows)

    def receipts_of(self, material_code: str) -> tuple[Receipt, ...]:
        """Every receipt of one material, oldest first."""
        key = normalize_code(material_code, field="material_code")
        rows = self._db.query(
            "SELECT * FROM material_receipt WHERE material_code = ? "
            "ORDER BY received_at, reference",
            (key,),
        )
        return tuple(_receipt_from_row(row) for row in rows)

    def record(self, movement: Movement) -> Movement:
        """Add one movement to the ledger."""
        self._db.execute(
            "INSERT INTO inventory_movement (plant_code, silo_code, material_code, at, "
            "kind, quantity_lb, reference, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                movement.plant_code,
                movement.silo_code,
                movement.material_code,
                movement.at.isoformat(),
                movement.kind.value,
                movement.quantity.to("lb").value,
                movement.reference,
                movement.notes,
            ),
        )
        return movement

    def record_all(self, movements: list[Movement]) -> None:
        """Add several movements in one transaction."""
        with self._db.transaction():
            for movement in movements:
                self.record(movement)

    def ledger(self, plant_code: str) -> InventoryLedger:
        """Every movement at one plant, as a ledger."""
        key = normalize_code(plant_code, field="plant_code")
        rows = self._db.query(
            "SELECT * FROM inventory_movement WHERE plant_code = ? ORDER BY at, silo_code, id",
            (key,),
        )
        return InventoryLedger(_movement_from_row(row) for row in rows)

    def balance(self, plant_code: str, silo_code: str) -> Quantity:
        """What the ledger says is in one vessel."""
        return self.ledger(plant_code).balance(silo_code)

    def movements_between(
        self, plant_code: str, start: date, end: date
    ) -> tuple[Movement, ...]:
        """Every movement at one plant in a window, oldest first."""
        key = normalize_code(plant_code, field="plant_code")
        rows = self._db.query(
            "SELECT * FROM inventory_movement WHERE plant_code = ? AND at >= ? AND at < ? "
            "ORDER BY at, silo_code, id",
            (key, *day_range(start, end)),
        )
        return tuple(_movement_from_row(row) for row in rows)

    def receipt_movement(self, receipt: Receipt) -> Movement:
        """The ledger line a receipt produces."""
        return Movement(
            receipt.plant_code,
            receipt.silo_code,
            receipt.material_code,
            receipt.received_at,
            MovementKind.RECEIPT,
            receipt.quantity,
            reference=receipt.reference,
        )

    def post_receipt(self, receipt: Receipt) -> Movement:
        """File a receipt and its ledger line together."""
        with self._db.transaction():
            self.save_receipt(receipt)
            return self.record(self.receipt_movement(receipt))
