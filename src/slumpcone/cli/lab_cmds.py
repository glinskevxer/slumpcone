"""Commands for the laboratory: sets, cylinders, breaks and the strength record."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_moment
from slumpcone.report.strength_report import render_report
from slumpcone.strength.acceptance import evaluate_strength
from slumpcone.strength.breaks import BreakResult, FractureType
from slumpcone.strength.specimen import (
    CureCondition,
    Specimen,
    SpecimenPurpose,
    SpecimenSize,
)
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@click.group("lab")
def lab_group() -> None:
    """Cast cylinders, break them and read the record."""


@lab_group.command("set")
@click.argument("set_code")
@click.option("--mix", "mix_code", required=True)
@click.option("--revision", type=int, default=1)
@click.option("--sampled", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--size", default="4x8")
@click.option("--cure", default="standard")
@click.option("--purpose", default="acceptance")
@click.option("--ticket", "ticket_number", default=None)
@click.option("--project", default=None)
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def set_command(
    context: CliContext,
    set_code: str,
    mix_code: str,
    revision: int,
    sampled: str,
    size: str,
    cure: str,
    purpose: str,
    ticket_number: str | None,
    project: str | None,
    notes: str,
) -> None:
    """Open a set of specimens against a mix design."""
    with context.register() as register:
        register.strength.open_set(
            set_code,
            mix_code,
            revision,
            parse_moment(sampled),
            size=SpecimenSize.parse(size),
            cure=CureCondition.parse(cure),
            purpose=SpecimenPurpose.parse(purpose),
            ticket_number=ticket_number,
            project=project,
            notes=notes,
        )
    click.echo(f"set {set_code.upper()} opened against {mix_code.upper()} r{revision}")


@lab_group.command("cylinder")
@click.argument("code")
@click.option("--set", "set_code", required=True)
@click.option("--ticket", "ticket_number", required=True)
@click.option("--cast", "cast_at", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--age", type=int, default=28, help="Planned test age in days.")
@click.option("--size", default="4x8")
@click.option("--cure", default="standard")
@click.option("--purpose", default="acceptance")
@click.pass_obj
@handle_errors
def cylinder_command(
    context: CliContext,
    code: str,
    set_code: str,
    ticket_number: str,
    cast_at: str,
    age: int,
    size: str,
    cure: str,
    purpose: str,
) -> None:
    """Cast one cylinder into a set."""
    specimen = Specimen(
        code,
        set_code,
        ticket_number,
        parse_moment(cast_at),
        SpecimenSize.parse(size),
        CureCondition.parse(cure),
        SpecimenPurpose.parse(purpose),
        age,
    )
    with context.register() as register:
        register.strength.save_specimen(specimen)
    click.echo(specimen.describe())


@lab_group.command("break")
@click.argument("specimen_code")
@click.option("--tested", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--age", type=float, required=True, help="Age at test in days.")
@click.option("--d1", "diameter_one", required=True, help='For example "4.00 in".')
@click.option("--d2", "diameter_two", default=None, help="The second diameter.")
@click.option("--length", default=None, help="Measured length.")
@click.option("--load", "max_load", required=True, help='Peak load, "63000 lbf".')
@click.option("--fracture", default="cone")
@click.option("--by", "tested_by", default=None)
@click.pass_obj
@handle_errors
def break_command(
    context: CliContext,
    specimen_code: str,
    tested: str,
    age: float,
    diameter_one: str,
    diameter_two: str | None,
    length: str | None,
    max_load: str,
    fracture: str,
    tested_by: str | None,
) -> None:
    """Record a break against a cylinder."""
    first = Quantity.parse(diameter_one)
    second = first if diameter_two is None else Quantity.parse(diameter_two)
    result = BreakResult(
        specimen_code,
        parse_moment(tested),
        age,
        first,
        second,
        first * 2.0 if length is None else Quantity.parse(length),
        Quantity.parse(max_load),
        FractureType.parse(fracture),
        tested_by,
    )
    with context.register() as register:
        register.strength.save_break(result)
    click.echo(result.describe())
    if result.is_out_of_round:
        click.echo("  this cylinder should not have been tested")


@lab_group.command("pending")
@day_option()
@click.pass_obj
@handle_errors
def pending_command(context: CliContext, on: date) -> None:
    """Cylinders that are due or overdue and have not been broken."""
    with context.register() as register:
        specimens = register.strength.pending_breaks(on)
    columns = (
        Column("specimen"),
        Column("set"),
        Column("cast"),
        Column("age", Align.RIGHT),
        Column("due"),
    )
    rows = [
        [
            specimen.code,
            specimen.set_code,
            specimen.cast_at.date().isoformat(),
            specimen.age_days,
            specimen.due_at.date().isoformat(),
        ]
        for specimen in specimens
    ]
    click.echo(render_table(columns, rows))


@lab_group.command("test")
@click.argument("set_code")
@click.pass_obj
@handle_errors
def test_command(context: CliContext, set_code: str) -> None:
    """Show the strength test one set adds up to."""
    with context.register() as register:
        built = register.strength.strength_test(set_code)
    click.echo(heading(built.describe()))
    click.echo(
        render_pairs(
            [
                ("mix", built.mix_code),
                ("result", built.average.format(0)),
                ("lowest", built.lowest.format(0)),
                ("highest", built.highest.format(0)),
                ("spread", built.within_test_range_percent.format(1)),
                ("complete", "yes" if built.is_complete else "no"),
                ("counts for acceptance", "yes" if built.counts_for_acceptance else "no"),
            ]
        )
    )
    for concern in built.concerns():
        click.echo(f"  {concern}")


@lab_group.command("strength")
@click.argument("mix_code")
@click.option("--specified", required=True, help='For example "4000 psi".')
@click.pass_obj
@handle_errors
def strength_command(context: CliContext, mix_code: str, specified: str) -> None:
    """The strength record for one mixture."""
    with context.register() as register:
        tests = register.strength.tests_for_mix(mix_code)
    report = evaluate_strength(mix_code.upper(), tests, Quantity.parse(specified))
    click.echo(render_report(report))


@lab_group.command("project-strength")
@click.argument("project")
@click.option("--specified", required=True)
@click.pass_obj
@handle_errors
def project_strength_command(context: CliContext, project: str, specified: str) -> None:
    """The strength record for one job, across every mixture on it."""
    with context.register() as register:
        tests = register.strength.tests_for_project(project)
    report = evaluate_strength(project, tests, Quantity.parse(specified))
    click.echo(render_report(report))
