"""Commands for laying pours out and putting trucks against them."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import click

from slumpcone.cli.common import (
    CliContext,
    F,
    day_option,
    handle_errors,
    parse_moment,
)
from slumpcone.dispatch.board import assign, trucks_to_hold
from slumpcone.dispatch.schedule import (
    CycleTime,
    Schedule,
    ScheduleError,
    build_schedule,
    overlaps,
)
from slumpcone.register import Register
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity

DEFAULT_START = time(7, 0)


def cycle_options(command: F) -> F:
    """The five legs of a truck cycle, as minutes."""
    for name, default, blurb in (
        ("--wash", 5, "Washing out after the load."),
        ("--back", 20, "Driving back to the plant."),
        ("--site", 15, "On site, waiting and discharging."),
        ("--out", 20, "Driving out to the job."),
        ("--load", 10, "Loading at the plant."),
    ):
        command = click.option(name, type=int, default=default, help=f"{blurb} Minutes.")(
            command
        )
    return command


def cycle_from(load: int, out: int, site: int, back: int, wash: int) -> CycleTime:
    """A cycle out of five minute counts."""
    return CycleTime(
        timedelta(minutes=load),
        timedelta(minutes=out),
        timedelta(minutes=site),
        timedelta(minutes=back),
        timedelta(minutes=wash),
    )


def schedule_for_order(
    register: Register,
    order_number: str,
    cycle: CycleTime,
    *,
    load_size: Quantity,
    rate: Quantity | None,
    start: datetime | None,
) -> Schedule:
    """Lay a booked order out, filling in what the booking did not say."""
    order = register.orders.get(order_number)
    pour_rate = rate if rate is not None else order.rate
    if pour_rate is None:
        raise ScheduleError(
            "SCHEDULE_NO_POUR_RATE",
            f"{order.number} carries no placing rate, give one with --rate",
        )
    when = start
    if when is None:
        clock = order.start_time or DEFAULT_START
        when = datetime.combine(order.placement_date, clock)
    return build_schedule(order.number, order.volume, load_size, pour_rate, when, cycle)


@click.group("dispatch")
def dispatch_group() -> None:
    """Lay pours out and put trucks against them."""


@dispatch_group.command("schedule")
@click.argument("order_number")
@click.option("--load", "load_size", default="9 yd3", help="Load size.")
@click.option("--rate", default=None, help='Placing rate, "30 yd3".')
@click.option("--start", default=None, metavar="YYYY-MM-DDTHH:MM")
@cycle_options
@click.pass_obj
@handle_errors
def schedule_command(
    context: CliContext,
    order_number: str,
    load_size: str,
    rate: str | None,
    start: str | None,
    load: int,
    out: int,
    site: int,
    back: int,
    wash: int,
) -> None:
    """Lay one order out into loads."""
    cycle = cycle_from(load, out, site, back, wash)
    with context.register() as register:
        found = schedule_for_order(
            register,
            order_number,
            cycle,
            load_size=Quantity.parse(load_size),
            rate=None if rate is None else Quantity.parse(rate),
            start=None if start is None else parse_moment(start),
        )
    click.echo(heading(f"Schedule, {found.order_number}"))
    click.echo(
        render_pairs(
            [
                ("volume", found.total_volume.format(1)),
                ("loads", len(found.loads)),
                ("spacing", f"{found.spacing.total_seconds() / 60:.0f} min"),
                ("cycle", found.cycle.describe()),
                ("trucks needed", found.trucks_needed),
                (
                    "first batch",
                    "-" if found.first_batch is None else f"{found.first_batch:%H:%M}",
                ),
                (
                    "last arrival",
                    "-" if found.last_arrival is None else f"{found.last_arrival:%H:%M}",
                ),
                ("on site for", f"{found.duration.total_seconds() / 3600:.1f} h"),
                (
                    "discharge limit",
                    "clears" if found.cycle.within_discharge_limit else "at risk",
                ),
            ]
        )
    )
    click.echo("")
    click.echo(
        render_table(
            (
                Column("load", Align.RIGHT),
                Column("batch"),
                Column("arrive"),
                Column("volume", Align.RIGHT),
                Column("off by"),
                Column("note"),
            ),
            [
                [
                    one.sequence,
                    f"{one.batch_at:%H:%M}",
                    f"{one.arrive_at:%H:%M}",
                    one.volume.format(1),
                    f"{one.discharge_deadline:%H:%M}",
                    "short" if one.is_short else "",
                ]
                for one in found.loads
            ],
        )
    )


@dispatch_group.command("board")
@click.argument("order_number")
@click.option("--truck", "trucks", multiple=True, help="A truck code. Repeatable.")
@click.option("--load", "load_size", default="9 yd3")
@click.option("--rate", default=None)
@click.option("--start", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--no-slip", is_flag=True, help="Leave loads unassigned rather than late.")
@cycle_options
@click.pass_obj
@handle_errors
def board_command(
    context: CliContext,
    order_number: str,
    trucks: tuple[str, ...],
    load_size: str,
    rate: str | None,
    start: str | None,
    no_slip: bool,
    load: int,
    out: int,
    site: int,
    back: int,
    wash: int,
) -> None:
    """Put trucks against one order."""
    cycle = cycle_from(load, out, site, back, wash)
    with context.register() as register:
        found = schedule_for_order(
            register,
            order_number,
            cycle,
            load_size=Quantity.parse(load_size),
            rate=None if rate is None else Quantity.parse(rate),
            start=None if start is None else parse_moment(start),
        )
        codes = trucks or tuple(truck.code for truck in register.deliveries.trucks())
    board = assign(found, codes, allow_slip=not no_slip)
    click.echo(board.describe())
    click.echo("")
    click.echo(
        render_table(
            (
                Column("load", Align.RIGHT),
                Column("truck"),
                Column("scheduled"),
                Column("actual"),
                Column("slip", Align.RIGHT),
            ),
            [
                [
                    one.load.sequence,
                    one.truck_code,
                    f"{one.load.batch_at:%H:%M}",
                    f"{one.batch_at:%H:%M}",
                    f"{one.slip.total_seconds() / 60:.0f}",
                ]
                for one in board.assignments
            ],
        )
    )
    for load_left in board.unassigned:
        click.echo(f"  unassigned: load {load_left.sequence} at {load_left.batch_at:%H:%M}")
    click.echo(f"{trucks_to_hold(found, codes)} of {len(codes)} truck(s) needed")


@dispatch_group.command("at")
@click.argument("order_number")
@click.argument("moment")
@click.option("--truck", "trucks", multiple=True)
@click.option("--load", "load_size", default="9 yd3")
@click.option("--rate", default=None)
@cycle_options
@click.pass_obj
@handle_errors
def at_command(
    context: CliContext,
    order_number: str,
    moment: str,
    trucks: tuple[str, ...],
    load_size: str,
    rate: str | None,
    load: int,
    out: int,
    site: int,
    back: int,
    wash: int,
) -> None:
    """What every truck is doing at one moment."""
    when = parse_moment(moment)
    cycle = cycle_from(load, out, site, back, wash)
    with context.register() as register:
        found = schedule_for_order(
            register,
            order_number,
            cycle,
            load_size=Quantity.parse(load_size),
            rate=None if rate is None else Quantity.parse(rate),
            start=None,
        )
        codes = trucks or tuple(truck.code for truck in register.deliveries.trucks())
    board = assign(found, codes)
    states = board.state_at(when)
    click.echo(heading(f"{found.order_number} at {when:%Y-%m-%d %H:%M}"))
    click.echo(
        render_table(
            (Column("truck"), Column("doing")),
            [[code, str(state)] for code, state in sorted(states.items())],
        )
    )
    click.echo(f"{board.working_at(when)} of {len(states)} carrying")


@dispatch_group.command("day")
@day_option("--on", "The day to lay out.")
@click.option("--load", "load_size", default="9 yd3")
@click.option("--rate", default="30 yd3")
@cycle_options
@click.pass_obj
@handle_errors
def day_command(
    context: CliContext,
    on: date,
    load_size: str,
    rate: str,
    load: int,
    out: int,
    site: int,
    back: int,
    wash: int,
) -> None:
    """Every order booked for a day, and which of them collide."""
    cycle = cycle_from(load, out, site, back, wash)
    schedules = []
    with context.register() as register:
        for order in register.orders.open_orders(on):
            if not order.status.accepts_loads:
                continue
            schedules.append(
                schedule_for_order(
                    register,
                    order.number,
                    cycle,
                    load_size=Quantity.parse(load_size),
                    rate=Quantity.parse(rate),
                    start=None,
                )
            )
    click.echo(heading(f"Dispatch, {on.isoformat()}"))
    click.echo(
        render_table(
            (
                Column("order"),
                Column("loads", Align.RIGHT),
                Column("volume", Align.RIGHT),
                Column("first batch"),
                Column("last arrival"),
                Column("trucks", Align.RIGHT),
            ),
            [
                [
                    one.order_number,
                    len(one.loads),
                    one.total_volume.format(1),
                    "-" if one.first_batch is None else f"{one.first_batch:%H:%M}",
                    "-" if one.last_arrival is None else f"{one.last_arrival:%H:%M}",
                    one.trucks_needed,
                ]
                for one in schedules
            ],
        )
    )
    clashes = overlaps(schedules)
    for first, second in clashes:
        click.echo(f"  {first} and {second} want the plant at the same time")
    click.echo(f"{len(schedules)} pour(s), {len(clashes)} overlap(s)")
