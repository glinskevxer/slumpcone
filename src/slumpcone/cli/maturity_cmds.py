"""Commands for maturity curves and the loggers read against them."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_moment
from slumpcone.strength.maturity import (
    MaturityCurve,
    MaturityPoint,
    TemperatureReading,
    equivalent_age,
    estimate_in_place,
    temperature_time_factor,
)
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature


def _parse_point(text: str) -> MaturityPoint:
    """Read ``240:2200`` as a maturity and a strength."""
    parts = text.split(":")
    if len(parts) != 2:
        raise click.BadParameter(f"{text!r} is not MATURITY:STRENGTH, for example 240:2200")
    try:
        maturity = float(parts[0])
    except ValueError as exc:
        raise click.BadParameter(f"{parts[0]!r} is not a maturity") from exc
    strength = parts[1].strip()
    return MaturityPoint(
        maturity, Quantity.parse(strength if " " in strength else f"{strength} psi")
    )


@click.group("maturity")
def maturity_group() -> None:
    """Fit maturity curves and read in place strength off them."""


@maturity_group.command("fit")
@click.argument("mix_code")
@click.option("--name", required=True, help='For example "summer".')
@click.option("--point", "points", multiple=True, required=True, help="MATURITY:STRENGTH.")
@day_option("--on", "The day the curve was fitted.")
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def fit_command(
    context: CliContext,
    mix_code: str,
    name: str,
    points: tuple[str, ...],
    on: date,
    notes: str,
) -> None:
    """File a strength maturity relationship."""
    curve = MaturityCurve(mix_code, tuple(_parse_point(entry) for entry in points))
    with context.register() as register:
        register.maturity.save_curve(curve, name, on, notes)
    click.echo(curve.describe())


@maturity_group.command("curves")
@click.argument("mix_code")
@click.pass_obj
@handle_errors
def curves_command(context: CliContext, mix_code: str) -> None:
    """Every curve on file for one mixture."""
    with context.register() as register:
        names = register.maturity.curves_for(mix_code)
        rows: list[list[object]] = []
        for name in names:
            curve = register.maturity.curve(mix_code, name)
            low, high = curve.span
            intercept, slope = curve.fit()
            rows.append(
                [
                    name,
                    len(curve.points),
                    f"{low:.0f}",
                    f"{high:.0f}",
                    f"{intercept:.0f} + {slope:.0f} ln(M)",
                ]
            )
    columns = (
        Column("name"),
        Column("points", Align.RIGHT),
        Column("from", Align.RIGHT),
        Column("to", Align.RIGHT),
        Column("fit"),
    )
    click.echo(render_table(columns, rows))


@maturity_group.command("log")
@click.argument("sensor")
@click.option("--placement", required=True)
@click.option("--at", "moment", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--temp", type=float, required=True, help="Reading in degF.")
@click.pass_obj
@handle_errors
def log_command(
    context: CliContext, sensor: str, placement: str, moment: str, temp: float
) -> None:
    """Record one logger reading."""
    reading = TemperatureReading(parse_moment(moment), Temperature(temp, "F"))
    with context.register() as register:
        register.maturity.record_reading(sensor, placement, reading)
    click.echo(
        f"{sensor.upper()} at {reading.at.isoformat(sep=' ', timespec='minutes')}: "
        f"{reading.temperature}"
    )


@maturity_group.command("history")
@click.argument("sensor")
@click.pass_obj
@handle_errors
def history_command(context: CliContext, sensor: str) -> None:
    """One sensor's readings and the maturity they add up to."""
    with context.register() as register:
        readings = register.maturity.readings(sensor)
    if len(readings) < 2:
        raise click.ClickException(
            f"{sensor.upper()} has fewer than two readings, so it has no maturity"
        )
    click.echo(heading(f"Sensor {sensor.upper()}"))
    click.echo(
        render_pairs(
            [
                ("readings", len(readings)),
                ("from", readings[0].at.isoformat(sep=" ", timespec="minutes")),
                ("to", readings[-1].at.isoformat(sep=" ", timespec="minutes")),
                ("temperature time factor", f"{temperature_time_factor(list(readings)):.0f}"),
                ("equivalent age", f"{equivalent_age(list(readings)):.1f} h"),
            ]
        )
    )


@maturity_group.command("estimate")
@click.argument("mix_code")
@click.option("--name", required=True, help="Which curve to read against.")
@click.option("--sensor", required=True)
@click.pass_obj
@handle_errors
def estimate_command(context: CliContext, mix_code: str, name: str, sensor: str) -> None:
    """Read an in place strength off a curve and a logger."""
    with context.register() as register:
        curve = register.maturity.curve(mix_code, name)
        readings = register.maturity.readings(sensor)
    if len(readings) < 2:
        raise click.ClickException(
            f"{sensor.upper()} has fewer than two readings, so it has no maturity"
        )
    estimate = estimate_in_place(curve, list(readings))
    click.echo(estimate.describe())
    if estimate.extrapolated:
        raise click.ClickException("the maturity is past the range the curve was measured over")
