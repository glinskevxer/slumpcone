"""Reading and writing the price list.

Amounts are stored as text rather than as a real. A price of $142.00 stored in
a REAL column comes back as 142.00000000000003 often enough that a monthly
total is out by a cent, and a cent in a cost report is the thing an accountant
opens a ticket about. SQLite has no decimal type, so the text is the decimal.

Prices are never updated in place. A new price is a new row with a new window,
because last month's production has to keep costing what it cost.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.money import Money
from slumpcone.pricing import MaterialPrice, PriceList
from slumpcone.store.db import Database
from slumpcone.store.rows import day
from slumpcone.units.quantity import Quantity


def _from_row(row: sqlite3.Row) -> MaterialPrice:
    return MaterialPrice(
        material_code=str(row["material_code"]),
        price=Money(Decimal(str(row["amount"])), str(row["currency"])),
        per=Quantity(float(row["per_value"]), str(row["per_unit"])),
        effective_from=day(row["effective_from"]),
        effective_to=day(row["effective_to"]),
    )


class PricingRepository:
    """Material prices, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, price: MaterialPrice) -> MaterialPrice:
        """File a price. Refuses a second one starting on the same day."""
        existing = self._db.query_one(
            "SELECT 1 FROM material_price WHERE material_code = ? AND currency = ? "
            "AND effective_from IS ?",
            (
                price.material_code,
                price.price.currency,
                None if price.effective_from is None else price.effective_from.isoformat(),
            ),
        )
        if existing is not None:
            starting = (
                "with no start date"
                if price.effective_from is None
                else f"starting {price.effective_from.isoformat()}"
            )
            raise ConflictError("price", f"{price.material_code} {starting}")
        self._db.execute(
            "INSERT INTO material_price (material_code, currency, amount, per_value, "
            "per_unit, effective_from, effective_to) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                price.material_code,
                price.price.currency,
                str(price.price.amount),
                price.per.value,
                price.per.unit,
                None if price.effective_from is None else price.effective_from.isoformat(),
                None if price.effective_to is None else price.effective_to.isoformat(),
            ),
        )
        return price

    def save_all(self, prices: list[MaterialPrice]) -> None:
        """File several prices in one transaction."""
        with self._db.transaction():
            for price in prices:
                self.save(price)

    def for_material(self, material_code: str) -> tuple[MaterialPrice, ...]:
        """Every price on file for one material, oldest window first."""
        key = normalize_code(material_code, field="material_code")
        rows = self._db.query(
            "SELECT * FROM material_price WHERE material_code = ? "
            "ORDER BY effective_from IS NULL DESC, effective_from, id",
            (key,),
        )
        return tuple(_from_row(row) for row in rows)

    def current(self, material_code: str, on: date) -> MaterialPrice:
        """The price in force for one material on a day."""
        prices = self.for_material(material_code)
        if not prices:
            raise NotFoundError("price for", normalize_code(material_code))
        return PriceList(prices).for_material(material_code, on)

    def price_list(self) -> PriceList:
        """Everything on file, as a price list."""
        rows = self._db.query("SELECT * FROM material_price ORDER BY material_code, id")
        return PriceList(_from_row(row) for row in rows)

    def codes(self) -> tuple[str, ...]:
        """Every material with a price on file, sorted."""
        rows = self._db.query(
            "SELECT DISTINCT material_code FROM material_price ORDER BY material_code"
        )
        return tuple(str(row["material_code"]) for row in rows)

    def close_out(self, material_code: str, on: date) -> int:
        """End every open window for a material on a day.

        Used when a new price starts: the old one stops being in force rather
        than being deleted, so a report run over last month still finds it.
        """
        key = normalize_code(material_code, field="material_code")
        cursor = self._db.execute(
            "UPDATE material_price SET effective_to = ? WHERE material_code = ? "
            "AND effective_to IS NULL",
            (on.isoformat(), key),
        )
        return int(cursor.rowcount)

    def delete_for(self, material_code: str) -> int:
        """Remove every price for a material, returning how many went."""
        key = normalize_code(material_code, field="material_code")
        cursor = self._db.execute("DELETE FROM material_price WHERE material_code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("price for", key)
        return int(cursor.rowcount)
