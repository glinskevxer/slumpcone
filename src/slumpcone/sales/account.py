"""Customer accounts, and the two things that stop a load leaving.

A plant refuses a load for two commercial reasons and they are not the same.
An account on hold is a decision somebody made, and a dispatcher cannot
override it. An account over its credit limit is arithmetic, and it changes
every time a ticket is written, so the same account can be fine at eight and
over at eleven without anybody doing anything.

Terms are stored as the days rather than as a phrase. "Net 30", "30 days" and
"payable within one month" are the same term written three ways, and a plant
with three spellings of one term cannot age its own debt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.money import Money


class AccountStatus(Enum):
    """Where an account stands."""

    OPEN = "open"
    ON_HOLD = "on_hold"
    CASH_ONLY = "cash_only"
    CLOSED = "closed"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> AccountStatus:
        """Read a status off an account record."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown account status {text!r}", field="status")

    @property
    def takes_orders(self) -> bool:
        """True when the plant may book work for this account at all."""
        return self in {AccountStatus.OPEN, AccountStatus.CASH_ONLY}

    @property
    def needs_payment_first(self) -> bool:
        """True when the load is paid for before it leaves."""
        return self is AccountStatus.CASH_ONLY


@dataclass(frozen=True, slots=True)
class PaymentTerms:
    """When an invoice falls due, and what a prompt payment is worth."""

    days: int = 30
    discount_days: int = 0
    discount_percent: float = 0.0

    def __post_init__(self) -> None:
        if self.days < 0:
            raise ValidationError("payment terms cannot be negative", field="days")
        if self.discount_days < 0:
            raise ValidationError("a discount window cannot be negative", field="discount_days")
        if self.discount_days > self.days:
            raise ValidationError(
                "a discount window cannot outlast the term itself", field="discount_days"
            )
        if not 0.0 <= self.discount_percent < 100.0:
            raise ValidationError(
                "a discount is a share of the invoice", field="discount_percent"
            )

    @property
    def is_on_delivery(self) -> bool:
        """True when there is no credit at all."""
        return self.days == 0

    @property
    def has_discount(self) -> bool:
        """True when paying early is worth something."""
        return self.discount_days > 0 and self.discount_percent > 0.0

    def due_on(self, invoiced: date) -> date:
        """When an invoice raised on a day falls due."""
        return invoiced + timedelta(days=self.days)

    def discount_until(self, invoiced: date) -> date | None:
        """The last day a discount may be taken, if there is one."""
        if not self.has_discount:
            return None
        return invoiced + timedelta(days=self.discount_days)

    def discount_on(self, amount: Money, paid: date, invoiced: date) -> Money:
        """What a payment on a day earns off an invoice."""
        until = self.discount_until(invoiced)
        if until is None or paid > until:
            return Money.zero(amount.currency)
        return amount * (self.discount_percent / 100.0)

    def describe(self) -> str:
        """The term as a plant writes it."""
        if self.is_on_delivery:
            return "cash on delivery"
        if self.has_discount:
            return f"{self.discount_percent:g}/{self.discount_days} net {self.days}"
        return f"net {self.days}"


@dataclass(frozen=True, slots=True)
class Account:
    """One customer."""

    code: str
    name: str
    status: AccountStatus = AccountStatus.OPEN
    terms: PaymentTerms = PaymentTerms()
    credit_limit: Money | None = None
    contact: str | None = None
    phone: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="account_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="account_name"))
        if self.contact is not None:
            object.__setattr__(self, "contact", normalize_name(self.contact, field="contact"))
        if self.credit_limit is not None and self.credit_limit.amount < 0:
            raise ValidationError("a credit limit cannot be negative", field="credit_limit")

    @property
    def has_credit_limit(self) -> bool:
        """True when a ceiling has been set at all."""
        return self.credit_limit is not None

    def available_credit(self, balance: Money) -> Money | None:
        """How much more this account may run up, when there is a limit."""
        if self.credit_limit is None:
            return None
        if balance.currency != self.credit_limit.currency:
            raise ValidationError(
                f"the balance is in {balance.currency} and the limit is in "
                f"{self.credit_limit.currency}",
                field="balance",
            )
        return self.credit_limit - balance

    def blocking_reasons(self, balance: Money, order_value: Money) -> tuple[str, ...]:
        """Everything stopping this account taking one more load."""
        reasons: list[str] = []
        if not self.status.takes_orders:
            reasons.append(f"the account is {self.status}")
        available = self.available_credit(balance)
        if available is not None and order_value > available:
            reasons.append(f"the order is {order_value} and only {available} of credit is left")
        return tuple(reasons)

    def require_credit(self, balance: Money, order_value: Money) -> None:
        """Refuse an order the account cannot take."""
        reasons = self.blocking_reasons(balance, order_value)
        if reasons:
            raise RuleViolationError("ACCOUNT_BLOCKED", "; ".join(reasons))

    def describe(self) -> str:
        """One line for an account listing."""
        limit = "-" if self.credit_limit is None else str(self.credit_limit)
        return (
            f"{self.code}  {self.name}  {self.status}  {self.terms.describe()}  limit {limit}"
        )
