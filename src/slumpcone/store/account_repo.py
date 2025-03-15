"""Reading and writing accounts and the prices they were quoted.

A quote is per account and per mixture, with a window, exactly like a material
price. That is not a coincidence: both answer "what did this cost on that day",
and both have to keep answering it correctly after the number changes.

The account balance is not stored here. It is the sum of what has been
delivered and not paid for, which belongs wherever the invoices are, and a
balance kept as a column is a balance that drifts.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.money import Money
from slumpcone.sales.account import Account, AccountStatus, PaymentTerms
from slumpcone.store.db import Database
from slumpcone.store.rows import day, text


def _from_row(row: sqlite3.Row) -> Account:
    currency = row["credit_currency"]
    limit = row["credit_limit"]
    return Account(
        code=str(row["code"]),
        name=str(row["name"]),
        status=AccountStatus(str(row["status"])),
        terms=PaymentTerms(
            int(row["terms_days"]),
            int(row["discount_days"]),
            float(row["discount_percent"]),
        ),
        credit_limit=(None if limit is None else Money(Decimal(str(limit)), str(currency))),
        contact=text(row["contact"]),
        phone=text(row["phone"]),
        notes=str(row["notes"]),
    )


class AccountRepository:
    """Accounts and quotes, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, account: Account) -> Account:
        """Insert or update an account by code."""
        self._db.execute(
            "INSERT INTO account (code, name, status, terms_days, discount_days, "
            "discount_percent, credit_currency, credit_limit, contact, phone, notes) "
            "VALUES (:code, :name, :status, :days, :ddays, :dpct, :currency, :limit, "
            ":contact, :phone, :notes) ON CONFLICT(code) DO UPDATE SET name = :name, "
            "status = :status, terms_days = :days, discount_days = :ddays, "
            "discount_percent = :dpct, credit_currency = :currency, "
            "credit_limit = :limit, contact = :contact, phone = :phone, notes = :notes",
            {
                "code": account.code,
                "name": account.name,
                "status": account.status.value,
                "days": account.terms.days,
                "ddays": account.terms.discount_days,
                "dpct": account.terms.discount_percent,
                "currency": (
                    None if account.credit_limit is None else account.credit_limit.currency
                ),
                "limit": (
                    None if account.credit_limit is None else str(account.credit_limit.amount)
                ),
                "contact": account.contact,
                "phone": account.phone,
                "notes": account.notes,
            },
        )
        return account

    def get(self, code: str) -> Account:
        """One account by code."""
        key = normalize_code(code, field="account_code")
        row = self._db.query_one("SELECT * FROM account WHERE code = ?", (key,))
        if row is None:
            raise NotFoundError("account", key)
        return _from_row(row)

    def all(self) -> tuple[Account, ...]:
        """Every account, in code order."""
        rows = self._db.query("SELECT * FROM account ORDER BY code")
        return tuple(_from_row(row) for row in rows)

    def open_accounts(self) -> tuple[Account, ...]:
        """Every account the plant may still book work for."""
        return tuple(account for account in self.all() if account.status.takes_orders)

    def delete(self, code: str) -> None:
        """Remove an account and its quotes."""
        key = normalize_code(code, field="account_code")
        cursor = self._db.execute("DELETE FROM account WHERE code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("account", key)

    def quote(
        self,
        account_code: str,
        mix_code: str,
        price: Money,
        *,
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> Money:
        """File a price for one account and one mixture."""
        account = normalize_code(account_code, field="account_code")
        mix = normalize_code(mix_code, field="mix_code")
        self.get(account)
        start = None if effective_from is None else effective_from.isoformat()
        if self._db.query_one(
            "SELECT 1 FROM account_quote WHERE account_code = ? AND mix_code = ? "
            "AND effective_from IS ?",
            (account, mix, start),
        ):
            raise ConflictError("quote", f"{account} {mix} from {start or 'always'}")
        self._db.execute(
            "INSERT INTO account_quote (account_code, mix_code, currency, amount, "
            "effective_from, effective_to) VALUES (?, ?, ?, ?, ?, ?)",
            (
                account,
                mix,
                price.currency,
                str(price.amount),
                start,
                None if effective_to is None else effective_to.isoformat(),
            ),
        )
        return price

    def quoted_price(self, account_code: str, mix_code: str, on: date) -> Money:
        """What one account pays for one mixture on a day."""
        account = normalize_code(account_code, field="account_code")
        mix = normalize_code(mix_code, field="mix_code")
        rows = self._db.query(
            "SELECT * FROM account_quote WHERE account_code = ? AND mix_code = ? "
            "ORDER BY effective_from IS NULL DESC, effective_from",
            (account, mix),
        )

        def in_force(row: sqlite3.Row) -> bool:
            starts = day(row["effective_from"])
            ends = day(row["effective_to"])
            if starts is not None and starts > on:
                return False
            return not (ends is not None and ends < on)

        covering = [row for row in rows if in_force(row)]
        if not covering:
            raise NotFoundError("quote for", f"{account} {mix}")
        chosen = covering[-1]
        return Money(Decimal(str(chosen["amount"])), str(chosen["currency"]))

    def quotes_for(self, account_code: str) -> tuple[tuple[str, Money], ...]:
        """Every quote on file for one account, by mixture."""
        account = normalize_code(account_code, field="account_code")
        rows = self._db.query(
            "SELECT * FROM account_quote WHERE account_code = ? ORDER BY mix_code, "
            "effective_from IS NULL DESC, effective_from",
            (account,),
        )
        return tuple(
            (str(row["mix_code"]), Money(Decimal(str(row["amount"])), str(row["currency"])))
            for row in rows
        )
