"""Building an invoice out of a run of tickets.

The billing clerk's job is deciding what to charge; working out *which* charges
apply is arithmetic on records the register already holds. Standby comes off
the delivery's own arrival and finish times. Returned concrete comes off the
delivery. Weekend and after-hours come off the batch time and the plant's own
working hours. None of that needs typing in, and every one of them gets missed
when it does.

What the clerk still decides is the price, because a quote is a negotiation,
and whether to bill a charge at all, because waiving standby on a job that ran
long through no fault of the customer is a commercial decision rather than an
arithmetic one. So the builder produces a draft with everything on it and the
clerk takes lines off.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time

from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.money import Money
from slumpcone.percent import Percent
from slumpcone.sales.account import Account
from slumpcone.sales.charges import AppliedCharge, ChargeKind, ChargeSchedule
from slumpcone.sales.invoice import Invoice, InvoiceLine

# Outside these the load is after hours. A plant that runs a night shift puts
# its own hours in.
DEFAULT_DAY_START = time(6, 0)
DEFAULT_DAY_END = time(17, 0)

# No tax unless the caller names one. A module level value rather than a call in
# the signature, which is evaluated once at import either way but reads as a
# constant instead of looking like a fresh object per call.
NO_TAX = Percent(0.0)


@dataclass(frozen=True, slots=True)
class BillingWindow:
    """When a plant's ordinary day runs."""

    starts: time = DEFAULT_DAY_START
    ends: time = DEFAULT_DAY_END
    weekend_days: tuple[int, ...] = (5, 6)

    def __post_init__(self) -> None:
        if self.ends <= self.starts:
            raise ValidationError("a working day has to end after it starts", field="ends")
        for day in self.weekend_days:
            if not 0 <= day <= 6:
                raise ValidationError("a weekday is 0 to 6", field="weekend_days")

    def is_after_hours(self, moment: datetime) -> bool:
        """True when a load was batched outside the ordinary day."""
        clock = moment.time()
        return clock < self.starts or clock >= self.ends

    def is_weekend(self, moment: datetime) -> bool:
        """True when a load was batched on a weekend day."""
        return moment.weekday() in self.weekend_days


def on_site_minutes(delivery: Delivery) -> float | None:
    """How long the truck was on the job, when both ends were recorded."""
    if delivery.arrived_at is None or delivery.discharge_finished_at is None:
        return None
    return (delivery.discharge_finished_at - delivery.arrived_at).total_seconds() / 60.0


@dataclass(frozen=True, slots=True)
class BillingResult:
    """A draft invoice and what could not be priced."""

    invoice: Invoice
    unpriced: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        """True when every ticket in the run had a price."""
        return not self.unpriced

    def describe(self) -> str:
        """One line for the clerk."""
        tail = (
            ""
            if self.is_complete
            else f", {len(self.unpriced)} ticket(s) with no quote: {', '.join(self.unpriced)}"
        )
        return f"{self.invoice.describe()}{tail}"


def build_invoice(
    number: str,
    account: Account,
    tickets: Sequence[BatchTicket],
    prices: Mapping[str, Money],
    *,
    invoiced_on: date,
    deliveries: Mapping[str, Delivery] | None = None,
    schedule: ChargeSchedule | None = None,
    window: BillingWindow | None = None,
    tax: Percent = NO_TAX,
    project: str | None = None,
    winter: bool = False,
) -> BillingResult:
    """Draft an invoice for a run of tickets.

    A ticket whose mixture has no quote is left off and named, rather than
    billed at zero or at a guess. An invoice that silently drops a load is
    worse than one that will not build.
    """
    if not tickets:
        raise ValidationError("an invoice needs at least one ticket", field="tickets")
    hours = window or BillingWindow()
    lines: list[InvoiceLine] = []
    unpriced: list[str] = []
    for ticket in sorted(tickets, key=lambda entry: (entry.batched_at, entry.number)):
        price = prices.get(ticket.mix_code)
        if price is None:
            unpriced.append(ticket.number)
            continue
        lines.append(InvoiceLine(ticket.number, ticket.mix_code, ticket.volume, price))
    if not lines:
        raise ValidationError("no ticket in this run has a quoted price", field="prices")
    concrete = Money.zero(lines[0].unit_price.currency)
    for line in lines:
        concrete = concrete + line.amount
    charges: list[AppliedCharge] = []
    if schedule is not None:
        found = deliveries or {}
        for line in lines:
            ticket = next(entry for entry in tickets if entry.number == line.ticket_number)
            delivery = found.get(ticket.number)
            charges.extend(
                schedule.charges_for(
                    ticket.volume,
                    line.amount,
                    on_site_minutes=None if delivery is None else on_site_minutes(delivery),
                    after_hours=hours.is_after_hours(ticket.batched_at),
                    weekend=hours.is_weekend(ticket.batched_at),
                    returned=None if delivery is None else delivery.returned_volume,
                    winter=winter,
                )
            )
    invoice = Invoice(
        number=number,
        account_code=account.code,
        invoiced_on=invoiced_on,
        lines=tuple(lines),
        charges=tuple(charges),
        terms=account.terms,
        tax=tax,
        project=project,
        currency=concrete.currency,
    )
    return BillingResult(invoice, tuple(unpriced))


def without_charge(invoice: Invoice, kind: ChargeKind) -> Invoice:
    """The same draft with one kind of charge taken off.

    Refuses on anything but a draft, because taking a charge off an issued
    invoice is a credit note rather than an edit.
    """
    from slumpcone.sales.invoice import InvoiceStatus

    if invoice.status is not InvoiceStatus.DRAFT:
        raise ValidationError(
            f"{invoice.number} is {invoice.status}; take a charge off with a credit "
            "note rather than an edit",
            field="status",
        )
    kept = tuple(charge for charge in invoice.charges if charge.kind is not kind)
    if len(kept) == len(invoice.charges):
        raise NotFoundError("charge on this invoice", str(kind))
    return replace(invoice, charges=kept)


def charge_summary(invoice: Invoice) -> dict[ChargeKind, Money]:
    """What each kind of charge came to on one invoice."""
    summary: dict[ChargeKind, Money] = {}
    for charge in invoice.charges:
        running = summary.get(charge.kind, Money.zero(invoice.currency))
        summary[charge.kind] = running + charge.amount
    return dict(sorted(summary.items(), key=lambda pair: pair[0].value))
