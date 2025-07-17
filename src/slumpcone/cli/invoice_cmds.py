"""Commands for drafting, issuing and settling invoices."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import (
    CliContext,
    day_option,
    handle_errors,
    parse_day,
    window_options,
)
from slumpcone.money import Money
from slumpcone.percent import Percent
from slumpcone.sales.billing import build_invoice, charge_summary
from slumpcone.sales.charges import ChargeKind, ChargeRule, ChargeSchedule
from slumpcone.sales.invoice import Payment, aging, balance_of, overdue_of
from slumpcone.textout import Align, Column, heading, render_pairs, render_table

# The schedule the drafting command uses when a plant has not set its own. Real
# figures, so a draft is worth reading, and obvious enough that nobody mistakes
# them for the plant's own.
DEFAULT_SCHEDULE = ChargeSchedule(
    [
        ChargeRule(ChargeKind.SHORT_LOAD, Money.of("120.00")),
        ChargeRule(ChargeKind.STANDBY, Money.of("2.25")),
        ChargeRule(ChargeKind.AFTER_HOURS, Money.of("150.00")),
        ChargeRule(ChargeKind.WEEKEND, Money.of("200.00")),
        ChargeRule(ChargeKind.RETURNED_CONCRETE, Money.of("18.00")),
        ChargeRule(ChargeKind.FUEL, Money.of("3.5")),
    ]
)


@click.group("invoice")
def invoice_group() -> None:
    """Draft, issue and settle invoices."""


@invoice_group.command("draft")
@click.argument("number")
@click.option("--account", "account_code", required=True)
@window_options
@click.option("--project", default=None, help="Only tickets on this job.")
@click.option("--tax", type=float, default=0.0)
@click.option("--charges/--no-charges", "with_charges", default=True)
@click.option("--winter", is_flag=True, help="Add the cold weather charges.")
@click.pass_obj
@handle_errors
def draft_command(
    context: CliContext,
    number: str,
    account_code: str,
    start: date,
    end: date,
    project: str | None,
    tax: float,
    with_charges: bool,
    winter: bool,
) -> None:
    """Draft an invoice from a run of tickets."""
    with context.register() as register:
        account = register.accounts.get(account_code)
        tickets = [
            ticket
            for ticket in register.batches.between(start, end)
            if project is None or ticket.project == project
        ]
        if not tickets:
            raise click.ClickException("no tickets in that window")
        prices: dict[str, Money] = {}
        for ticket in tickets:
            if ticket.mix_code in prices:
                continue
            try:
                prices[ticket.mix_code] = register.accounts.quoted_price(
                    account.code, ticket.mix_code, end
                )
            except Exception:
                continue
        deliveries = {}
        for ticket in tickets:
            try:
                deliveries[ticket.number] = register.deliveries.get(ticket.number)
            except Exception:
                continue
        result = build_invoice(
            number,
            account,
            tickets,
            prices,
            invoiced_on=end,
            deliveries=deliveries,
            schedule=DEFAULT_SCHEDULE if with_charges else None,
            tax=Percent(tax),
            project=project,
            winter=winter,
        )
        register.invoices.save(result.invoice)
    click.echo(result.describe())


@invoice_group.command("show")
@click.argument("number")
@day_option()
@click.pass_obj
@handle_errors
def show_command(context: CliContext, number: str, on: date) -> None:
    """Print one invoice."""
    with context.register() as register:
        invoice = register.invoices.get(number)
    click.echo(heading(f"Invoice {invoice.number}"))
    click.echo(
        render_pairs(
            [
                ("account", invoice.account_code),
                ("job", invoice.project or "-"),
                ("invoiced", invoice.invoiced_on.isoformat()),
                ("terms", invoice.terms.describe()),
                ("due", invoice.due_on.isoformat()),
                ("status", str(invoice.status)),
                ("concrete", str(invoice.concrete)),
                ("charges", str(invoice.extras)),
                ("tax", str(invoice.tax_amount)),
                ("total", str(invoice.total)),
                ("paid", str(invoice.paid)),
                ("outstanding", str(invoice.outstanding)),
                ("aging", invoice.aging_bucket(on)),
            ]
        )
    )
    click.echo("")
    click.echo(
        render_table(
            (
                Column("ticket"),
                Column("mix"),
                Column("quantity", Align.RIGHT),
                Column("unit", Align.RIGHT),
                Column("amount", Align.RIGHT),
            ),
            [
                [
                    line.ticket_number,
                    line.mix_code,
                    line.volume.format(2),
                    str(line.unit_price),
                    str(line.amount),
                ]
                for line in invoice.lines
            ],
        )
    )
    summary = charge_summary(invoice)
    if summary:
        click.echo("")
        click.echo(
            render_table(
                (Column("charge"), Column("amount", Align.RIGHT)),
                [[str(kind), str(amount)] for kind, amount in summary.items()],
            )
        )


@invoice_group.command("issue")
@click.argument("number")
@click.option("--on", "issued_on", default=None, metavar="YYYY-MM-DD")
@click.pass_obj
@handle_errors
def issue_command(context: CliContext, number: str, issued_on: str | None) -> None:
    """Issue a draft."""
    with context.register() as register:
        invoice = register.invoices.get(number)
        issued = invoice.issue(None if issued_on is None else parse_day(issued_on))
        register.invoices.save(issued)
        context.note(register, "invoice.issue", issued.number, f"total {issued.total}")
    click.echo(issued.describe())


@invoice_group.command("pay")
@click.argument("number")
@click.option("--amount", required=True)
@click.option("--on", "received_on", required=True, metavar="YYYY-MM-DD")
@click.option("--reference", default=None)
@click.pass_obj
@handle_errors
def pay_command(
    context: CliContext, number: str, amount: str, received_on: str, reference: str | None
) -> None:
    """Record a payment."""
    payment = Payment(parse_day(received_on), Money.parse(amount), reference)
    with context.register() as register:
        invoice = register.invoices.get(number)
        paid = invoice.receive(payment)
        register.invoices.save(paid)
        discount = invoice.terms.discount_on(
            invoice.total, payment.received_on, invoice.invoiced_on
        )
    click.echo(paid.describe())
    if not discount.is_zero():
        click.echo(f"a prompt payment discount of {discount} was available")


@invoice_group.command("void")
@click.argument("number")
@click.pass_obj
@handle_errors
def void_command(context: CliContext, number: str) -> None:
    """Void an invoice that has taken no money."""
    with context.register() as register:
        voided = register.invoices.get(number).void()
        register.invoices.save(voided)
        context.note(register, "invoice.void", voided.number)
    click.echo(voided.describe())


@invoice_group.command("list")
@click.option("--account", "account_code", default=None)
@click.option("--owed", is_flag=True, help="Only invoices still expecting money.")
@day_option()
@click.pass_obj
@handle_errors
def list_command(context: CliContext, account_code: str | None, owed: bool, on: date) -> None:
    """List invoices."""
    with context.register() as register:
        if owed:
            invoices = register.invoices.owed()
        elif account_code is not None:
            invoices = register.invoices.for_account(account_code)
        else:
            invoices = register.invoices.between(date(1900, 1, 1), on)
    columns = (
        Column("number"),
        Column("account"),
        Column("invoiced"),
        Column("total", Align.RIGHT),
        Column("outstanding", Align.RIGHT),
        Column("status"),
        Column("aging"),
    )
    rows = [
        [
            invoice.number,
            invoice.account_code,
            invoice.invoiced_on.isoformat(),
            str(invoice.total),
            str(invoice.outstanding),
            str(invoice.status),
            invoice.aging_bucket(on),
        ]
        for invoice in invoices
    ]
    click.echo(render_table(columns, rows))


@invoice_group.command("aging")
@day_option()
@click.option("--account", "account_code", default=None)
@click.pass_obj
@handle_errors
def aging_command(context: CliContext, on: date, account_code: str | None) -> None:
    """The outstanding balance split into aging buckets."""
    with context.register() as register:
        invoices = (
            register.invoices.owed()
            if account_code is None
            else register.invoices.for_account(account_code)
        )
    click.echo(heading(f"Aging at {on.isoformat()}"))
    click.echo(
        render_pairs(
            [
                ("invoices", len(invoices)),
                ("outstanding", str(balance_of(invoices))),
                ("overdue", str(overdue_of(invoices, on))),
            ]
        )
    )
    click.echo("")
    click.echo(
        render_table(
            (Column("bucket"), Column("amount", Align.RIGHT)),
            [[name, str(amount)] for name, amount in aging(list(invoices), on).items()],
        )
    )


@invoice_group.command("unbilled")
@window_options
@click.pass_obj
@handle_errors
def unbilled_command(context: CliContext, start: date, end: date) -> None:
    """Tickets in a window that no invoice has picked up."""
    with context.register() as register:
        numbers = register.invoices.unbilled_tickets(start, end)
    click.echo(heading(f"Unbilled, {start.isoformat()} to {end.isoformat()}"))
    for number in numbers:
        click.echo(f"  {number}")
    click.echo(f"{len(numbers)} ticket(s)")
