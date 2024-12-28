"""Commands for the price list and what a mixture costs."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.money import Money
from slumpcone.pricing import MaterialPrice, cost_of, margin
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@click.group("price")
def price_group() -> None:
    """File material prices and cost a mixture out."""


@price_group.command("set")
@click.argument("material_code")
@click.argument("amount")
@click.option("--per", required=True, help='The basis, for example "1 ton".')
@click.option("--currency", default="USD")
@click.option("--from", "effective_from", default=None, metavar="YYYY-MM-DD")
@click.option("--to", "effective_to", default=None, metavar="YYYY-MM-DD")
@click.option("--close-previous", is_flag=True, help="End any open window first.")
@click.pass_obj
@handle_errors
def set_command(
    context: CliContext,
    material_code: str,
    amount: str,
    per: str,
    currency: str,
    effective_from: str | None,
    effective_to: str | None,
    close_previous: bool,
) -> None:
    """File a price for a material."""
    price = MaterialPrice(
        material_code,
        Money.parse(amount, currency),
        Quantity.parse(per),
        effective_from=None if effective_from is None else parse_day(effective_from),
        effective_to=None if effective_to is None else parse_day(effective_to),
    )
    with context.register() as register:
        if close_previous and price.effective_from is not None:
            from datetime import timedelta

            closed = register.prices.close_out(
                price.material_code, price.effective_from - timedelta(days=1)
            )
            if closed:
                context.say(f"closed {closed} open price window(s)")
        register.prices.save(price)
    click.echo(price.describe())


@price_group.command("list")
@day_option()
@click.pass_obj
@handle_errors
def list_command(context: CliContext, on: date) -> None:
    """The price in force for every material on a day."""
    with context.register() as register:
        rows: list[list[object]] = []
        for code in register.prices.codes():
            try:
                price = register.prices.current(code, on)
            except Exception:
                rows.append([code, "-", "-", "no price in force"])
                continue
            rows.append(
                [
                    code,
                    str(price.price),
                    price.per.format(0),
                    "-" if price.effective_from is None else price.effective_from.isoformat(),
                ]
            )
    columns = (
        Column("material"),
        Column("price", Align.RIGHT),
        Column("per", Align.RIGHT),
        Column("from"),
    )
    click.echo(render_table(columns, rows))


@price_group.command("history")
@click.argument("material_code")
@click.pass_obj
@handle_errors
def history_command(context: CliContext, material_code: str) -> None:
    """Every price ever filed for one material."""
    with context.register() as register:
        prices = register.prices.for_material(material_code)
    if not prices:
        raise click.ClickException(f"no price on file for {material_code.upper()!r}")
    columns = (
        Column("price", Align.RIGHT),
        Column("per", Align.RIGHT),
        Column("from"),
        Column("to"),
    )
    rows = [
        [
            str(price.price),
            price.per.format(0),
            "-" if price.effective_from is None else price.effective_from.isoformat(),
            "-" if price.effective_to is None else price.effective_to.isoformat(),
        ]
        for price in prices
    ]
    click.echo(render_table(columns, rows))


@price_group.command("cost")
@click.argument("mix_code")
@click.option("--volume", default="1 yd3", help="The batch to cost.")
@click.option("--sale", default=None, help='Sale price per unit, "$118.00".')
@day_option()
@click.pass_obj
@handle_errors
def cost_command(
    context: CliContext, mix_code: str, volume: str, sale: str | None, on: date
) -> None:
    """Cost a mixture out at a day's prices."""
    with context.register() as register:
        design = register.mixes.latest(mix_code)
        prices = register.prices.price_list()
    breakdown = cost_of(design.proportions, prices, Quantity.parse(volume), on)
    click.echo(heading(f"Cost of {design.identity}"))
    click.echo(breakdown.describe())
    click.echo("")
    click.echo(breakdown.render())
    if sale is not None:
        sale_price = Money.parse(sale)
        click.echo("")
        click.echo(
            render_pairs(
                [
                    ("sale price", str(sale_price)),
                    ("cost", str(breakdown.per_unit)),
                    ("margin", margin(sale_price, breakdown.per_unit).format(1)),
                ]
            )
        )


@price_group.command("compare")
@click.argument("mix_codes", nargs=-1, required=True)
@click.option("--volume", default="1 yd3")
@day_option()
@click.pass_obj
@handle_errors
def compare_command(
    context: CliContext, mix_codes: tuple[str, ...], volume: str, on: date
) -> None:
    """Cost several mixtures out side by side."""
    size = Quantity.parse(volume)
    rows: list[list[object]] = []
    with context.register() as register:
        prices = register.prices.price_list()
        for code in mix_codes:
            design = register.mixes.latest(code)
            breakdown = cost_of(design.proportions, prices, size, on)
            rows.append(
                [
                    design.identity,
                    design.cementitious.format(0),
                    f"{design.water_cementitious_ratio:.3f}",
                    str(breakdown.per_unit),
                    "yes" if breakdown.is_complete else "no",
                ]
            )
    columns = (
        Column("mix"),
        Column("cementitious", Align.RIGHT),
        Column("w/cm", Align.RIGHT),
        Column("per unit", Align.RIGHT),
        Column("fully priced"),
    )
    click.echo(render_table(columns, rows))
