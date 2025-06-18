"""Commands for laying pours out and putting trucks against them."""

from __future__ import annotations

import functools
from datetime import date, datetime, time, timedelta
from typing import Any, cast

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


CYCLE_LEGS = (
    ("--wash", 5, "Washing out after the load."),
    ("--back", 20, "Driving back to the plant."),
    ("--site", 15, "On site, waiting and discharging."),
    ("--out", 20, "Driving out to the job."),
    ("--load", 10, "Loading at the plant."),
)


def cycle_from(load: int, out: int, site: int, back: int, wash: int) -> CycleTime:
    """A cycle out of five minute counts."""
    return CycleTime(
        timedelta(minutes=load),
        timedelta(minutes=out),
        timedelta(minutes=site),
        timedelta(minutes=back),
        timedelta(minutes=wash),
    )


def cycle_options(command: F) -> F:
    """The five legs of a truck cycle, collapsed into one ``cycle`` argument.

    Every command that lays a pour out takes the same five minute counts and
    every one of them turned them into a :class:`CycleTime` on its first line.
    Five parameters in four signatures is twenty places for the legs to end up
    in the wrong order, which is a bug nothing catches because every leg is an
    integer number of minutes.

    So the decorator both declares the options and does the assembly, and the
    commands underneath it take a cycle. The wrapper sits inside the click
    decorators, which means click still sees the five options and the command
    body never does.
    """

    @functools.wraps(command)
    def wrapper(
        *args: Any,
        load: int,
        out: int,
        site: int,
        back: int,
        wash: int,
        **kwargs: Any,
    ) -> Any:
        return command(*args, cycle=cycle_from(load, out, site, back, wash), **kwargs)

    decorated: F = cast(F, wrapper)
    for name, default, blurb in CYCLE_LEGS:
        decorated = click.option(name, type=int, default=default, help=f"{blurb} Minutes.")(
            decorated
        )
    return decorated


def schedule_for_order(
    register: Register,
    order_number: str,
    cycle: CycleTime,
    *,
    load_size: Quantity,
    rate: Quantity | None,
    start: datetime | None,
    use_profile: bool = True,
) -> Schedule:
    """Lay a booked order out, filling in what the booking did not say.

    The cycle handed in is the caller's guess. A job with a profile measured off
    its own tickets beats a guess every time, so the profile wins unless the
    caller has explicitly said not to use it.
    """
    order = register.orders.get(order_number)
    if use_profile:
        cycle = register.haul.get_or(order.project_code, cycle)
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
@click.option("--ignore-profile", is_flag=True, help="Use the given cycle, not the job's.")
@cycle_options
@click.pass_obj
@handle_errors
def schedule_command(
    context: CliContext,
    order_number: str,
    load_size: str,
    rate: str | None,
    start: str | None,
    ignore_profile: bool,
    cycle: CycleTime,
) -> None:
    """Lay one order out into loads."""
    with context.register() as register:
        found = schedule_for_order(
            register,
            order_number,
            cycle,
            load_size=Quantity.parse(load_size),
            rate=None if rate is None else Quantity.parse(rate),
            start=None if start is None else parse_moment(start),
            use_profile=not ignore_profile,
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
    cycle: CycleTime,
) -> None:
    """Put trucks against one order."""
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
    cycle: CycleTime,
) -> None:
    """What every truck is doing at one moment."""
    when = parse_moment(moment)
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
    cycle: CycleTime,
) -> None:
    """Every order booked for a day, and which of them collide."""
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


@dispatch_group.command("haul")
@click.argument("project_code")
@cycle_options
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def haul_command(
    context: CliContext,
    project_code: str,
    cycle: CycleTime,
    notes: str,
) -> None:
    """File a haul profile for one job by hand."""
    with context.register() as register:
        register.haul.save(project_code, cycle, notes=notes)
    click.echo(f"{project_code.strip().upper()}: {cycle.describe()}")


@dispatch_group.command("fit")
@click.argument("project_code")
@day_option("--on", "The day to record the fit against.")
@click.option("--load", "load_minutes", type=int, default=10)
@click.option("--wash", "wash_minutes", type=int, default=5)
@click.option(
    "--label",
    default=None,
    help="The job name written on the tickets. Defaults to the project code.",
)
@click.pass_obj
@handle_errors
def fit_command(
    context: CliContext,
    project_code: str,
    on: date,
    load_minutes: int,
    wash_minutes: int,
    label: str | None,
) -> None:
    """Fit a haul profile from the deliveries already on file for a job.

    A ticket carries the job as the free text the dispatcher typed, not as the
    project code, and the two are rarely the same string. So the label the
    tickets actually carry is an option, and it defaults to the code for the
    plants where somebody was disciplined about it.
    """
    wanted = (label or project_code).strip().casefold()
    with context.register() as register:
        tickets = {
            ticket.number
            for ticket in register.batches.between(date(1900, 1, 1), on)
            if ticket.project is not None and ticket.project.casefold() == wanted
        }
        deliveries = [
            delivery
            for delivery in register.deliveries.between(date(1900, 1, 1), on)
            if delivery.ticket_number in tickets
        ]
        cycle = register.haul.fit(
            project_code,
            deliveries,
            loading=timedelta(minutes=load_minutes),
            wash=timedelta(minutes=wash_minutes),
            measured_on=on,
        )
    click.echo(f"fitted off {len(deliveries)} delivery record(s)")
    click.echo(cycle.describe())


@dispatch_group.command("profiles")
@click.pass_obj
@handle_errors
def profiles_command(context: CliContext) -> None:
    """Every haul profile on file."""
    with context.register() as register:
        rows = []
        for code in register.haul.projects():
            cycle = register.haul.get(code)
            measured, count, notes = register.haul.provenance(code)
            rows.append(
                [
                    code,
                    f"{cycle.loading.total_seconds() / 60:.0f}",
                    f"{cycle.haul_out.total_seconds() / 60:.0f}",
                    f"{cycle.on_site.total_seconds() / 60:.0f}",
                    f"{cycle.haul_back.total_seconds() / 60:.0f}",
                    f"{cycle.wash.total_seconds() / 60:.0f}",
                    "-" if measured is None else measured.isoformat(),
                    count,
                    notes,
                ]
            )
    click.echo(
        render_table(
            (
                Column("job"),
                Column("load", Align.RIGHT),
                Column("out", Align.RIGHT),
                Column("site", Align.RIGHT),
                Column("back", Align.RIGHT),
                Column("wash", Align.RIGHT),
                Column("measured"),
                Column("records", Align.RIGHT),
                Column("source"),
            ),
            rows,
        )
    )
    click.echo(f"{len(rows)} profile(s)")


@dispatch_group.command("forget")
@click.argument("project_code")
@click.pass_obj
@handle_errors
def forget_command(context: CliContext, project_code: str) -> None:
    """Drop a haul profile."""
    with context.register() as register:
        register.haul.forget(project_code)
    click.echo(f"{project_code.strip().upper()} profile dropped")
