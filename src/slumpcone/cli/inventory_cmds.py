"""Commands for receipts, the movement ledger and what is in the yard."""

from __future__ import annotations

from datetime import date, datetime

import click

from slumpcone.cli.common import (
    CliContext,
    handle_errors,
    parse_moment,
    window_options,
)
from slumpcone.plant.inventory import Movement, MovementKind
from slumpcone.plant.receipt import Receipt, apply_receipt, check_receipt
from slumpcone.report.inventory_report import render_inventory_report
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@click.group("inventory")
def inventory_group() -> None:
    """Receive material, draw on it and reconcile the ledger."""


@inventory_group.command("receive")
@click.argument("reference")
@click.option("--plant", "plant_code", required=True)
@click.option("--silo", "silo_code", required=True)
@click.option("--material", "material_code", required=True)
@click.option("--quantity", required=True, help='For example "48000 lb".')
@click.option("--at", "received_at", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--supplier", default=None)
@click.option("--bol", "supplier_ticket", default=None)
@click.option("--certificate", "certificate_reference", default=None)
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def receive_command(
    context: CliContext,
    reference: str,
    plant_code: str,
    silo_code: str,
    material_code: str,
    quantity: str,
    received_at: str,
    supplier: str | None,
    supplier_ticket: str | None,
    certificate_reference: str | None,
    notes: str,
) -> None:
    """Take a delivery into a vessel, raising its level and the ledger."""
    receipt = Receipt(
        reference=reference,
        plant_code=plant_code,
        silo_code=silo_code,
        material_code=material_code,
        received_at=parse_moment(received_at),
        quantity=Quantity.parse(quantity),
        supplier=supplier,
        supplier_ticket=supplier_ticket,
        certificate_reference=certificate_reference,
        notes=notes,
    )
    with context.register() as register:
        silo = register.plants.silo(plant_code, silo_code)
        for fault in check_receipt(receipt, silo):
            click.echo(f"  {fault}")
        filled = apply_receipt(receipt, silo)
        register.inventory.post_receipt(receipt)
        register.plants.save_silo(plant_code, filled)
    click.echo(receipt.describe())
    click.echo(filled.describe())


@inventory_group.command("draw")
@click.option("--plant", "plant_code", required=True)
@click.option("--silo", "silo_code", required=True)
@click.option("--quantity", required=True)
@click.option("--at", "drawn_at", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--reference", default=None, help="The ticket the draw was for.")
@click.pass_obj
@handle_errors
def draw_command(
    context: CliContext,
    plant_code: str,
    silo_code: str,
    quantity: str,
    drawn_at: str | None,
    reference: str | None,
) -> None:
    """Take material out of a vessel."""
    moment = datetime.now() if drawn_at is None else parse_moment(drawn_at)
    amount = Quantity.parse(quantity)
    with context.register() as register:
        silo = register.plants.silo(plant_code, silo_code)
        drawn = silo.draw(amount)
        register.inventory.record(
            Movement(
                plant_code,
                silo.code,
                silo.material_code,
                moment,
                MovementKind.DRAWDOWN,
                amount,
                reference=reference,
            )
        )
        register.plants.save_silo(plant_code, drawn)
    click.echo(drawn.describe())


@inventory_group.command("reconcile")
@click.option("--plant", "plant_code", required=True)
@click.option("--silo", "silo_code", required=True)
@click.option("--measured", required=True, help='The probed level, "115000 lb".')
@click.option("--at", "measured_at", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--reference", default=None)
@click.pass_obj
@handle_errors
def reconcile_command(
    context: CliContext,
    plant_code: str,
    silo_code: str,
    measured: str,
    measured_at: str | None,
    reference: str | None,
) -> None:
    """Set a vessel to a measured level and record the correction."""
    moment = datetime.now() if measured_at is None else parse_moment(measured_at)
    level = Quantity.parse(measured)
    with context.register() as register:
        silo = register.plants.silo(plant_code, silo_code)
        corrected, difference = silo.reconcile(level)
        ledger = register.inventory.ledger(plant_code)
        entry = ledger.reconcile(silo.code, level, moment, reference=reference)
        if entry is not None:
            register.inventory.record(entry)
        register.plants.save_silo(plant_code, corrected)
    click.echo(
        render_pairs(
            [
                ("silo", corrected.code),
                ("measured", level.format(0)),
                ("correction", difference.format(0)),
                ("ledger entry", "none" if entry is None else "recorded"),
            ]
        )
    )


@inventory_group.command("ledger")
@click.option("--plant", "plant_code", required=True)
@click.option("--silo", "silo_code", default=None)
@window_options
@click.pass_obj
@handle_errors
def ledger_command(
    context: CliContext, plant_code: str, silo_code: str | None, start: date, end: date
) -> None:
    """List the movements at a plant over a window."""
    with context.register() as register:
        movements = register.inventory.movements_between(plant_code, start, end)
    if silo_code is not None:
        wanted = silo_code.strip().upper().replace(" ", "-")
        movements = tuple(entry for entry in movements if entry.silo_code == wanted)
    columns = (
        Column("at"),
        Column("silo"),
        Column("material"),
        Column("kind"),
        Column("quantity", Align.RIGHT),
        Column("reference"),
    )
    rows = [
        [
            entry.at.isoformat(sep=" ", timespec="minutes"),
            entry.silo_code,
            entry.material_code,
            str(entry.kind),
            entry.signed.format(0),
            entry.reference or "-",
        ]
        for entry in movements
    ]
    click.echo(heading(f"Ledger at {plant_code.upper()}"))
    click.echo(render_table(columns, rows))


@inventory_group.command("report")
@click.option("--plant", "plant_code", required=True)
@window_options
@click.pass_obj
@handle_errors
def report_command(context: CliContext, plant_code: str, start: date, end: date) -> None:
    """The inventory report for one plant."""
    with context.register() as register:
        plant = register.plants.get(plant_code)
        silos = register.plants.silos(plant.code)
        ledger = register.inventory.ledger(plant.code)
    click.echo(render_inventory_report(plant.code, silos, ledger, start, end))


@inventory_group.command("receipts")
@click.option("--plant", "plant_code", required=True)
@window_options
@click.pass_obj
@handle_errors
def receipts_command(context: CliContext, plant_code: str, start: date, end: date) -> None:
    """List receipts at a plant over a window."""
    with context.register() as register:
        receipts = register.inventory.receipts_between(plant_code, start, end)
    columns = (
        Column("reference"),
        Column("received"),
        Column("material"),
        Column("silo"),
        Column("quantity", Align.RIGHT),
        Column("certificate"),
    )
    rows = [
        [
            receipt.reference,
            receipt.received_at.date().isoformat(),
            receipt.material_code,
            receipt.silo_code,
            receipt.quantity.format(0),
            receipt.certificate_reference or "-",
        ]
        for receipt in receipts
    ]
    click.echo(render_table(columns, rows))
