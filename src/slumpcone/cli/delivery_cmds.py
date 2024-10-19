"""Commands for trucks, deliveries and jobsite water."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import click

from slumpcone.cli.common import (
    CliContext,
    handle_errors,
    parse_day,
    parse_moment,
    window_options,
)
from slumpcone.delivery.haul import haul_limits
from slumpcone.delivery.record import Delivery
from slumpcone.delivery.truck import Truck
from slumpcone.delivery.water import RequestedBy, WaterAddition, judge_addition
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature


@click.group("delivery")
def delivery_group() -> None:
    """File trucks, deliveries and the water added at the job."""


@delivery_group.command("truck")
@click.argument("code")
@click.option("--drum", required=True, help='Gross drum volume, "11 yd3".')
@click.option("--fleet", default=None)
@click.option("--uniformity", default=None, metavar="YYYY-MM-DD")
@click.option("--interval", type=int, default=365)
@click.pass_obj
@handle_errors
def truck_command(
    context: CliContext,
    code: str,
    drum: str,
    fleet: str | None,
    uniformity: str | None,
    interval: int,
) -> None:
    """File a truck mixer."""
    truck = Truck(
        code,
        Quantity.parse(drum),
        fleet=fleet,
        last_uniformity_test=None if uniformity is None else parse_day(uniformity),
        uniformity_test_days=interval,
    )
    with context.register() as register:
        register.deliveries.save_truck(truck)
    click.echo(truck.describe())


@delivery_group.command("trucks")
@click.pass_obj
@handle_errors
def trucks_command(context: CliContext) -> None:
    """List the fleet."""
    with context.register() as register:
        trucks = register.deliveries.trucks()
    columns = (
        Column("code"),
        Column("fleet"),
        Column("drum", Align.RIGHT),
        Column("mixing", Align.RIGHT),
        Column("agitating", Align.RIGHT),
        Column("uniformity due"),
    )
    rows = [
        [
            truck.code,
            truck.fleet or "-",
            truck.drum_volume.format(1),
            truck.mixing_capacity.format(2),
            truck.agitating_capacity.format(2),
            "-" if truck.uniformity_due is None else truck.uniformity_due.isoformat(),
        ]
        for truck in trucks
    ]
    click.echo(render_table(columns, rows))


@delivery_group.command("record")
@click.argument("ticket")
@click.option("--truck", "truck_code", required=True)
@click.option("--batched", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--left", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--arrived", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--start", "discharge_started", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--finish", "discharge_finished", default=None, metavar="YYYY-MM-DDTHH:MM")
@click.option("--rev-arrival", type=int, default=None)
@click.option("--rev-discharge", type=int, default=None)
@click.option("--returned", default=None, help='Concrete brought back, "0.5 yd3".')
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def record_command(
    context: CliContext,
    ticket: str,
    truck_code: str,
    batched: str,
    left: str | None,
    arrived: str | None,
    discharge_started: str | None,
    discharge_finished: str | None,
    rev_arrival: int | None,
    rev_discharge: int | None,
    returned: str | None,
    notes: str,
) -> None:
    """Record or update a delivery, keeping any water additions on it."""
    with context.register() as register:
        try:
            existing = register.deliveries.get(ticket)
            additions = existing.water_additions
        except Exception:
            additions = ()
        delivery = Delivery(
            ticket_number=ticket,
            truck_code=truck_code,
            batched_at=parse_moment(batched),
            left_plant_at=None if left is None else parse_moment(left),
            arrived_at=None if arrived is None else parse_moment(arrived),
            discharge_started_at=(
                None if discharge_started is None else parse_moment(discharge_started)
            ),
            discharge_finished_at=(
                None if discharge_finished is None else parse_moment(discharge_finished)
            ),
            revolutions_on_arrival=rev_arrival,
            revolutions_at_discharge=rev_discharge,
            water_additions=additions,
            returned_volume=None if returned is None else Quantity.parse(returned),
            notes=notes,
        )
        register.deliveries.save(delivery)
    click.echo(delivery.describe())


@delivery_group.command("water")
@click.argument("ticket")
@click.option("--amount", required=True, help='Water added, "5 gal".')
@click.option("--at", "added_at", required=True, metavar="YYYY-MM-DDTHH:MM")
@click.option("--by", "requested_by", default="purchaser")
@click.option("--revolutions", type=int, default=30)
@click.option("--discharged", default=None, help="Concrete already placed.")
@click.pass_obj
@handle_errors
def water_command(
    context: CliContext,
    ticket: str,
    amount: str,
    added_at: str,
    requested_by: str,
    revolutions: int,
    discharged: str | None,
) -> None:
    """Record water added at the job and judge it."""
    addition = WaterAddition(
        ticket,
        parse_moment(added_at),
        Quantity.parse(amount),
        RequestedBy.parse(requested_by),
        revolutions,
        None if discharged is None else Quantity.parse(discharged),
    )
    with context.register() as register:
        delivery = register.deliveries.get(ticket)
        register.deliveries.save(
            replace(delivery, water_additions=(*delivery.water_additions, addition))
        )
        stored = register.batches.get(ticket)
        design = register.mixes.get(stored.mix_code, stored.mix_revision)
        water_line = next(line for line in stored.lines if line.material_class.value == "water")
        cementitious = Quantity.zero("lb")
        for line in stored.lines:
            if line.material_class.is_cementitious:
                cementitious = cementitious + line.actual.to("lb")
    verdict = judge_addition(
        addition,
        water_line.actual,
        cementitious,
        design.water_cementitious_ratio,
        design.exposure.max_water_cementitious,
    )
    click.echo(verdict.describe())


@delivery_group.command("haul")
@click.argument("ticket")
@click.option("--retarder", is_flag=True, help="The mixture carries a retarder.")
@click.option("--temp", type=float, default=None, help="Concrete temperature, degF.")
@click.option("--waived", is_flag=True, help="The purchaser waived the time limit.")
@click.pass_obj
@handle_errors
def haul_command(
    context: CliContext, ticket: str, retarder: bool, temp: float | None, waived: bool
) -> None:
    """Judge one load's haul against the limits that apply to it."""
    with context.register() as register:
        delivery = register.deliveries.get(ticket)
    limits = haul_limits(
        has_retarder=retarder,
        concrete_temperature=None if temp is None else Temperature(temp, "F"),
        time_waived=waived,
    )
    verdict = delivery.haul_verdict(limits)
    if verdict is None:
        raise click.ClickException(
            f"delivery {ticket} has not finished discharging, or has no counter reading"
        )
    click.echo(render_pairs([("limits", limits.describe())]))
    click.echo(verdict.describe())


@delivery_group.command("list")
@window_options
@click.option("--unfinished", is_flag=True, help="Only loads that never finished.")
@click.option("--truck", "truck_code", default=None)
@click.pass_obj
@handle_errors
def list_command(
    context: CliContext, start: date, end: date, unfinished: bool, truck_code: str | None
) -> None:
    """List deliveries in a window."""
    with context.register() as register:
        if unfinished:
            deliveries = register.deliveries.unfinished(start, end)
        elif truck_code is not None:
            deliveries = register.deliveries.for_truck(truck_code, start, end)
        else:
            deliveries = register.deliveries.between(start, end)
    columns = (
        Column("ticket"),
        Column("truck"),
        Column("batched"),
        Column("total", Align.RIGHT),
        Column("water", Align.RIGHT),
        Column("returned", Align.RIGHT),
    )
    rows = []
    for delivery in deliveries:
        total = delivery.total_time
        rows.append(
            [
                delivery.ticket_number,
                delivery.truck_code,
                delivery.batched_at.isoformat(sep=" ", timespec="minutes"),
                "-" if total is None else f"{total.total_seconds() / 60:.0f} min",
                delivery.water_added.format(1),
                "-" if delivery.returned_volume is None else delivery.returned_volume.format(2),
            ]
        )
    click.echo(heading("Deliveries"))
    click.echo(render_table(columns, rows))
