"""Commands for mix designs: filing them, checking them and proportioning one."""

from __future__ import annotations

import click

from slumpcone.cli.common import CliContext, handle_errors
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.limits import check_design
from slumpcone.mixdesign.proportioner import ProportioningRequest, proportion
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.mixdesign.tables import ExposureSeverity
from slumpcone.mixdesign.volumes import check_yield
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def _parse_charge(text: str) -> Charge:
    """Read ``CEM-I:cement:470 lb/yd3`` from the command line."""
    parts = text.split(":")
    if len(parts) != 3:
        raise click.BadParameter(
            f"{text!r} is not CODE:CLASS:CONTENT, for example CEM-I:cement:470"
        )
    code, klass, content = (part.strip() for part in parts)
    rate = content if "/" in content else f"{content} lb/yd3"
    return Charge(code, MaterialClass.parse(klass), MassPerVolume.parse(rate))


def _parse_dose(text: str) -> AdmixtureCharge:
    """Read ``AD-AE:1.2`` from the command line."""
    parts = text.split(":")
    if len(parts) != 2:
        raise click.BadParameter(f"{text!r} is not CODE:DOSE, for example AD-AE:1.2")
    code, dose = (part.strip() for part in parts)
    amount = dose if " " in dose else f"{dose} floz"
    return AdmixtureCharge(code, Quantity.parse(amount))


@click.group("mix")
def mix_group() -> None:
    """File and check mix designs."""


@mix_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--strength", required=True, help='For example "4000 psi".')
@click.option("--nms", required=True, help='Nominal maximum size, "1 in".')
@click.option("--slump", required=True, help='Target slump, "4 in".')
@click.option("--age", type=int, default=28, help="Test age in days.")
@click.option("--air", type=float, default=0.0, help="Design air content, percent.")
@click.option("--exposure", default="", help='For example "F2 S1".')
@click.option("--plant", "plant_code", default=None)
@click.option("--charge", "charges", multiple=True, help="CODE:CLASS:CONTENT, repeatable.")
@click.option("--admixture", "doses", multiple=True, help="CODE:DOSE, repeatable.")
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def add_command(
    context: CliContext,
    code: str,
    name: str,
    strength: str,
    nms: str,
    slump: str,
    age: int,
    air: float,
    exposure: str,
    plant_code: str | None,
    charges: tuple[str, ...],
    doses: tuple[str, ...],
    notes: str,
) -> None:
    """File the first revision of a mix design."""
    if not charges:
        raise click.UsageError("a mix design needs at least one --charge")
    proportions = Proportions(
        tuple(_parse_charge(entry) for entry in charges),
        tuple(_parse_dose(entry) for entry in doses),
        Percent(air),
    )
    design = MixDesign(
        code=code,
        name=name,
        proportions=proportions,
        specified_strength=Quantity.parse(strength),
        nominal_max_size=Quantity.parse(nms),
        slump_target=Quantity.parse(slump),
        test_age_days=age,
        exposure=ExposureSet.parse(exposure) if exposure else ExposureSet(),
        plant_code=plant_code,
        notes=notes,
    )
    with context.register() as register:
        register.mixes.save(design)
        context.note(register, "mix.save", design.code, f"revision {design.revision}")
    click.echo(design.describe())


@mix_group.command("list")
@click.option("--plant", "plant_code", default=None, help="Only mixes tied to this plant.")
@click.pass_obj
@handle_errors
def list_command(context: CliContext, plant_code: str | None) -> None:
    """List the newest revision of every mix design."""
    with context.register() as register:
        designs = (
            register.mixes.latest_all()
            if plant_code is None
            else register.mixes.for_plant(plant_code)
        )
    columns = (
        Column("code"),
        Column("rev", Align.RIGHT),
        Column("name"),
        Column("strength", Align.RIGHT),
        Column("w/cm", Align.RIGHT),
        Column("air", Align.RIGHT),
        Column("exposure"),
    )
    rows = [
        [
            design.code,
            design.revision,
            design.name,
            design.specified_strength.format(0),
            f"{design.water_cementitious_ratio:.3f}",
            design.design_air.format(1),
            str(design.exposure),
        ]
        for design in designs
    ]
    click.echo(render_table(columns, rows))


@mix_group.command("show")
@click.argument("code")
@click.option("--revision", type=int, default=None, help="A particular revision.")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, code: str, revision: int | None) -> None:
    """Show a mix design and its proportions."""
    with context.register() as register:
        design = (
            register.mixes.latest(code)
            if revision is None
            else register.mixes.get(code, revision)
        )
    click.echo(heading(design.describe()))
    click.echo(
        render_pairs(
            [
                ("cementitious", design.cementitious.format(0)),
                ("water/cementitious", f"{design.water_cementitious_ratio:.3f}"),
                ("replacement", design.proportions.supplementary_replacement.format(1)),
                ("sand fraction", design.proportions.fine_aggregate_fraction.format(1)),
                ("design air", design.design_air.format(1)),
                ("slump", design.slump_tolerance().format(1, "in")),
                ("aggregate", design.nominal_max_size.format(2)),
                ("plant", design.plant_code or "-"),
            ]
        )
    )
    click.echo("")
    columns = (Column("material"), Column("class"), Column("content", Align.RIGHT))
    rows = [
        [charge.material_code, str(charge.material_class), charge.content.format(1)]
        for charge in design.proportions.charges
    ]
    click.echo(render_table(columns, rows))
    if design.proportions.admixtures:
        click.echo("")
        dose_rows = [
            [dose.material_code, dose.dose_per_cwt.format(2)]
            for dose in design.proportions.admixtures
        ]
        click.echo(
            render_table((Column("admixture"), Column("per cwt", Align.RIGHT)), dose_rows)
        )


@mix_group.command("check")
@click.argument("code")
@click.option("--revision", type=int, default=None)
@click.pass_obj
@handle_errors
def check_command(context: CliContext, code: str, revision: int | None) -> None:
    """Check a design against its exposure classes and its own yield."""
    with context.register() as register:
        design = (
            register.mixes.latest(code)
            if revision is None
            else register.mixes.get(code, revision)
        )
        catalog = register.materials.load_catalog()
        gravities = {
            material.code: material.specific_gravity
            for material in catalog
            if material.specific_gravity is not None
        }
        findings = check_design(design, catalog)
    click.echo(heading(f"Check of {design.identity}"))
    click.echo(check_yield(design.proportions, gravities).describe())
    if not findings:
        click.echo("no findings")
        return
    for finding in findings:
        click.echo(f"  {finding.describe()}")
    raise click.ClickException(f"{len(findings)} finding(s)")


@mix_group.command("proportion")
@click.option("--strength", required=True, help='Required average strength, "4800 psi".')
@click.option("--slump", required=True, help='Target slump, "4 in".')
@click.option("--cement", required=True, help="Cement material code.")
@click.option("--coarse", required=True, help="Coarse aggregate code.")
@click.option("--fine", required=True, help="Fine aggregate code.")
@click.option("--water", "water_code", required=True, help="Water material code.")
@click.option("--scm", "scm_code", default=None)
@click.option("--replacement", type=float, default=0.0, help="SCM share of the binder.")
@click.option("--air/--no-air", "air_entrained", default=True)
@click.option("--severity", default="moderate", help="mild, moderate or severe.")
@click.option("--max-wcm", type=float, default=None)
@click.option("--min-cementitious", default=None, help='For example "564 lb".')
@click.pass_obj
@handle_errors
def proportion_command(
    context: CliContext,
    strength: str,
    slump: str,
    cement: str,
    coarse: str,
    fine: str,
    water_code: str,
    scm_code: str | None,
    replacement: float,
    air_entrained: bool,
    severity: str,
    max_wcm: float | None,
    min_cementitious: str | None,
) -> None:
    """Work a mixture up from the tables and print the working."""
    with context.register() as register:
        materials = register.materials
        request = ProportioningRequest(
            required_average_strength=Quantity.parse(strength),
            slump_target=Quantity.parse(slump),
            cement=materials.get(cement),
            coarse=materials.get(coarse),
            fine=materials.get(fine),
            water=materials.get(water_code),
            scm=None if scm_code is None else materials.get(scm_code),
            scm_replacement=Percent(replacement),
            air_entrained=air_entrained,
            severity=ExposureSeverity(severity.strip().lower()),
            max_water_cementitious=max_wcm,
            min_cementitious=(
                None if min_cementitious is None else Quantity.parse(min_cementitious)
            ),
        )
    result = proportion(request)
    click.echo(heading("Proportioning"))
    click.echo(result.describe())
    click.echo("")
    columns = (Column("material"), Column("content", Align.RIGHT))
    rows = [
        [charge.material_code, charge.content.format(1)]
        for charge in result.proportions.charges
    ]
    click.echo(render_table(columns, rows))
    click.echo("")
    click.echo(
        render_pairs(
            [
                ("water/cementitious", f"{result.water_cementitious:.3f}"),
                ("air", result.air.format(1)),
                ("cementitious", result.proportions.cementitious.format(0)),
            ]
        )
    )


@mix_group.command("revisions")
@click.argument("code")
@click.pass_obj
@handle_errors
def revisions_command(context: CliContext, code: str) -> None:
    """List every revision of one design."""
    with context.register() as register:
        designs = register.mixes.revisions(code)
    if not designs:
        raise click.ClickException(f"no mix design on file with identity {code!r}")
    columns = (
        Column("rev", Align.RIGHT),
        Column("w/cm", Align.RIGHT),
        Column("cementitious", Align.RIGHT),
        Column("air", Align.RIGHT),
        Column("notes"),
    )
    rows = [
        [
            design.revision,
            f"{design.water_cementitious_ratio:.3f}",
            design.cementitious.format(0),
            design.design_air.format(1),
            design.notes,
        ]
        for design in designs
    ]
    click.echo(render_table(columns, rows))
