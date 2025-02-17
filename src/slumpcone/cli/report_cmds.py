"""Commands that print the reports somebody has to be handed."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, window_options
from slumpcone.fresh.acceptance import judge_load
from slumpcone.report.compliance import (
    from_catalog,
    from_plant,
    from_submittals,
    from_trucks,
    render_compliance_report,
)
from slumpcone.report.fleet import render_fleet_report
from slumpcone.report.nonconformance import (
    counts_by_severity,
    from_haul,
    from_load,
    from_ticket,
    register_from,
    render_register,
)
from slumpcone.report.production import render_production_report
from slumpcone.report.yield_report import render_yield_report
from slumpcone.spec.frequency import check_frequency
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@click.group("report")
def report_group() -> None:
    """Print the reports a plant has to produce."""


@report_group.command("production")
@window_options
@click.pass_obj
@handle_errors
def production_command(context: CliContext, start: date, end: date) -> None:
    """Volume, loads and returned concrete over a window."""
    with context.register() as register:
        tickets = register.batches.between(start, end)
        deliveries = register.deliveries.between(start, end)
    click.echo(render_production_report(list(tickets), list(deliveries), start=start, end=end))


@report_group.command("nonconformance")
@window_options
@click.pass_obj
@handle_errors
def nonconformance_command(context: CliContext, start: date, end: date) -> None:
    """Everything the register objects to over a window."""
    groups = []
    with context.register() as register:
        tickets = register.batches.between(start, end)
        for ticket in tickets:
            groups.append(from_ticket(ticket))
            tests = register.fresh.for_ticket(ticket.number)
            if tests:
                design = register.mixes.get(ticket.mix_code, ticket.mix_revision)
                groups.append(
                    from_load(
                        judge_load(ticket.number, tests, design), ticket.batched_at.date()
                    )
                )
            try:
                delivery = register.deliveries.get(ticket.number)
            except Exception:
                continue
            verdict = delivery.haul_verdict()
            if verdict is not None:
                groups.append(from_haul(verdict, ticket.number, ticket.batched_at.date()))
    entries = register_from(groups)
    click.echo(heading(f"Non conformance, {start.isoformat()} to {end.isoformat()}"))
    click.echo(
        render_pairs(
            [(str(severity), count) for severity, count in counts_by_severity(entries).items()]
        )
    )
    click.echo("")
    click.echo(render_register(entries))


@report_group.command("compliance")
@day_option()
@click.option("--within", type=int, default=45, help="Days ahead to look.")
@click.pass_obj
@handle_errors
def compliance_command(context: CliContext, on: date, within: int) -> None:
    """Everything that expires, in one list."""
    with context.register() as register:
        catalog = register.materials.load_catalog()
        items = list(from_catalog(catalog, on))
        for plant in register.plants.all():
            items.extend(from_plant(plant))
        items.extend(from_trucks(register.deliveries.trucks()))
        for project in register.projects.all():
            items.extend(from_submittals(register.projects.submittals_for(project.code)))
    click.echo(render_compliance_report(items, on, horizon_days=within))


@report_group.command("yield")
@click.argument("mix_code")
@window_options
@click.pass_obj
@handle_errors
def yield_command(context: CliContext, mix_code: str, start: date, end: date) -> None:
    """Relative yield and gravimetric air for one mixture's loads."""
    with context.register() as register:
        design = register.mixes.latest(mix_code)
        catalog = register.materials.load_catalog()
        gravities = {
            material.code: material.specific_gravity
            for material in catalog
            if material.specific_gravity is not None
        }
        tickets = {
            ticket.number
            for ticket in register.batches.for_mix(design.code)
            if start <= ticket.batched_at.date() <= end
        }
        tests = [
            test for test in register.fresh.between(start, end) if test.ticket_number in tickets
        ]
    click.echo(render_yield_report(design.code, tests, design.proportions, gravities))


@report_group.command("fleet")
@window_options
@click.option("--shift", type=float, default=600.0, help="Shift length in minutes.")
@click.option("--cycle", type=float, default=90.0, help="Expected cycle in minutes.")
@click.pass_obj
@handle_errors
def fleet_command(
    context: CliContext, start: date, end: date, shift: float, cycle: float
) -> None:
    """Where the trucks went and where the time went."""
    with context.register() as register:
        deliveries = register.deliveries.between(start, end)
        tickets = register.batches.between(start, end)
    click.echo(
        render_fleet_report(
            list(deliveries),
            list(tickets),
            shift_minutes=shift,
            cycle_minutes=cycle,
        )
    )


@report_group.command("frequency")
@window_options
@click.option("--area", default=None, help='Slab surface area, "24000 ft2".')
@click.pass_obj
@handle_errors
def frequency_command(context: CliContext, start: date, end: date, area: str | None) -> None:
    """Whether each mixture was sampled often enough over a window."""
    surface = None if area is None else Quantity.parse(area)
    rows: list[list[object]] = []
    with context.register() as register:
        tickets = register.batches.between(start, end)
        by_mix: dict[str, list[object]] = {}
        for ticket in tickets:
            by_mix.setdefault(ticket.mix_code, []).append(ticket)
        for mix_code, placed in sorted(by_mix.items()):
            volume = Quantity.zero("yd3")
            days: set[date] = set()
            for entry in placed:
                volume = volume + entry.volume.to("yd3")  # type: ignore[attr-defined]
                days.add(entry.batched_at.date())  # type: ignore[attr-defined]
            taken = len(register.strength.tests_for_mix(mix_code))
            finding = check_frequency(mix_code, volume, len(days), taken, surface)
            rows.append(
                [
                    finding.class_code,
                    finding.volume.format(1),
                    len(days),
                    finding.requirement.required,
                    finding.taken,
                    finding.requirement.governing_rule,
                    "yes" if finding.conforms else f"{finding.shortfall} short",
                ]
            )
    columns = (
        Column("mix"),
        Column("volume", Align.RIGHT),
        Column("days", Align.RIGHT),
        Column("required", Align.RIGHT),
        Column("taken", Align.RIGHT),
        Column("governed by"),
        Column("ok"),
    )
    click.echo(heading(f"Sampling frequency, {start.isoformat()} to {end.isoformat()}"))
    click.echo(render_table(columns, rows))
