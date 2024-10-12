"""Commands for the tests a technician runs at the point of discharge."""

from __future__ import annotations

from datetime import date, datetime

import click

from slumpcone.cli.common import CliContext, handle_errors, parse_moment, window_options
from slumpcone.fresh.acceptance import judge_load
from slumpcone.fresh.sampling import Sample, check_sample
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from slumpcone.units.temperature import Temperature


@click.group("field")
def field_group() -> None:
    """Record and judge fresh property tests."""


@field_group.command("record")
@click.argument("ticket")
@click.option("--at", "taken_at", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--slump", default=None, help='For example "4.5 in".')
@click.option("--air", type=float, default=None, help="Air content, percent.")
@click.option("--air-method", default="pressure", help="pressure or volumetric.")
@click.option("--temp", type=float, default=None, help="Concrete temperature, degF.")
@click.option("--unit-weight", type=float, default=None, help="Density, lb/ft3.")
@click.option("--discharged", default=None, help='Discharged before the sample, "3 yd3".')
@click.option("--technician", default=None)
@click.option("--retest", is_flag=True, help="This is the second sample on a property.")
@click.pass_obj
@handle_errors
def record_command(
    context: CliContext,
    ticket: str,
    taken_at: str | None,
    slump: str | None,
    air: float | None,
    air_method: str,
    temp: float | None,
    unit_weight: float | None,
    discharged: str | None,
    technician: str | None,
    retest: bool,
) -> None:
    """Record every reading taken off one sample."""
    moment = datetime.now() if taken_at is None else parse_moment(taken_at)
    before = None if discharged is None else Quantity.parse(discharged)
    air_kind = (
        FreshTestKind.AIR_VOLUMETRIC
        if air_method.strip().lower().startswith("vol")
        else FreshTestKind.AIR_PRESSURE
    )
    built: list[FreshTest] = []
    if slump is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.SLUMP,
                moment,
                slump=Quantity.parse(slump),
                discharged_before_sample=before,
                technician=technician,
                is_retest=retest,
            )
        )
    if air is not None:
        built.append(
            FreshTest(
                ticket,
                air_kind,
                moment,
                air=Percent(air),
                discharged_before_sample=before,
                technician=technician,
                is_retest=retest,
            )
        )
    if temp is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.TEMPERATURE,
                moment,
                temperature=Temperature(temp, "F"),
                discharged_before_sample=before,
                technician=technician,
                is_retest=retest,
            )
        )
    if unit_weight is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.UNIT_WEIGHT,
                moment,
                unit_weight=MassPerVolume(unit_weight, "lb", "ft3"),
                discharged_before_sample=before,
                technician=technician,
                is_retest=retest,
            )
        )
    if not built:
        raise click.UsageError("give at least one reading")
    with context.register() as register:
        register.fresh.save_all(built)
    for test in built:
        click.echo(test.describe())


@field_group.command("list")
@click.argument("ticket")
@click.pass_obj
@handle_errors
def list_command(context: CliContext, ticket: str) -> None:
    """List every test taken on one load."""
    with context.register() as register:
        tests = register.fresh.for_ticket(ticket)
    columns = (
        Column("taken"),
        Column("method"),
        Column("reading", Align.RIGHT),
        Column("retest"),
        Column("technician"),
    )
    rows = [
        [
            test.taken_at.isoformat(sep=" ", timespec="minutes"),
            str(test.kind),
            test.value_text,
            "yes" if test.is_retest else "no",
            test.technician or "-",
        ]
        for test in tests
    ]
    click.echo(render_table(columns, rows))


@field_group.command("judge")
@click.argument("ticket")
@click.pass_obj
@handle_errors
def judge_command(context: CliContext, ticket: str) -> None:
    """Judge one load against its mix design's bands."""
    with context.register() as register:
        stored = register.batches.get(ticket)
        design = register.mixes.get(stored.mix_code, stored.mix_revision)
        tests = register.fresh.for_ticket(ticket)
    verdict = judge_load(stored.number, tests, design)
    click.echo(verdict.describe())


@field_group.command("sample")
@click.argument("ticket")
@click.option("--load", required=True, help='The load size, "9 yd3".')
@click.option("--discharged", required=True, help='Discharged before the sample, "3 yd3".')
@click.option("--portions", type=int, default=2)
@click.option("--span", type=float, default=0.0, help="Minutes between the portions.")
@click.option("--delay", type=float, default=0.0, help="Minutes before testing started.")
@click.option("--for-specimens", is_flag=True, help="Judge against the moulding limit.")
@click.pass_obj
@handle_errors
def sample_command(
    context: CliContext,
    ticket: str,
    load: str,
    discharged: str,
    portions: int,
    span: float,
    delay: float,
    for_specimens: bool,
) -> None:
    """Say whether a sample can carry an acceptance result."""
    sample = Sample(
        ticket,
        Quantity.parse(load),
        Quantity.parse(discharged),
        portions,
        span,
        delay,
    )
    faults = check_sample(sample, for_specimens=for_specimens)
    click.echo(
        render_pairs(
            [
                ("ticket", sample.ticket_number),
                ("through the load", sample.discharged_fraction.format(0)),
                ("still in the drum", sample.remaining.format(2)),
                ("acceptance sample", "no" if faults else "yes"),
            ]
        )
    )
    for fault in faults:
        click.echo(f"  {fault}")


@field_group.command("outstanding")
@window_options
@click.pass_obj
@handle_errors
def outstanding_command(context: CliContext, start: date, end: date) -> None:
    """Loads in a window whose fresh tests have not settled."""
    with context.register() as register:
        tickets = register.batches.between(start, end)
        rows: list[list[object]] = []
        for ticket in tickets:
            tests = register.fresh.for_ticket(ticket.number)
            design = register.mixes.get(ticket.mix_code, ticket.mix_revision)
            verdict = judge_load(ticket.number, tests, design)
            rows.append(
                [
                    ticket.number,
                    ticket.batched_at.isoformat(sep=" ", timespec="minutes"),
                    str(verdict.outcome),
                ]
            )
    click.echo(heading("Fresh test outcomes"))
    click.echo(render_table((Column("ticket"), Column("batched"), Column("outcome")), rows))
