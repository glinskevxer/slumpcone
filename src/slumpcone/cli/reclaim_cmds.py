"""Commands for wash water and returned concrete."""

from __future__ import annotations

from datetime import date, timedelta

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, window_options
from slumpcone.materials.wash_water import (
    RETURNED_SHARE_LIMIT,
    ReturnedConcrete,
    WashWater,
    blend_into,
)
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@click.group("reclaim")
def reclaim_group() -> None:
    """Wash water tanks and loads that came back."""


@reclaim_group.command("tank")
@click.argument("tank")
@click.option("--plant", "plant_code", required=True)
@click.option("--sg", "specific_gravity", type=float, required=True)
@click.option("--volume", required=True, help='For example "2000 gal".')
@day_option("--on", "The day the tank was read.")
@click.option("--notes", default="")
@click.option("--replace", is_flag=True, help="Overwrite today's reading.")
@click.pass_obj
@handle_errors
def tank_command(
    context: CliContext,
    tank: str,
    plant_code: str,
    specific_gravity: float,
    volume: str,
    on: date,
    notes: str,
    replace: bool,
) -> None:
    """Record a wash tank density reading."""
    reading = WashWater(tank, specific_gravity, Quantity.parse(volume))
    with context.register() as register:
        register.reclaim.save_reading(reading, plant_code, on, notes=notes, replace=replace)
    click.echo(reading.describe())


@reclaim_group.command("tanks")
@click.option("--plant", "plant_code", required=True)
@day_option("--on")
@click.option("--usable", is_flag=True, help="Only the tanks clean enough to batch from.")
@click.pass_obj
@handle_errors
def tanks_command(context: CliContext, plant_code: str, on: date, usable: bool) -> None:
    """Every tank read on one day."""
    with context.register() as register:
        tanks = (
            register.reclaim.usable_on(plant_code, on)
            if usable
            else register.reclaim.readings_on(plant_code, on)
        )
    click.echo(heading(f"Wash tanks, {plant_code.strip().upper()} on {on.isoformat()}"))
    click.echo(
        render_table(
            (
                Column("tank"),
                Column("sg", Align.RIGHT),
                Column("solids ppm", Align.RIGHT),
                Column("solids", Align.RIGHT),
                Column("held", Align.RIGHT),
                Column("verdict"),
            ),
            [
                [
                    one.tank,
                    f"{one.specific_gravity:.3f}",
                    f"{one.solids_ppm:,.0f}",
                    one.solids_share.format(2),
                    one.volume.format(0),
                    "usable" if one.meets_solids_limit else "over the limit",
                ]
                for one in tanks
            ],
        )
    )
    click.echo(f"{len(tanks)} tank(s)")


@reclaim_group.command("draw")
@click.argument("tank")
@click.argument("amount")
@click.option("--plant", "plant_code", required=True)
@day_option("--on")
@click.pass_obj
@handle_errors
def draw_command(
    context: CliContext, tank: str, amount: str, plant_code: str, on: date
) -> None:
    """How much of a draw is water and how much is cement that already reacted."""
    drawn = Quantity.parse(amount)
    with context.register() as register:
        reading = register.reclaim.reading(plant_code, tank, on)
    click.echo(
        render_pairs(
            [
                ("tank", reading.tank),
                ("specific gravity", f"{reading.specific_gravity:.3f}"),
                ("drawn", drawn.format(1)),
                ("water", reading.water_in(drawn).format(1)),
                ("solids", reading.solids_in(drawn).format(2)),
                (
                    "usable",
                    "yes" if reading.meets_solids_limit else "no, over the solids limit",
                ),
            ]
        )
    )
    if not reading.meets_solids_limit:
        raise click.ClickException("this tank is over the C1602 solids limit")


@reclaim_group.command("returned")
@click.argument("ticket")
@click.option("--mix", "mix_code", required=True)
@click.option("--volume", required=True, help='For example "3 yd3".')
@click.option("--age", type=float, required=True, help="Minutes since batching.")
@day_option("--on", "The day it came back.")
@click.pass_obj
@handle_errors
def returned_command(
    context: CliContext,
    ticket: str,
    mix_code: str,
    volume: str,
    age: float,
    on: date,
) -> None:
    """Record a load that came back."""
    load = ReturnedConcrete(ticket, mix_code, Quantity.parse(volume), timedelta(minutes=age))
    with context.register() as register:
        register.reclaim.save_returned(load, on)
    click.echo(load.describe())


@reclaim_group.command("yard")
@day_option("--on")
@click.option("--into", "new_load", default="9 yd3", help="The load being planned.")
@click.option("--waited", type=float, default=0.0, help="Extra minutes on the yard.")
@click.option(
    "--cap",
    type=float,
    default=RETURNED_SHARE_LIMIT.value,
    help="Share of a new load returned concrete may be, percent.",
)
@click.pass_obj
@handle_errors
def yard_command(
    context: CliContext, on: date, new_load: str, waited: float, cap: float
) -> None:
    """What is still sitting on the yard, and how much of it can be used."""
    size = Quantity.parse(new_load)
    wait = timedelta(minutes=waited)
    with context.register() as register:
        loads = register.reclaim.still_on_the_yard(on)
    click.echo(heading(f"On the yard, {on.isoformat()}"))
    click.echo(
        render_table(
            (
                Column("ticket"),
                Column("mix"),
                Column("volume", Align.RIGHT),
                Column("age", Align.RIGHT),
                Column("into a load", Align.RIGHT),
                Column("verdict"),
            ),
            [
                [
                    one.ticket_number,
                    one.mix_code,
                    one.volume.format(1),
                    f"{one.age_at(wait).total_seconds() / 60:.0f} min",
                    blend_into(one, size, waited=wait, cap=Percent(cap)).format(2),
                    "usable" if one.is_usable(wait) else "too old",
                ]
                for one in loads
            ],
        )
    )
    stranded = [one for one in loads if not one.is_usable(wait)]
    click.echo(f"{len(loads)} load(s) on the yard, {len(stranded)} too old to use")


@reclaim_group.command("use")
@click.argument("ticket")
@click.argument("new_ticket")
@click.pass_obj
@handle_errors
def use_command(context: CliContext, ticket: str, new_ticket: str) -> None:
    """Record that a returned load went into a later one."""
    with context.register() as register:
        register.reclaim.use_in(ticket, new_ticket)
    click.echo(f"{ticket.strip().upper()} went into {new_ticket.strip().upper()}")


@reclaim_group.command("dispose")
@click.argument("ticket")
@day_option("--on")
@click.pass_obj
@handle_errors
def dispose_command(context: CliContext, ticket: str, on: date) -> None:
    """Record that a returned load was dumped."""
    with context.register() as register:
        register.reclaim.dispose(ticket, on)
        context.note(register, "reclaim.dispose", ticket.strip().upper(), on.isoformat())
    click.echo(f"{ticket.strip().upper()} disposed of on {on.isoformat()}")


@reclaim_group.command("history")
@window_options
@click.pass_obj
@handle_errors
def history_command(context: CliContext, start: date, end: date) -> None:
    """Every load that came back in a window, and what became of it."""
    with context.register() as register:
        loads = register.reclaim.returned_between(start, end)
        fates = {
            one.ticket_number: register.reclaim.fate_of(one.ticket_number) for one in loads
        }
    rows = []
    for one in loads:
        used, dumped = fates[one.ticket_number]
        if used is not None:
            fate = f"used in {used}"
        elif dumped is not None:
            fate = f"dumped {dumped.isoformat()}"
        else:
            fate = "still on the yard"
        rows.append([one.ticket_number, one.mix_code, one.volume.format(1), fate])
    click.echo(
        render_table(
            (Column("ticket"), Column("mix"), Column("volume", Align.RIGHT), Column("fate")),
            rows,
        )
    )
    click.echo(f"{len(loads)} load(s) came back")
