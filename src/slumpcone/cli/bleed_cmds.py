"""Commands for bleeding and segregation tests.

A bleeding test is a stack of draws taken over an hour or two, so the recording
command takes the draws as repeated options rather than asking for them one at a
time. A technician runs this once, at the end, off the sheet in front of them.
"""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, window_options
from slumpcone.fresh.bleeding import (
    BleedingError,
    BleedReading,
    BleedTest,
    ColumnSegregation,
    VisualStability,
    worst_bleeder,
)
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


def parse_draw(raw: str) -> BleedReading:
    """One draw, written as minutes:pounds the way the field sheet reads."""
    if ":" not in raw:
        raise BleedingError("BLEED_DRAW_UNREADABLE", f"cannot read the draw {raw!r}")
    left, right = raw.split(":", 1)
    try:
        minutes = float(left.strip())
        water = float(right.strip())
    except ValueError as error:
        raise BleedingError("BLEED_DRAW_UNREADABLE", f"cannot read the draw {raw!r}") from error
    return BleedReading(minutes, Quantity(water, "lb"))


@click.group("bleed")
def bleed_group() -> None:
    """Record and read bleeding and segregation tests."""


@bleed_group.command("record")
@click.argument("ticket")
@day_option("--on", "The day the test was run.")
@click.option("--sample", required=True, help="Mass of the sample, with a unit.")
@click.option("--batch", required=True, help="Mass of the whole batch.")
@click.option("--water", required=True, help="Net mixing water in the batch.")
@click.option("--area", default="0.0785 ft2", help="Surface area of the sample.")
@click.option(
    "--draw",
    "draws",
    multiple=True,
    metavar="MINUTES:POUNDS",
    help="One draw off the surface. Repeat for every draw taken.",
)
@click.option("--technician", default="")
@click.option("--replace", is_flag=True, help="Overwrite a test already on file.")
@click.pass_obj
@handle_errors
def record_command(
    context: CliContext,
    ticket: str,
    on: date,
    sample: str,
    batch: str,
    water: str,
    area: str,
    draws: tuple[str, ...],
    technician: str,
    replace: bool,
) -> None:
    """Record a bleeding test with every draw it took."""
    test = BleedTest(
        ticket,
        Quantity.parse(sample),
        Quantity.parse(batch),
        Quantity.parse(water),
        Quantity.parse(area),
        tuple(parse_draw(raw) for raw in draws),
    )
    with context.register() as register:
        register.bleeding.save(test, on, technician=technician, replace=replace)
    click.echo(test.describe())


@bleed_group.command("show")
@click.argument("ticket")
@day_option("--on")
@click.option("--after", type=float, default=0.0, help="Rate window start, in minutes.")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, ticket: str, on: date, after: float) -> None:
    """Print one bleeding test."""
    with context.register() as register:
        test = register.bleeding.get(ticket, on)
    click.echo(heading(f"Bleeding, {test.ticket_number} on {on.isoformat()}"))
    pairs: list[tuple[str, object]] = [
        ("sample", test.sample_mass.format(1)),
        ("mixing water in sample", test.sample_water.format(2)),
        ("draws", len(test.readings)),
        ("total bled", test.total_water.format(3)),
        ("duration", f"{test.duration_minutes:.0f} min"),
        ("share of mixing water", test.bleeding_percent_of_mixing_water.format(2)),
        ("depth", f"{test.bleeding_volume_per_area:.4f} in3/in2"),
    ]
    if test.readings:
        pairs.append(("rate", test.rate_percent_per_hour(after_minutes=after).format(2)))
    click.echo(render_pairs(pairs))
    if not test.readings:
        return
    click.echo("")
    click.echo(
        render_table(
            (Column("minutes", Align.RIGHT), Column("water", Align.RIGHT)),
            [
                [f"{reading.elapsed_minutes:.0f}", reading.water.format(3)]
                for reading in test.readings
            ],
        )
    )


@bleed_group.command("list")
@window_options
@click.pass_obj
@handle_errors
def list_command(context: CliContext, start: date, end: date) -> None:
    """Bleeding tests in a window, heaviest bleeder called out."""
    with context.register() as register:
        tests = list(register.bleeding.between(start, end))
    click.echo(heading(f"Bleeding, {start.isoformat()} to {end.isoformat()}"))
    click.echo(
        render_table(
            (
                Column("ticket"),
                Column("draws", Align.RIGHT),
                Column("bled", Align.RIGHT),
                Column("share", Align.RIGHT),
                Column("depth", Align.RIGHT),
            ),
            [
                [
                    test.ticket_number,
                    len(test.readings),
                    test.total_water.format(3),
                    test.bleeding_percent_of_mixing_water.format(2),
                    f"{test.bleeding_volume_per_area:.4f}",
                ]
                for test in tests
            ],
        )
    )
    worst = worst_bleeder(tests)
    if worst is not None:
        click.echo("")
        click.echo(f"heaviest: {worst.describe()}")


@bleed_group.command("column")
@click.argument("ticket")
@day_option("--on")
@click.option("--top", required=True, help="Coarse aggregate in the top section.")
@click.option("--bottom", required=True, help="Coarse aggregate in the bottom section.")
@click.option(
    "--visual",
    type=click.IntRange(0, 3),
    default=None,
    help="Visual stability index, 0 through 3.",
)
@click.option("--technician", default="")
@click.pass_obj
@handle_errors
def column_command(
    context: CliContext,
    ticket: str,
    on: date,
    top: str,
    bottom: str,
    visual: int | None,
    technician: str,
) -> None:
    """Record a column segregation result."""
    column = ColumnSegregation(ticket, Quantity.parse(top), Quantity.parse(bottom))
    index = None if visual is None else VisualStability(visual)
    with context.register() as register:
        register.bleeding.save_segregation(column, on, technician=technician, visual=index)
    click.echo(column.describe())
    if index is not None:
        click.echo(f"visual stability {index.value}, {index.note}")


@bleed_group.command("columns")
@window_options
@click.option("--failing", is_flag=True, help="Only results over the ten percent cap.")
@click.pass_obj
@handle_errors
def columns_command(context: CliContext, start: date, end: date, failing: bool) -> None:
    """Column segregation results in a window."""
    with context.register() as register:
        results = list(register.bleeding.segregations_between(start, end))
        if failing:
            results = list(register.bleeding.failing_segregations(results))
    click.echo(
        render_table(
            (
                Column("ticket"),
                Column("top", Align.RIGHT),
                Column("bottom", Align.RIGHT),
                Column("index", Align.RIGHT),
                Column("direction"),
                Column("verdict"),
            ),
            [
                [
                    result.ticket_number,
                    result.top_coarse.format(2),
                    result.bottom_coarse.format(2),
                    result.index.format(1),
                    result.direction,
                    "ok" if result.is_acceptable else "over the cap",
                ]
                for result in results
            ],
        )
    )
    click.echo(f"{len(results)} result(s)")
