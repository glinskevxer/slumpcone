"""Commands for the standards of control and the charts."""

from __future__ import annotations

import click

from slumpcone.cli.common import CliContext, handle_errors
from slumpcone.report.control_chart import (
    individual_chart,
    moving_average_chart,
    moving_range_chart,
    render_control_report,
)
from slumpcone.strength.control import read_control
from slumpcone.textout import heading, render_pairs
from slumpcone.units.quantity import Quantity


@click.group("control")
def control_group() -> None:
    """Read how consistent the plant and the laboratory are."""


@control_group.command("read")
@click.argument("mix_code")
@click.pass_obj
@handle_errors
def read_command(context: CliContext, mix_code: str) -> None:
    """The two variations, and which of them needs attention."""
    with context.register() as register:
        tests = register.strength.tests_for_mix(mix_code)
    reading = read_control(tests)
    click.echo(heading(f"Standards of control for {mix_code.upper()}"))
    click.echo(
        render_pairs(
            [
                ("tests", reading.test_count),
                ("mean", reading.mean.format(0)),
                ("overall deviation", reading.overall_deviation.format(0)),
                ("overall variation", reading.overall_variation.format(1)),
                ("overall grade", str(reading.overall_grade)),
                ("companions per test", reading.companions),
                ("within test deviation", reading.within_test_deviation.format(0)),
                ("within test variation", reading.within_test_variation.format(1)),
                ("within test grade", str(reading.within_test_grade)),
                ("look at", reading.where_the_problem_is),
            ]
        )
    )
    if not reading.is_enough_tests:
        click.echo("")
        click.echo("these grades are read off too few tests to mean much yet")


@control_group.command("charts")
@click.argument("mix_code")
@click.option("--specified", required=True, help='For example "4000 psi".')
@click.pass_obj
@handle_errors
def charts_command(context: CliContext, mix_code: str, specified: str) -> None:
    """All three control charts for one mixture."""
    with context.register() as register:
        tests = register.strength.tests_for_mix(mix_code)
    click.echo(render_control_report(mix_code.upper(), tests, Quantity.parse(specified)))


@control_group.command("chart")
@click.argument("mix_code")
@click.option(
    "--kind",
    type=click.Choice(["individual", "average", "range"]),
    default="individual",
)
@click.option("--specified", default="4000 psi", help="Needed for the average chart.")
@click.pass_obj
@handle_errors
def chart_command(context: CliContext, mix_code: str, kind: str, specified: str) -> None:
    """One chart on its own."""
    with context.register() as register:
        tests = register.strength.tests_for_mix(mix_code)
    if kind == "individual":
        chart = individual_chart(tests)
    elif kind == "average":
        chart = moving_average_chart(tests, Quantity.parse(specified))
    else:
        chart = moving_range_chart(tests)
    click.echo(chart.render())
    if not chart.is_in_control:
        raise click.ClickException(f"{len(chart.outside)} point(s) outside the limits")
