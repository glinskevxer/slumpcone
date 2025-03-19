"""Invoices, and the difference between what is owed and what is overdue.

An invoice is built from tickets rather than typed, because the tickets are
what the customer signed for and any figure that does not trace back to one is
a figure somebody will dispute. Each line names its ticket.

Two totals matter and they are not the same. Outstanding is what has not been
paid. Overdue is what has not been paid and whose term has run out. An account
can carry a large outstanding balance and owe nothing overdue, which is a
customer paying on terms, and the two get confused in every aging report that
subtracts payments from a single number.

Payments are a list, not a balance. Part payments happen, they arrive out of
order, and one of them will need reversing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import Enum

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name, normalize_ticket_number
from slumpcone.money import Money, total
from slumpcone.percent import Percent
from slumpcone.sales.account import PaymentTerms
from slumpcone.sales.charges import AppliedCharge
from slumpcone.units.checks import require_volume
from slumpcone.units.quantity import Quantity

# The buckets an aging report puts an overdue invoice in.
AGING_BUCKETS = (30, 60, 90)


class InvoiceStatus(Enum):
    """Where an invoice stands."""

    DRAFT = "draft"
    ISSUED = "issued"
    PART_PAID = "part_paid"
    PAID = "paid"
    VOID = "void"

    def __str__(self) -> str:
        return self.value

    @property
    def is_owed(self) -> bool:
        """True when money is still expected against it."""
        return self in {InvoiceStatus.ISSUED, InvoiceStatus.PART_PAID}

    @property
    def is_settled(self) -> bool:
        """True when nothing more will happen to it."""
        return self in {InvoiceStatus.PAID, InvoiceStatus.VOID}


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    """One ticket's worth of concrete."""

    ticket_number: str
    mix_code: str
    volume: Quantity
    unit_price: Money

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticket_number", normalize_ticket_number(self.ticket_number))
        object.__setattr__(self, "mix_code", normalize_code(self.mix_code, field="mix_code"))
        require_volume(self.volume, "an invoiced quantity", field="volume")
        if self.volume.value <= 0.0:
            raise ValidationError("an invoiced quantity has to be positive", field="volume")
        if self.unit_price.amount < 0:
            raise ValidationError("a unit price cannot be negative", field="unit_price")

    @property
    def amount(self) -> Money:
        """What this line comes to."""
        return self.unit_price * self.volume.to("yd3").value

    def describe(self) -> str:
        """One line for an invoice."""
        return (
            f"{self.ticket_number}  {self.mix_code}  {self.volume.format(2)} at "
            f"{self.unit_price}  {self.amount}"
        )


@dataclass(frozen=True, slots=True)
class Payment:
    """One payment received against an invoice."""

    received_on: date
    amount: Money
    reference: str | None = None

    def __post_init__(self) -> None:
        if self.amount.amount <= 0:
            raise ValidationError("a payment has to be positive", field="amount")
        if self.reference is not None:
            object.__setattr__(
                self, "reference", normalize_code(self.reference, field="reference")
            )


@dataclass(frozen=True, slots=True)
class Invoice:
    """One invoice, its lines, its charges and what has been paid on it."""

    number: str
    account_code: str
    invoiced_on: date
    lines: tuple[InvoiceLine, ...]
    charges: tuple[AppliedCharge, ...] = ()
    payments: tuple[Payment, ...] = ()
    terms: PaymentTerms = PaymentTerms()
    tax: Percent = Percent(0.0)
    project: str | None = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    currency: str = "USD"
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalize_code(self.number, field="invoice_number"))
        object.__setattr__(
            self, "account_code", normalize_code(self.account_code, field="account_code")
        )
        if self.project is not None:
            object.__setattr__(self, "project", normalize_name(self.project, field="project"))
        if not 0.0 <= self.tax.value < 100.0:
            raise ValidationError("a tax rate is a share of the invoice", field="tax")
        for payment in self.payments:
            if payment.received_on < self.invoiced_on:
                raise ValidationError(
                    "a payment cannot arrive before the invoice", field="payments"
                )

    @property
    def concrete(self) -> Money:
        """The concrete alone."""
        return total([line.amount for line in self.lines], self.currency)

    @property
    def extras(self) -> Money:
        """Everything besides the concrete."""
        return total([charge.amount for charge in self.charges], self.currency)

    @property
    def subtotal(self) -> Money:
        """Concrete and charges together, before tax."""
        return self.concrete + self.extras

    @property
    def tax_amount(self) -> Money:
        """The tax on the subtotal."""
        return self.subtotal * (self.tax.value / 100.0)

    @property
    def total(self) -> Money:
        """What the customer owes on this invoice."""
        return self.subtotal + self.tax_amount

    @property
    def paid(self) -> Money:
        """Everything received against it."""
        return total([payment.amount for payment in self.payments], self.currency)

    @property
    def outstanding(self) -> Money:
        """What is still unpaid, floored at nothing."""
        left = self.total - self.paid
        return Money.zero(self.currency) if left.amount < 0 else left

    @property
    def is_overpaid(self) -> bool:
        """True when more came in than was billed."""
        return self.paid > self.total

    @property
    def due_on(self) -> date:
        """When it falls due."""
        return self.terms.due_on(self.invoiced_on)

    def days_overdue(self, on: date) -> int:
        """Days past the due date, zero until it passes."""
        return max((on - self.due_on).days, 0)

    def is_overdue(self, on: date) -> bool:
        """True when it is past due and still owed."""
        return self.status.is_owed and on > self.due_on and not self.outstanding.is_zero()

    def aging_bucket(self, on: date) -> str:
        """Which column of an aging report it falls in."""
        if not self.is_overdue(on):
            return "current"
        days = self.days_overdue(on)
        previous = 0
        for bucket in AGING_BUCKETS:
            if days <= bucket:
                return f"{previous + 1} to {bucket}"
            previous = bucket
        return f"over {AGING_BUCKETS[-1]}"

    def issue(self, on: date | None = None) -> Invoice:
        """Move a draft to issued."""
        if self.status is not InvoiceStatus.DRAFT:
            raise RuleViolationError(
                "INVOICE_ALREADY_ISSUED", f"{self.number} is already {self.status}"
            )
        if not self.lines:
            raise ValidationError("an invoice needs at least one line", field="lines")
        return replace(
            self,
            status=InvoiceStatus.ISSUED,
            invoiced_on=on or self.invoiced_on,
        )

    def receive(self, payment: Payment) -> Invoice:
        """Record a payment and move the status with it."""
        if self.status is InvoiceStatus.VOID:
            raise RuleViolationError(
                "INVOICE_VOID", f"{self.number} is void and cannot take a payment"
            )
        if self.status is InvoiceStatus.DRAFT:
            raise RuleViolationError(
                "INVOICE_NOT_ISSUED", f"{self.number} has not been issued yet"
            )
        received = (*self.payments, payment)
        taken = total([entry.amount for entry in received], self.currency)
        status = InvoiceStatus.PAID if taken >= self.total else InvoiceStatus.PART_PAID
        return replace(self, payments=received, status=status)

    def void(self) -> Invoice:
        """Void an invoice that has taken no money."""
        if self.payments:
            raise RuleViolationError(
                "INVOICE_HAS_PAYMENTS",
                f"{self.number} has {len(self.payments)} payment(s) and cannot be voided",
            )
        return replace(self, status=InvoiceStatus.VOID)

    def describe(self) -> str:
        """One line for an invoice register."""
        return (
            f"{self.number}  {self.account_code}  {self.invoiced_on.isoformat()}  "
            f"{self.total}  {self.status}  due {self.due_on.isoformat()}"
        )


def balance_of(invoices: Iterable[Invoice], currency: str = "USD") -> Money:
    """What an account owes across every invoice that is still owed."""
    return total(
        [invoice.outstanding for invoice in invoices if invoice.status.is_owed], currency
    )


def overdue_of(invoices: Iterable[Invoice], on: date, currency: str = "USD") -> Money:
    """What an account owes that has run past its terms."""
    return total(
        [invoice.outstanding for invoice in invoices if invoice.is_overdue(on)], currency
    )


def aging(invoices: Sequence[Invoice], on: date, currency: str = "USD") -> dict[str, Money]:
    """The outstanding balance split into aging buckets."""
    buckets: dict[str, Money] = {"current": Money.zero(currency)}
    previous = 0
    for bucket in AGING_BUCKETS:
        buckets[f"{previous + 1} to {bucket}"] = Money.zero(currency)
        previous = bucket
    buckets[f"over {AGING_BUCKETS[-1]}"] = Money.zero(currency)
    for invoice in invoices:
        if not invoice.status.is_owed:
            continue
        name = invoice.aging_bucket(on)
        buckets[name] = buckets[name] + invoice.outstanding
    return buckets
