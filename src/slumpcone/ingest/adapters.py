"""Turning accepted rows into the records the register holds.

The adapters are deliberately thin and deliberately strict. Everything they
build goes through the same constructors the rest of the package uses, so a row
that produces an impossible record raises there rather than getting a second,
looser validation path of its own. An import that can create records the
application cannot is worse than an import that refuses them.

One row does not always make one record. A field test sheet with a slump, an
air content and a temperature on the same line is three tests taken off one
sample, and they are three rows in the register because they are three
different methods with three different tolerances.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from slumpcone.delivery.record import Delivery
from slumpcone.errors import ValidationError
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.ingest.result import AcceptedRow
from slumpcone.percent import Percent
from slumpcone.plant.receipt import Receipt
from slumpcone.strength.breaks import BreakResult, FractureType
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from slumpcone.units.temperature import Temperature


def _need(row: AcceptedRow, name: str) -> Any:
    value = row.get(name)
    if value is None:
        raise ValidationError(f"{name} is missing on line {row.line_number}", field=name)
    return value


def to_delivery(row: AcceptedRow) -> Delivery:
    """A batch recorder row as the start of a delivery record."""
    truck = row.get("truck_code")
    if truck is None:
        raise ValidationError(
            f"no truck on line {row.line_number}, so there is no delivery to record",
            field="truck_code",
        )
    batched_at = _need(row, "batched_at")
    if not isinstance(batched_at, datetime):
        raise ValidationError("batched_at is not a timestamp", field="batched_at")
    return Delivery(
        ticket_number=str(_need(row, "ticket_number")),
        truck_code=str(truck),
        batched_at=batched_at,
        notes=f"imported from line {row.line_number}",
    )


def to_break_result(row: AcceptedRow) -> BreakResult:
    """A lab row as a break result.

    A cylinder with one diameter recorded is taken as round: the lab measured
    once because the two agreed. That is a real convention rather than a guess,
    and it is why the profile only requires one of the pair.
    """
    diameter_one = row.get("diameter_one")
    diameter_two = row.get("diameter_two") or diameter_one
    if diameter_one is None:
        raise ValidationError(f"no diameter on line {row.line_number}", field="diameter_one")
    length = row.get("length")
    if length is None:
        length = diameter_one * 2.0
    fracture = row.get("fracture")
    tested_at = _need(row, "tested_at")
    return BreakResult(
        specimen_code=str(_need(row, "specimen_code")),
        tested_at=tested_at,
        age_days=float(_need(row, "age_days")),
        diameter_one=diameter_one,
        diameter_two=diameter_two,
        length=length,
        max_load=_need(row, "max_load"),
        fracture=(FractureType.CONE if fracture is None else FractureType.parse(str(fracture))),
        tested_by=None if row.get("tested_by") is None else str(row.get("tested_by")),
        notes=f"imported from line {row.line_number}",
    )


def to_fresh_tests(row: AcceptedRow) -> tuple[FreshTest, ...]:
    """A field sheet row as one test per reading on it."""
    ticket = str(_need(row, "ticket_number"))
    taken_at = _need(row, "taken_at")
    technician = None if row.get("technician") is None else str(row.get("technician"))
    is_retest = bool(row.get("is_retest") or False)
    built: list[FreshTest] = []
    slump = row.get("slump")
    if slump is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.SLUMP,
                taken_at,
                slump=slump,
                technician=technician,
                is_retest=is_retest,
            )
        )
    air = row.get("air")
    if air is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.AIR_PRESSURE,
                taken_at,
                air=air if isinstance(air, Percent) else Percent(float(air)),
                technician=technician,
                is_retest=is_retest,
            )
        )
    temperature = row.get("temperature")
    if temperature is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.TEMPERATURE,
                taken_at,
                temperature=Temperature(float(temperature), "F"),
                technician=technician,
                is_retest=is_retest,
            )
        )
    unit_weight = row.get("unit_weight")
    if unit_weight is not None:
        built.append(
            FreshTest(
                ticket,
                FreshTestKind.UNIT_WEIGHT,
                taken_at,
                unit_weight=MassPerVolume(float(unit_weight), "lb", "ft3"),
                technician=technician,
                is_retest=is_retest,
            )
        )
    if not built:
        raise ValidationError(f"no readings on line {row.line_number}", field="ticket_number")
    return tuple(built)


def to_receipt(row: AcceptedRow) -> Receipt:
    """A supplier delivery row as a receipt."""
    quantity = _need(row, "quantity")
    if not isinstance(quantity, Quantity):
        raise ValidationError("quantity is not a weight", field="quantity")
    return Receipt(
        reference=str(_need(row, "reference")),
        plant_code=str(_need(row, "plant_code")),
        silo_code=str(_need(row, "silo_code")),
        material_code=str(_need(row, "material_code")),
        received_at=_need(row, "received_at"),
        quantity=quantity,
        supplier=None if row.get("supplier") is None else str(row.get("supplier")),
        supplier_ticket=(
            None if row.get("supplier_ticket") is None else str(row.get("supplier_ticket"))
        ),
        certificate_reference=(
            None
            if row.get("certificate_reference") is None
            else str(row.get("certificate_reference"))
        ),
        notes=f"imported from line {row.line_number}",
    )
