"""Commands for moisture probe calibration."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, window_options
from slumpcone.cli.output import listing, page
from slumpcone.percent import Percent
from slumpcone.plant.probe import ProbeCheck
from slumpcone.textout import Align, Column, heading, render_pairs


@click.group("probe")
def probe_group() -> None:
    """Moisture probes and the checks that keep them honest."""


@probe_group.command("check")
@click.argument("probe")
@click.option("--plant", "plant_code", required=True)
@click.option("--probe-read", "probe_reading", type=float, required=True)
@click.option("--oven", "oven_reading", type=float, required=True)
@day_option("--on", "The day the check was run.")
@click.option("--technician", default="")
@click.option("--notes", default="")
@click.option("--replace", is_flag=True)
@click.pass_obj
@handle_errors
def check_command(
    context: CliContext,
    probe: str,
    plant_code: str,
    probe_reading: float,
    oven_reading: float,
    on: date,
    technician: str,
    notes: str,
    replace: bool,
) -> None:
    """Record a probe check against an oven dried sample."""
    check = ProbeCheck(probe, on, Percent(probe_reading), Percent(oven_reading), technician)
    with context.register() as register:
        register.probes.save(check, plant_code, notes=notes, replace=replace)
        context.note(register, "probe.check", check.probe_code, check.describe())
    click.echo(check.describe())


@probe_group.command("show")
@click.argument("probe")
@click.option("--plant", "plant_code", required=True)
@day_option("--on")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, probe: str, plant_code: str, on: date) -> None:
    """One probe's history and where it stands today."""
    with context.register() as register:
        history = register.probes.history(plant_code, probe)
    page(
        f"Probe {history.probe_code}",
        [
            ("checks", len(history.checks)),
            ("mean offset", f"{history.mean_offset.value:+.2f} points"),
            ("drift", f"{history.drift.value:.2f} points"),
            ("drifting", "yes" if history.is_drifting else "no"),
            ("standing", str(history.standing(on))),
            ("may batch", "yes" if history.standing(on).may_batch else "no"),
        ],
        (
            Column("checked"),
            Column("probe", Align.RIGHT),
            Column("oven", Align.RIGHT),
            Column("offset", Align.RIGHT),
            Column("verdict"),
            Column("technician"),
        ),
        [
            [
                one.checked_on.isoformat(),
                one.probe_reading.format(2),
                one.oven_reading.format(2),
                f"{one.offset.value:+.2f}",
                "ok" if one.is_within_limit else "out of limit",
                one.technician or "-",
            ]
            for one in history.checks
        ],
    )


@probe_group.command("correct")
@click.argument("probe")
@click.argument("reading", type=float)
@click.option("--plant", "plant_code", required=True)
@day_option("--on")
@click.pass_obj
@handle_errors
def correct_command(
    context: CliContext, probe: str, reading: float, plant_code: str, on: date
) -> None:
    """Apply a probe's standing offset to a reading."""
    with context.register() as register:
        history = register.probes.history(plant_code, probe)
        corrected = history.corrected(Percent(reading), on)
    click.echo(
        render_pairs(
            [
                ("probe", history.probe_code),
                ("as read", Percent(reading).format(2)),
                ("offset", f"{history.mean_offset.value:+.2f} points"),
                ("corrected", corrected.format(2)),
            ]
        )
    )


@probe_group.command("list")
@click.option("--plant", "plant_code", required=True)
@day_option("--on")
@click.option("--attention", is_flag=True, help="Only the ones to do something about.")
@click.pass_obj
@handle_errors
def list_command(context: CliContext, plant_code: str, on: date, attention: bool) -> None:
    """Every probe at one plant."""
    with context.register() as register:
        histories = (
            register.probes.needing_attention(plant_code, on)
            if attention
            else register.probes.histories(plant_code)
        )
    click.echo(heading(f"Probes, {plant_code.strip().upper()} on {on.isoformat()}"))
    listing(
        (
            Column("probe"),
            Column("checks", Align.RIGHT),
            Column("last"),
            Column("offset", Align.RIGHT),
            Column("drift", Align.RIGHT),
            Column("standing"),
        ),
        [
            [
                one.probe_code,
                len(one.checks),
                "never" if one.latest is None else one.latest.checked_on.isoformat(),
                f"{one.mean_offset.value:+.2f}",
                f"{one.drift.value:.2f}",
                str(one.standing(on)),
            ]
            for one in histories
        ],
        "probe",
    )
    with context.register() as register:
        blocked = register.probes.needing_attention(plant_code, on)
    if blocked:
        names = ", ".join(one.probe_code for one in blocked)
        click.echo(f"do not batch off: {names}")


@probe_group.command("checks")
@click.option("--plant", "plant_code", required=True)
@window_options
@click.pass_obj
@handle_errors
def checks_command(context: CliContext, plant_code: str, start: date, end: date) -> None:
    """Every check run in a window."""
    with context.register() as register:
        checks = register.probes.checks_between(plant_code, start, end)
    for one in checks:
        click.echo(f"  {one.describe()}")
    click.echo(f"{len(checks)} check(s)")
