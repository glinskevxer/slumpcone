"""Commands for customer accounts and what they were quoted."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.money import Money
from slumpcone.sales.account import Account, AccountStatus, PaymentTerms
from slumpcone.textout import Align, Column, heading, render_pairs, render_table


@click.group("account")
def account_group() -> None:
    """File customers, their terms and their prices."""


@account_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--status", default="open")
@click.option("--terms", type=int, default=30, help="Days to pay.")
@click.option("--discount-days", type=int, default=0)
@click.option("--discount", type=float, default=0.0, help="Prompt payment discount.")
@click.option("--limit", "credit_limit", default=None, help='Credit limit, "$25000".')
@click.option("--contact", default=None)
@click.option("--phone", default=None)
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def add_command(
    context: CliContext,
    code: str,
    name: str,
    status: str,
    terms: int,
    discount_days: int,
    discount: float,
    credit_limit: str | None,
    contact: str | None,
    phone: str | None,
    notes: str,
) -> None:
    """File a customer."""
    account = Account(
        code=code,
        name=name,
        status=AccountStatus.parse(status),
        terms=PaymentTerms(terms, discount_days, discount),
        credit_limit=None if credit_limit is None else Money.parse(credit_limit),
        contact=contact,
        phone=phone,
        notes=notes,
    )
    with context.register() as register:
        register.accounts.save(account)
    click.echo(account.describe())


@account_group.command("list")
@click.option("--open", "only_open", is_flag=True, help="Only accounts taking work.")
@click.pass_obj
@handle_errors
def list_command(context: CliContext, only_open: bool) -> None:
    """List the customers."""
    with context.register() as register:
        accounts = register.accounts.open_accounts() if only_open else register.accounts.all()
    columns = (
        Column("code"),
        Column("name"),
        Column("status"),
        Column("terms"),
        Column("limit", Align.RIGHT),
        Column("contact"),
    )
    rows = [
        [
            account.code,
            account.name,
            str(account.status),
            account.terms.describe(),
            "-" if account.credit_limit is None else str(account.credit_limit),
            account.contact or "-",
        ]
        for account in accounts
    ]
    click.echo(render_table(columns, rows))


@account_group.command("show")
@click.argument("code")
@click.option("--balance", default="0.00", help="What they owe right now.")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, code: str, balance: str) -> None:
    """Show one customer, their terms and their quotes."""
    owed = Money.parse(balance)
    with context.register() as register:
        account = register.accounts.get(code)
        quotes = register.accounts.quotes_for(account.code)
    available = account.available_credit(owed)
    click.echo(heading(account.describe()))
    click.echo(
        render_pairs(
            [
                ("status", str(account.status)),
                ("terms", account.terms.describe()),
                ("contact", account.contact or "-"),
                ("phone", account.phone or "-"),
                ("balance", str(owed)),
                ("credit left", "-" if available is None else str(available)),
                ("takes orders", "yes" if account.status.takes_orders else "no"),
            ]
        )
    )
    if quotes:
        click.echo("")
        click.echo(
            render_table(
                (Column("mix"), Column("price", Align.RIGHT)),
                [[mix, str(price)] for mix, price in quotes],
            )
        )


@account_group.command("quote")
@click.argument("account_code")
@click.argument("mix_code")
@click.argument("price")
@click.option("--from", "effective_from", default=None, metavar="YYYY-MM-DD")
@click.option("--to", "effective_to", default=None, metavar="YYYY-MM-DD")
@click.pass_obj
@handle_errors
def quote_command(
    context: CliContext,
    account_code: str,
    mix_code: str,
    price: str,
    effective_from: str | None,
    effective_to: str | None,
) -> None:
    """Quote one customer a price for one mixture."""
    amount = Money.parse(price)
    with context.register() as register:
        register.accounts.quote(
            account_code,
            mix_code,
            amount,
            effective_from=None if effective_from is None else parse_day(effective_from),
            effective_to=None if effective_to is None else parse_day(effective_to),
        )
    click.echo(f"{account_code.upper()} pays {amount} for {mix_code.upper()}")


@account_group.command("check")
@click.argument("code")
@click.option("--balance", required=True, help="What they owe right now.")
@click.option("--order", "order_value", required=True, help="What the order is worth.")
@click.pass_obj
@handle_errors
def check_command(context: CliContext, code: str, balance: str, order_value: str) -> None:
    """Say whether an account can take one more order."""
    with context.register() as register:
        account = register.accounts.get(code)
    reasons = account.blocking_reasons(Money.parse(balance), Money.parse(order_value))
    if not reasons:
        click.echo("nothing stops this order")
        return
    for reason in reasons:
        click.echo(f"  {reason}")
    raise click.ClickException(f"{len(reasons)} reason(s)")


@account_group.command("margin")
@click.argument("account_code")
@click.argument("mix_code")
@day_option()
@click.option("--volume", default="1 yd3")
@click.pass_obj
@handle_errors
def margin_command(
    context: CliContext, account_code: str, mix_code: str, on: date, volume: str
) -> None:
    """What one customer pays for a mixture against what it costs to make."""
    from slumpcone.pricing import cost_of, margin
    from slumpcone.units.quantity import Quantity

    with context.register() as register:
        quoted = register.accounts.quoted_price(account_code, mix_code, on)
        design = register.mixes.latest(mix_code)
        prices = register.prices.price_list()
        breakdown = cost_of(design.proportions, prices, Quantity.parse(volume), on)
    click.echo(
        render_pairs(
            [
                ("account", account_code.upper()),
                ("mix", design.identity),
                ("quoted", str(quoted)),
                ("cost", str(breakdown.per_unit)),
                ("margin", margin(quoted, breakdown.per_unit).format(1)),
                ("fully priced", "yes" if breakdown.is_complete else "no"),
            ]
        )
    )
