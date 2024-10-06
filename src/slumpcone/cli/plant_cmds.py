"""Commands for plants, their scales and their vessels."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.materials.kinds import MaterialClass, WaterSource
from slumpcone.plant.plant import MixingMethod, Plant
from slumpcone.plant.scale import Scale
from slumpcone.plant.silo import Silo
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


@click.group("plant")
def plant_group() -> None:
    """File plants, scales and vessels."""


@plant_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--system", default="customary", help="customary or metric.")
@click.option("--mixing", default="truck_mixed", help="How the plant mixes.")
@click.option("--water", "water_source", default="potable")
@click.option("--max-load", default=None, help='For example "11 yd3".')
@click.option("--certified-to", default=None, metavar="YYYY-MM-DD")
@click.option("--location", default=None)
@click.pass_obj
@handle_errors
def add_command(
    context: CliContext,
    code: str,
    name: str,
    system: str,
    mixing: str,
    water_source: str,
    max_load: str | None,
    certified_to: str | None,
    location: str | None,
) -> None:
    """File a plant. Its scales are added separately."""
    with context.register() as register:
        try:
            existing = register.plants.get(code)
            scales = existing.scales
            silos = register.plants.silos(existing.code)
        except Exception:
            scales = ()
            silos = ()
        plant = Plant(
            code=code,
            name=name,
            unit_system=UnitSystem.parse(system),
            mixing_method=MixingMethod.parse(mixing),
            water_source=WaterSource.parse(water_source),
            scales=scales,
            max_load=None if max_load is None else Quantity.parse(max_load),
            certification_expires=None if certified_to is None else parse_day(certified_to),
            location=location,
        )
        register.plants.save(plant, silos)
    click.echo(plant.describe())


@plant_group.command("list")
@day_option()
@click.pass_obj
@handle_errors
def list_command(context: CliContext, on: date) -> None:
    """List the plants and whether they can run."""
    with context.register() as register:
        plants = register.plants.all()
    columns = (
        Column("code"),
        Column("name"),
        Column("system"),
        Column("mixing"),
        Column("scales", Align.RIGHT),
        Column("operable"),
    )
    rows = [
        [
            plant.code,
            plant.name,
            str(plant.unit_system),
            str(plant.mixing_method),
            len(plant.scales),
            "yes" if plant.is_operable(on) else "no",
        ]
        for plant in plants
    ]
    click.echo(render_table(columns, rows))


@plant_group.command("show")
@click.argument("code")
@day_option()
@click.pass_obj
@handle_errors
def show_command(context: CliContext, code: str, on: date) -> None:
    """Show one plant, its scales and its vessels."""
    with context.register() as register:
        plant = register.plants.get(code)
        silos = register.plants.silos(plant.code)
    click.echo(heading(plant.describe()))
    click.echo(
        render_pairs(
            [
                ("unit system", str(plant.unit_system)),
                ("mixing", str(plant.mixing_method)),
                ("water", str(plant.water_source)),
                ("max load", "-" if plant.max_load is None else plant.max_load.format(2)),
                (
                    "certified to",
                    "-"
                    if plant.certification_expires is None
                    else plant.certification_expires.isoformat(),
                ),
                ("operable", "yes" if plant.is_operable(on) else "no"),
            ]
        )
    )
    for reason in plant.blocking_reasons(on):
        click.echo(f"  {reason}")
    if plant.scales:
        click.echo("")
        click.echo(heading("Scales", underline="-"))
        for scale in plant.scales:
            click.echo(scale.describe(on))
    if silos:
        click.echo("")
        click.echo(heading("Vessels", underline="-"))
        for silo in silos:
            click.echo(silo.describe())


@plant_group.command("scale")
@click.argument("plant_code")
@click.argument("code")
@click.argument("name")
@click.option("--capacity", required=True, help='For example "12000 lb".')
@click.option("--graduation", required=True, help='For example "2 lb".')
@click.option("--weighs", required=True, help="Comma separated material classes.")
@click.option("--calibrated", required=True, metavar="YYYY-MM-DD")
@click.option("--interval", type=int, default=182, help="Calibration interval in days.")
@click.pass_obj
@handle_errors
def scale_command(
    context: CliContext,
    plant_code: str,
    code: str,
    name: str,
    capacity: str,
    graduation: str,
    weighs: str,
    calibrated: str,
    interval: int,
) -> None:
    """Add or replace a scale on a plant."""
    classes = tuple(MaterialClass.parse(part) for part in weighs.split(",") if part.strip())
    scale = Scale(
        code,
        name,
        Quantity.parse(capacity),
        Quantity.parse(graduation),
        classes,
        parse_day(calibrated),
        interval,
    )
    with context.register() as register:
        plant = register.plants.get(plant_code)
        kept = tuple(entry for entry in plant.scales if entry.code != scale.code)
        silos = register.plants.silos(plant.code)
        from dataclasses import replace

        register.plants.save(replace(plant, scales=(*kept, scale)), silos)
    click.echo(scale.describe(date.today()))


@plant_group.command("silo")
@click.argument("plant_code")
@click.argument("code")
@click.argument("name")
@click.option("--material", required=True)
@click.option("--capacity", required=True, help='For example "200000 lb".')
@click.option("--level", default="0 lb")
@click.option("--low", default=None, help="Low level mark.")
@click.pass_obj
@handle_errors
def silo_command(
    context: CliContext,
    plant_code: str,
    code: str,
    name: str,
    material: str,
    capacity: str,
    level: str,
    low: str | None,
) -> None:
    """Add or replace a vessel on a plant."""
    silo = Silo(
        code,
        name,
        material,
        Quantity.parse(capacity),
        Quantity.parse(level),
        None if low is None else Quantity.parse(low),
    )
    with context.register() as register:
        register.plants.save_silo(plant_code, silo)
    click.echo(silo.describe())


@plant_group.command("silos")
@click.argument("plant_code")
@click.pass_obj
@handle_errors
def silos_command(context: CliContext, plant_code: str) -> None:
    """List the vessels on a plant."""
    with context.register() as register:
        silos = register.plants.silos(plant_code)
    columns = (
        Column("silo"),
        Column("material"),
        Column("level", Align.RIGHT),
        Column("capacity", Align.RIGHT),
        Column("fill", Align.RIGHT),
        Column("state"),
    )
    rows = [
        [
            silo.code,
            silo.material_code,
            silo.level.format(0),
            silo.capacity.format(0),
            silo.fill.format(0),
            str(silo.state),
        ]
        for silo in silos
    ]
    click.echo(render_table(columns, rows))
