"""Commands for emission factors and the footprints computed off them."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.carbon.benchmark import assess
from slumpcone.carbon.factors import CarbonError, EmissionFactor, Provenance, Stage
from slumpcone.carbon.footprint import Footprint, footprint_of, reduction
from slumpcone.carbon.footprint import compare as order_by_weight
from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.cli.output import listing
from slumpcone.materials.kinds import MaterialClass
from slumpcone.register import Register
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

DEFAULT_TABLE = "national average"


def footprint_for(
    register: Register, mix_code: str, revision: int | None, volume: Quantity
) -> Footprint:
    """Look a mixture up and work out what it carries."""
    design = (
        register.mixes.latest(mix_code)
        if revision is None
        else register.mixes.get(mix_code, revision)
    )
    return footprint_of(
        design,
        register.carbon.book(),
        volume=volume,
        admixture_density=register.carbon.densities(),
    )


@click.group("carbon")
def carbon_group() -> None:
    """Emission factors, footprints and benchmark tables."""


@carbon_group.command("seed")
@click.option("--table", "table_name", default=DEFAULT_TABLE)
@click.pass_obj
@handle_errors
def seed_command(context: CliContext, table_name: str) -> None:
    """Load the shipped industry averages and benchmark shape."""
    with context.register() as register:
        added = register.carbon.load_defaults()
        if table_name in register.carbon.table_names():
            click.echo(f"{added} factor(s) added, {table_name} already on file")
            return
        register.carbon.load_default_table(table_name)
    click.echo(f"{added} factor(s) added, benchmark table {table_name} loaded")
    click.echo("these are industry averages and cannot back a declaration")


@carbon_group.command("factor")
@click.argument("material")
@click.option("--class", "material_class", required=True)
@click.option("--value", type=float, required=True, help="kg CO2e per kg of material.")
@click.option("--stage", default="A1-A3")
@click.option("--provenance", default="industry average")
@click.option("--source", default="", help="The document the figure came from.")
@click.option("--published", default=None, metavar="YYYY-MM-DD")
@click.pass_obj
@handle_errors
def factor_command(
    context: CliContext,
    material: str,
    material_class: str,
    value: float,
    stage: str,
    provenance: str,
    source: str,
    published: str | None,
) -> None:
    """File an emission factor for one material."""
    factor = EmissionFactor(
        material,
        MaterialClass(material_class.strip().lower()),
        value,
        Stage(stage.strip().upper().replace("_", "-")),
        Provenance(provenance.strip().lower()),
        source,
        None if published is None else parse_day(published),
    )
    with context.register() as register:
        register.carbon.save_factor(factor)
    click.echo(factor.describe())


@carbon_group.command("factors")
@day_option("--on")
@click.option("--stale", is_flag=True, help="Only the declarations that have aged out.")
@click.pass_obj
@handle_errors
def factors_command(context: CliContext, on: date, stale: bool) -> None:
    """Every emission factor on file."""
    with context.register() as register:
        book = register.carbon.book()
        factors = (
            book.stale(on)
            if stale
            else sorted(book.as_mapping().values(), key=lambda one: one.material_code)
        )
    listing(
        (
            Column("material"),
            Column("class"),
            Column("kg CO2e/kg", Align.RIGHT),
            Column("stage"),
            Column("provenance"),
            Column("published"),
        ),
        [
            [
                one.material_code,
                one.material_class.value,
                f"{one.kg_co2e_per_kg:.4f}",
                str(one.stage),
                str(one.provenance),
                "-" if one.published_on is None else one.published_on.isoformat(),
            ]
            for one in factors
        ],
        "factor",
    )


@carbon_group.command("drop")
@click.argument("material")
@click.pass_obj
@handle_errors
def drop_command(context: CliContext, material: str) -> None:
    """Forget an emission factor."""
    with context.register() as register:
        register.carbon.forget_factor(material)
    click.echo(f"{material.strip().upper()} dropped")


@carbon_group.command("density")
@click.argument("material")
@click.argument("density")
@click.pass_obj
@handle_errors
def density_command(context: CliContext, material: str, density: str) -> None:
    """File the density an admixture is counted through."""
    rate = MassPerVolume.parse(density)
    with context.register() as register:
        register.carbon.save_density(material, rate)
    click.echo(f"{material.strip().upper()} counted at {rate}")


@carbon_group.command("mix")
@click.argument("mix_code")
@click.option("--revision", type=int, default=None)
@click.option("--volume", default="1 yd3")
@click.option("--table", "table_name", default=DEFAULT_TABLE)
@day_option("--on")
@click.pass_obj
@handle_errors
def mix_command(
    context: CliContext,
    mix_code: str,
    revision: int | None,
    volume: str,
    table_name: str,
    on: date,
) -> None:
    """What one mixture carries, and how it reads against a benchmark."""
    with context.register() as register:
        found = footprint_for(register, mix_code, revision, Quantity.parse(volume))
        design = (
            register.mixes.latest(mix_code)
            if revision is None
            else register.mixes.get(mix_code, revision)
        )
        book = register.carbon.book()
        table = (
            register.carbon.table(table_name)
            if table_name in register.carbon.table_names()
            else None
        )
        verdict = (
            None if table is None else assess(found, design.specified_strength, table, book, on)
        )
    click.echo(heading(f"Carbon, {found.mix_code} r{found.revision}"))
    click.echo(
        render_pairs(
            [
                ("stage", f"{found.stage}, {found.stage.label}"),
                ("volume", found.volume.format(2)),
                ("total", f"{found.total_kg:.1f} kg CO2e"),
                ("per yd3", f"{found.per_cubic_yard:.1f} kg"),
                ("per m3", f"{found.per_cubic_metre:.1f} kg"),
                ("cement share", found.cement_share.format(1)),
                (
                    "intensity",
                    f"{found.intensity(design.specified_strength):.2f} kg/m3 per MPa",
                ),
                ("not counted", ", ".join(found.uncounted) or "nothing"),
            ]
        )
    )
    click.echo("")
    click.echo(
        render_table(
            (
                Column("material"),
                Column("mass", Align.RIGHT),
                Column("kg CO2e", Align.RIGHT),
                Column("share", Align.RIGHT),
            ),
            [
                [
                    line.material_code,
                    line.mass.format(1),
                    f"{line.kg_co2e:.2f}",
                    line.share_of(found.total_kg).format(1),
                ]
                for line in found.ranked()
            ],
        )
    )
    if verdict is None:
        click.echo("")
        click.echo(f"no benchmark table named {table_name} is on file")
        return
    click.echo("")
    click.echo(verdict.describe())
    for blocker in verdict.blockers:
        click.echo(f"  {blocker}")


@carbon_group.command("compare")
@click.argument("mix_codes", nargs=-1)
@click.option("--volume", default="1 yd3")
@click.pass_obj
@handle_errors
def compare_command(context: CliContext, mix_codes: tuple[str, ...], volume: str) -> None:
    """Order mixtures by what they carry, lightest first."""
    if len(mix_codes) < 2:
        raise CarbonError("CARBON_NOTHING_TO_COMPARE", "give two or more mixtures to compare")
    size = Quantity.parse(volume)
    with context.register() as register:
        found = [footprint_for(register, code, None, size) for code in mix_codes]
    ordered = order_by_weight(found)
    lightest = ordered[0]
    click.echo(
        render_table(
            (
                Column("mix"),
                Column("per m3", Align.RIGHT),
                Column("cement share", Align.RIGHT),
                Column("against lightest", Align.RIGHT),
            ),
            [
                [
                    f"{one.mix_code} r{one.revision}",
                    f"{one.per_cubic_metre:.1f}",
                    one.cement_share.format(1),
                    reduction(one, lightest).format(1),
                ]
                for one in ordered
            ],
        )
    )
    click.echo(f"lightest: {lightest.describe()}")


@carbon_group.command("tables")
@click.pass_obj
@handle_errors
def tables_command(context: CliContext) -> None:
    """Every benchmark table on file, with its rows."""
    with context.register() as register:
        names = register.carbon.table_names()
        tables = [register.carbon.table(name) for name in names]
    for table in tables:
        click.echo(heading(table.name))
        for row in table.classes:
            click.echo(f"  {row.describe()}")
    click.echo(f"{len(tables)} table(s)")
