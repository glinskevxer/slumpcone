"""Commands for planning a batch and writing the ticket for it."""

from __future__ import annotations

from datetime import date, datetime

import click

from slumpcone.batching.engine import blocking_reasons, plan_batch
from slumpcone.batching.moisture import AggregateMoisture
from slumpcone.batching.ticket import BatchTicket
from slumpcone.cli.common import (
    CliContext,
    day_option,
    handle_errors,
    parse_moment,
    window_options,
)
from slumpcone.percent import Percent
from slumpcone.report.ticket_audit import render_audit_report, render_ticket
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


def _parse_moisture(text: str) -> AggregateMoisture:
    """Read ``CA-57:1.5:0.7`` as total moisture and absorption."""
    parts = text.split(":")
    if len(parts) != 3:
        raise click.BadParameter(
            f"{text!r} is not CODE:TOTAL:ABSORPTION, for example CA-57:1.5:0.7"
        )
    code, total, absorption = (part.strip() for part in parts)
    try:
        return AggregateMoisture(code, Percent(float(total)), Percent(float(absorption)))
    except ValueError as exc:
        raise click.BadParameter(f"{text!r} has a reading that is not a number") from exc


def _parse_weight(text: str) -> tuple[str, Quantity]:
    """Read ``CEM-I:4235`` as a recorded weight."""
    parts = text.split(":")
    if len(parts) != 2:
        raise click.BadParameter(f"{text!r} is not CODE:WEIGHT, for example CEM-I:4235")
    code, amount = (part.strip() for part in parts)
    return code, Quantity.parse(amount if " " in amount else f"{amount} lb")


def _parse_dose(text: str) -> tuple[str, Quantity]:
    """Read ``AD-AE:61`` as a dispensed dose."""
    parts = text.split(":")
    if len(parts) != 2:
        raise click.BadParameter(f"{text!r} is not CODE:AMOUNT, for example AD-AE:61")
    code, amount = (part.strip() for part in parts)
    return code, Quantity.parse(amount if " " in amount else f"{amount} floz")


@click.group("batch")
def batch_group() -> None:
    """Plan batches and write tickets."""


@batch_group.command("plan")
@click.option("--plant", "plant_code", required=True)
@click.option("--mix", "mix_code", required=True)
@click.option("--volume", required=True, help='For example "9 yd3".')
@click.option("--moisture", "moistures", multiple=True, help="CODE:TOTAL:ABSORPTION.")
@day_option()
@click.pass_obj
@handle_errors
def plan_command(
    context: CliContext,
    plant_code: str,
    mix_code: str,
    volume: str,
    moistures: tuple[str, ...],
    on: date,
) -> None:
    """Work out the weights for one load."""
    readings = {}
    for entry in moistures:
        reading = _parse_moisture(entry)
        readings[reading.material_code] = reading
    with context.register() as register:
        plant = register.plants.get(plant_code)
        design = register.mixes.latest(mix_code)
        catalog = register.materials.load_catalog()
    planned = plan_batch(plant, design, catalog, Quantity.parse(volume), on, readings)
    click.echo(heading(f"Batch sheet, {planned.mix_code} r{planned.mix_revision}"))
    columns = (
        Column("material"),
        Column("design", Align.RIGHT),
        Column("required", Align.RIGHT),
        Column("allowance", Align.RIGHT),
        Column("scale"),
    )
    rows = [
        [
            line.material_code,
            line.design_weight.format(0),
            line.required.format(0),
            line.allowance.format(1),
            line.scale_code or "metered",
        ]
        for line in planned.lines
    ]
    click.echo(render_table(columns, rows))
    if planned.admixture_lines:
        click.echo("")
        dose_rows = [
            [dose.material_code, dose.charge.format(1)] for dose in planned.admixture_lines
        ]
        click.echo(
            render_table((Column("admixture"), Column("charge", Align.RIGHT)), dose_rows)
        )
    click.echo("")
    click.echo(planned.correction.describe())


@batch_group.command("check")
@click.option("--plant", "plant_code", required=True)
@click.option("--mix", "mix_code", required=True)
@click.option("--volume", required=True)
@day_option()
@click.pass_obj
@handle_errors
def check_command(
    context: CliContext, plant_code: str, mix_code: str, volume: str, on: date
) -> None:
    """Say whether a load can be batched, without batching it."""
    with context.register() as register:
        plant = register.plants.get(plant_code)
        design = register.mixes.latest(mix_code)
        catalog = register.materials.load_catalog()
    reasons = blocking_reasons(plant, design, catalog, Quantity.parse(volume), on)
    if not reasons:
        click.echo("nothing stops this batch")
        return
    for reason in reasons:
        click.echo(f"  {reason}")
    raise click.ClickException(f"{len(reasons)} reason(s)")


@batch_group.command("ticket")
@click.argument("number")
@click.option("--plant", "plant_code", required=True)
@click.option("--mix", "mix_code", required=True)
@click.option("--volume", required=True)
@click.option("--at", "batched_at", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--truck", "truck_code", default=None)
@click.option("--purchaser", default=None)
@click.option("--project", default=None)
@click.option("--moisture", "moistures", multiple=True, help="CODE:TOTAL:ABSORPTION.")
@click.option("--actual", "actuals", multiple=True, help="CODE:WEIGHT as recorded.")
@click.option("--dose", "doses", multiple=True, help="CODE:AMOUNT as dispensed.")
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def ticket_command(
    context: CliContext,
    number: str,
    plant_code: str,
    mix_code: str,
    volume: str,
    batched_at: str | None,
    truck_code: str | None,
    purchaser: str | None,
    project: str | None,
    moistures: tuple[str, ...],
    actuals: tuple[str, ...],
    doses: tuple[str, ...],
    notes: str,
) -> None:
    """Batch a load and file its ticket."""
    moment = datetime.now() if batched_at is None else parse_moment(batched_at)
    readings = {}
    for entry in moistures:
        reading = _parse_moisture(entry)
        readings[reading.material_code] = reading
    recorded = dict(_parse_weight(entry) for entry in actuals)
    dispensed = dict(_parse_dose(entry) for entry in doses)
    with context.register() as register:
        plant = register.plants.get(plant_code)
        design = register.mixes.latest(mix_code)
        catalog = register.materials.load_catalog()
        planned = plan_batch(
            plant, design, catalog, Quantity.parse(volume), moment.date(), readings
        )
        ticket = BatchTicket.from_plan(
            planned,
            number,
            moment,
            recorded,
            dispensed,
            truck_code=truck_code,
            purchaser=purchaser,
            project=project,
            notes=notes,
        )
        register.batches.save(ticket)
    click.echo(ticket.describe())
    for result in ticket.out_of_tolerance:
        click.echo(f"  {result.describe()}")


@batch_group.command("show")
@click.argument("number")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, number: str) -> None:
    """Print one ticket."""
    with context.register() as register:
        ticket = register.batches.get(number)
    click.echo(render_ticket(ticket))


@batch_group.command("audit")
@window_options
@click.option("--plant", "plant_code", default=None)
@click.pass_obj
@handle_errors
def audit_command(context: CliContext, start: date, end: date, plant_code: str | None) -> None:
    """Audit a run of tickets."""
    with context.register() as register:
        tickets = (
            register.batches.between(start, end)
            if plant_code is None
            else register.batches.for_plant(plant_code, start, end)
        )
    click.echo(render_audit_report(list(tickets)))


@batch_group.command("day")
@day_option()
@click.pass_obj
@handle_errors
def day_command(context: CliContext, on: date) -> None:
    """What was recorded on one day."""
    with context.register() as register:
        summary = register.day_summary(on)
    click.echo(heading(f"Register on {on.isoformat()}"))
    click.echo(render_pairs(list(summary.items())))
