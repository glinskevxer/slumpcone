"""Reading and writing invoices.

An invoice is written whole every time, lines and all. They are small, they are
edited only while they are a draft, and diffing four lines against four lines to
save three writes is a trade nobody wants when the alternative can leave a line
from a previous version behind.

The one thing the repository will not do is change an invoice that has taken
money. That rule lives on the record rather than here, and the save simply
refuses to write over a status the record would not have allowed.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from slumpcone.errors import NotFoundError, RuleViolationError
from slumpcone.identity import normalize_code
from slumpcone.money import Money
from slumpcone.percent import Percent
from slumpcone.sales.account import PaymentTerms
from slumpcone.sales.charges import AppliedCharge, ChargeKind
from slumpcone.sales.invoice import Invoice, InvoiceLine, InvoiceStatus, Payment
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range, text
from slumpcone.units.quantity import Quantity


def _money(amount: object, currency: str) -> Money:
    return Money(Decimal(str(amount)), currency)


class InvoiceRepository:
    """Invoices, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, invoice: Invoice) -> Invoice:
        """Write an invoice whole, refusing to overwrite one that took money."""
        existing = self._db.query_one(
            "SELECT status FROM invoice WHERE number = ?", (invoice.number,)
        )
        if existing is not None:
            standing = InvoiceStatus(str(existing["status"]))
            paid = self._db.scalar(
                "SELECT count(*) FROM invoice_payment WHERE invoice_number = ?",
                (invoice.number,),
            )
            if standing is InvoiceStatus.VOID or (paid and not invoice.payments):
                raise RuleViolationError(
                    "INVOICE_SETTLED",
                    f"{invoice.number} is {standing} on file and cannot be rewritten",
                )
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO invoice (number, account_code, invoiced_on, terms_days, "
                "discount_days, discount_percent, tax_percent, project, status, "
                "currency, notes) VALUES (:number, :account, :invoiced, :days, :ddays, "
                ":dpct, :tax, :project, :status, :currency, :notes) "
                "ON CONFLICT(number) DO UPDATE SET account_code = :account, "
                "invoiced_on = :invoiced, terms_days = :days, discount_days = :ddays, "
                "discount_percent = :dpct, tax_percent = :tax, project = :project, "
                "status = :status, currency = :currency, notes = :notes",
                {
                    "number": invoice.number,
                    "account": invoice.account_code,
                    "invoiced": invoice.invoiced_on.isoformat(),
                    "days": invoice.terms.days,
                    "ddays": invoice.terms.discount_days,
                    "dpct": invoice.terms.discount_percent,
                    "tax": invoice.tax.value,
                    "project": invoice.project,
                    "status": invoice.status.value,
                    "currency": invoice.currency,
                    "notes": invoice.notes,
                },
            )
            for table in ("invoice_line", "invoice_charge", "invoice_payment"):
                self._db.execute(
                    f"DELETE FROM {table} WHERE invoice_number = ?", (invoice.number,)
                )
            for position, line in enumerate(invoice.lines):
                self._db.execute(
                    "INSERT INTO invoice_line (invoice_number, position, ticket_number, "
                    "mix_code, volume_yd3, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        invoice.number,
                        position,
                        line.ticket_number,
                        line.mix_code,
                        line.volume.to("yd3").value,
                        str(line.unit_price.amount),
                    ),
                )
            for position, charge in enumerate(invoice.charges):
                self._db.execute(
                    "INSERT INTO invoice_charge (invoice_number, position, kind, "
                    "quantity, amount, reason) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        invoice.number,
                        position,
                        charge.kind.value,
                        charge.quantity,
                        str(charge.amount.amount),
                        charge.reason,
                    ),
                )
            for position, payment in enumerate(invoice.payments):
                self._db.execute(
                    "INSERT INTO invoice_payment (invoice_number, position, received_on, "
                    "amount, reference) VALUES (?, ?, ?, ?, ?)",
                    (
                        invoice.number,
                        position,
                        payment.received_on.isoformat(),
                        str(payment.amount.amount),
                        payment.reference,
                    ),
                )
        return invoice

    def _from_row(self, row: sqlite3.Row) -> Invoice:
        number = str(row["number"])
        currency = str(row["currency"])
        lines = self._db.query(
            "SELECT * FROM invoice_line WHERE invoice_number = ? ORDER BY position",
            (number,),
        )
        charges = self._db.query(
            "SELECT * FROM invoice_charge WHERE invoice_number = ? ORDER BY position",
            (number,),
        )
        payments = self._db.query(
            "SELECT * FROM invoice_payment WHERE invoice_number = ? ORDER BY position",
            (number,),
        )
        return Invoice(
            number=number,
            account_code=str(row["account_code"]),
            invoiced_on=date.fromisoformat(str(row["invoiced_on"])),
            lines=tuple(
                InvoiceLine(
                    str(line["ticket_number"]),
                    str(line["mix_code"]),
                    Quantity(float(line["volume_yd3"]), "yd3"),
                    _money(line["unit_price"], currency),
                )
                for line in lines
            ),
            charges=tuple(
                AppliedCharge(
                    ChargeKind(str(charge["kind"])),
                    float(charge["quantity"]),
                    _money(charge["amount"], currency),
                    str(charge["reason"]),
                )
                for charge in charges
            ),
            payments=tuple(
                Payment(
                    date.fromisoformat(str(payment["received_on"])),
                    _money(payment["amount"], currency),
                    text(payment["reference"]),
                )
                for payment in payments
            ),
            terms=PaymentTerms(
                int(row["terms_days"]),
                int(row["discount_days"]),
                float(row["discount_percent"]),
            ),
            tax=Percent(float(row["tax_percent"])),
            project=text(row["project"]),
            status=InvoiceStatus(str(row["status"])),
            currency=currency,
            notes=str(row["notes"]),
        )

    def get(self, number: str) -> Invoice:
        """One invoice by number."""
        key = normalize_code(number, field="invoice_number")
        row = self._db.query_one("SELECT * FROM invoice WHERE number = ?", (key,))
        if row is None:
            raise NotFoundError("invoice", key)
        return self._from_row(row)

    def for_account(self, account_code: str) -> tuple[Invoice, ...]:
        """Every invoice for one account, oldest first."""
        key = normalize_code(account_code, field="account_code")
        rows = self._db.query(
            "SELECT * FROM invoice WHERE account_code = ? ORDER BY invoiced_on, number",
            (key,),
        )
        return tuple(self._from_row(row) for row in rows)

    def between(self, start: date, end: date) -> tuple[Invoice, ...]:
        """Every invoice raised in a window, oldest first."""
        rows = self._db.query(
            "SELECT * FROM invoice WHERE invoiced_on >= ? AND invoiced_on < ? "
            "ORDER BY invoiced_on, number",
            day_range(start, end),
        )
        return tuple(self._from_row(row) for row in rows)

    def owed(self) -> tuple[Invoice, ...]:
        """Every invoice still expecting money, oldest first."""
        rows = self._db.query(
            "SELECT * FROM invoice WHERE status IN ('issued', 'part_paid') "
            "ORDER BY invoiced_on, number"
        )
        return tuple(self._from_row(row) for row in rows)

    def for_ticket(self, ticket_number: str) -> Invoice | None:
        """The invoice one ticket was billed on, if it has been."""
        row = self._db.query_one(
            "SELECT invoice_number FROM invoice_line WHERE ticket_number = ? LIMIT 1",
            (ticket_number.strip(),),
        )
        return None if row is None else self.get(str(row["invoice_number"]))

    def unbilled_tickets(self, start: date, end: date) -> tuple[str, ...]:
        """Tickets in a window that no invoice has picked up yet."""
        rows = self._db.query(
            "SELECT t.number FROM batch_ticket t LEFT JOIN invoice_line l "
            "ON l.ticket_number = t.number WHERE l.ticket_number IS NULL "
            "AND t.batched_at >= ? AND t.batched_at < ? ORDER BY t.batched_at, t.number",
            day_range(start, end),
        )
        return tuple(str(row["number"]) for row in rows)

    def delete(self, number: str) -> None:
        """Remove a draft invoice and everything on it."""
        key = normalize_code(number, field="invoice_number")
        invoice = self.get(key)
        if invoice.status is not InvoiceStatus.DRAFT:
            raise RuleViolationError(
                "INVOICE_NOT_A_DRAFT",
                f"{key} is {invoice.status} and can be voided but not deleted",
            )
        self._db.execute("DELETE FROM invoice WHERE number = ?", (key,))
