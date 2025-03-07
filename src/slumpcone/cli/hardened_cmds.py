"""Commands for flexural beams and for coring a structure."""

from __future__ import annotations

import click

from slumpcone.cli.common import CliContext, handle_errors, parse_moment
from slumpcone.strength.cores import Core, CoreCondition
from slumpcone.strength.flexural import (
    FlexuralBreak,
    average_rupture,
    equivalent_compressive,
    estimated_rupture,
)
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@click.group("beam")
def beam_group() -> None:
    """Break beams and read the modulus of rupture."""


@beam_group.command("break")
@click.argument("specimen_code")
@click.option("--set", "set_code", required=True)
@click.option("--mix", "mix_code", required=True)
@click.option("--tested", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--age", type=float, default=28.0)
@click.option("--span", default="18 in")
@click.option("--width", default="6 in")
@click.option("--depth", default="6 in")
@click.option("--load", "max_load", required=True, help='Peak load, "6200 lbf".')
@click.option("--fracture-at", required=True, help="Distance to the nearer support.")
@click.pass_obj
@handle_errors
def break_command(
    context: CliContext,
    specimen_code: str,
    set_code: str,
    mix_code: str,
    tested: str,
    age: float,
    span: str,
    width: str,
    depth: str,
    max_load: str,
    fracture_at: str,
) -> None:
    """Record one beam."""
    beam = FlexuralBreak(
        specimen_code,
        Quantity.parse(span),
        Quantity.parse(width),
        Quantity.parse(depth),
        Quantity.parse(max_load),
        Quantity.parse(fracture_at),
        age,
    )
    with context.register() as register:
        register.hardened.save_beam(beam, set_code, mix_code, parse_moment(tested))
    click.echo(beam.describe())


@beam_group.command("set")
@click.argument("set_code")
@click.pass_obj
@handle_errors
def set_command(context: CliContext, set_code: str) -> None:
    """The beams in one set and the average they give."""
    with context.register() as register:
        beams = register.hardened.beams_in(set_code)
    if not beams:
        raise click.ClickException(f"no beams on file for set {set_code.upper()!r}")
    for beam in beams:
        click.echo(beam.describe())
    usable = [beam for beam in beams if beam.is_usable]
    if not usable:
        raise click.ClickException("every beam broke well outside the middle third")
    result = average_rupture(list(beams))
    click.echo("")
    click.echo(
        render_pairs(
            [
                ("beams", len(beams)),
                ("counted", len(usable)),
                ("modulus of rupture", result.format(0)),
                ("equivalent compressive", equivalent_compressive(result).format(0)),
            ]
        )
    )


@beam_group.command("estimate")
@click.option("--compressive", default=None, help='For example "4000 psi".')
@click.option("--rupture", default=None, help='For example "600 psi".')
@click.option("--factor", type=float, default=7.5)
@click.pass_obj
@handle_errors
def estimate_command(
    context: CliContext, compressive: str | None, rupture: str | None, factor: float
) -> None:
    """Convert between compressive strength and modulus of rupture."""
    if (compressive is None) == (rupture is None):
        raise click.UsageError("give exactly one of --compressive and --rupture")
    if compressive is not None:
        result = estimated_rupture(Quantity.parse(compressive), factor)
        click.echo(f"{compressive} gives a modulus of rupture of {result.format(0)}")
        return
    assert rupture is not None
    result = equivalent_compressive(Quantity.parse(rupture), factor)
    click.echo(f"{rupture} implies a compressive strength of {result.format(0)}")


@click.group("core")
def core_group() -> None:
    """Take cores and judge the structure on them."""


@core_group.command("take")
@click.argument("code")
@click.option("--location", required=True)
@click.option("--specified", required=True, help='For example "4000 psi".')
@click.option("--taken", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--diameter", default="4 in")
@click.option("--length", required=True, help="Measured length after trimming.")
@click.option("--load", "max_load", required=True)
@click.option("--condition", default="soaked", help="soaked, air dried or as received.")
@click.option("--reinforced", is_flag=True, help="The core contains steel.")
@click.pass_obj
@handle_errors
def take_command(
    context: CliContext,
    code: str,
    location: str,
    specified: str,
    taken: str,
    diameter: str,
    length: str,
    max_load: str,
    condition: str,
    reinforced: bool,
) -> None:
    """Record one core."""
    core = Core(
        code,
        Quantity.parse(diameter),
        Quantity.parse(length),
        Quantity.parse(max_load),
        CoreCondition.parse(condition),
        reinforced,
    )
    with context.register() as register:
        register.hardened.save_core(
            core, location, Quantity.parse(specified), parse_moment(taken)
        )
    click.echo(core.describe())


@core_group.command("judge")
@click.argument("location")
@click.pass_obj
@handle_errors
def judge_command(context: CliContext, location: str) -> None:
    """Judge one location on the cores taken from it."""
    with context.register() as register:
        found = register.hardened.investigation(location)
    click.echo(found.describe())
    if not found.is_adequate:
        raise click.ClickException("the structure is not shown to be adequate")


@core_group.command("locations")
@click.pass_obj
@handle_errors
def locations_command(context: CliContext) -> None:
    """Every location that has been cored."""
    with context.register() as register:
        rows: list[list[object]] = []
        for location in register.hardened.locations():
            found = register.hardened.investigation(location)
            rows.append(
                [
                    location,
                    len(found.cores),
                    found.average.format(0) if found.testable else "-",
                    "yes" if found.is_adequate else "no",
                ]
            )
    columns = (
        Column("location"),
        Column("cores", Align.RIGHT),
        Column("average", Align.RIGHT),
        Column("adequate"),
    )
    click.echo(heading("Cored locations"))
    click.echo(render_table(columns, rows))
