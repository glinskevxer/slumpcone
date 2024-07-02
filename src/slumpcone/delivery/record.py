"""The delivery record: what happened to one load after it left the plant.

Five timestamps and two counters, and the order they have to be in is itself a
check. A load cannot arrive before it leaves, or finish discharging before it
starts. Plants collect these off a truck tracking system and the systems get
them wrong, usually by dropping one and back-filling it from the next.

The haul verdict is computed from the record rather than stored on it. The
limits that apply depend on the mixture and the weather, and those are known
where the judging happens, not where the timestamps are collected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from slumpcone.delivery.haul import HaulLimits, HaulVerdict, judge_haul
from slumpcone.delivery.water import WaterAddition
from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_ticket_number
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class Delivery:
    """One load's trip, from the batch panel to the last of the chute."""

    ticket_number: str
    truck_code: str
    batched_at: datetime
    left_plant_at: datetime | None = None
    arrived_at: datetime | None = None
    discharge_started_at: datetime | None = None
    discharge_finished_at: datetime | None = None
    revolutions_on_arrival: int | None = None
    revolutions_at_discharge: int | None = None
    water_additions: tuple[WaterAddition, ...] = ()
    returned_volume: Quantity | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticket_number", normalize_ticket_number(self.ticket_number))
        object.__setattr__(
            self, "truck_code", normalize_code(self.truck_code, field="truck_code")
        )
        self._check_order()
        for name in ("revolutions_on_arrival", "revolutions_at_discharge"):
            count = getattr(self, name)
            if count is not None and count < 0:
                raise ValidationError("a revolution count cannot be negative", field=name)
        if self.returned_volume is not None:
            if self.returned_volume.dimension.value != "volume":
                raise ValidationError("returned concrete is a volume", field="returned_volume")
            if self.returned_volume.value < 0.0:
                raise ValidationError(
                    "returned concrete cannot be negative", field="returned_volume"
                )
        for addition in self.water_additions:
            if addition.ticket_number != self.ticket_number:
                raise ValidationError(
                    f"water addition for ticket {addition.ticket_number} on "
                    f"{self.ticket_number}",
                    field="water_additions",
                )

    def _check_order(self) -> None:
        stages = (
            ("batched_at", self.batched_at),
            ("left_plant_at", self.left_plant_at),
            ("arrived_at", self.arrived_at),
            ("discharge_started_at", self.discharge_started_at),
            ("discharge_finished_at", self.discharge_finished_at),
        )
        seen: list[tuple[str, datetime]] = [
            (name, moment) for name, moment in stages if moment is not None
        ]
        for (earlier_name, earlier), (later_name, later) in zip(seen, seen[1:], strict=False):
            if later < earlier:
                raise ValidationError(
                    f"{later_name} is before {earlier_name}", field=later_name
                )

    @property
    def is_complete(self) -> bool:
        """True when the load has finished discharging."""
        return self.discharge_finished_at is not None

    @property
    def haul_time(self) -> timedelta | None:
        """Plant to site, when both ends are known."""
        if self.left_plant_at is None or self.arrived_at is None:
            return None
        return self.arrived_at - self.left_plant_at

    @property
    def wait_time(self) -> timedelta | None:
        """Arrival to the start of discharge, which is where loads die."""
        if self.arrived_at is None or self.discharge_started_at is None:
            return None
        return self.discharge_started_at - self.arrived_at

    @property
    def discharge_time(self) -> timedelta | None:
        """How long the load took to come out."""
        if self.discharge_started_at is None or self.discharge_finished_at is None:
            return None
        return self.discharge_finished_at - self.discharge_started_at

    @property
    def total_time(self) -> timedelta | None:
        """Batch to the last of the chute."""
        if self.discharge_finished_at is None:
            return None
        return self.discharge_finished_at - self.batched_at

    @property
    def water_added(self) -> Quantity:
        """Every jobsite addition, added up."""
        total = Quantity.zero("gal")
        for addition in self.water_additions:
            total = total + addition.amount.to("gal")
        return total

    @property
    def has_multiple_additions(self) -> bool:
        """True when water went in more than once, which is not allowed."""
        return len(self.water_additions) > 1

    def haul_verdict(self, limits: HaulLimits | None = None) -> HaulVerdict | None:
        """Judge the haul, or ``None`` when the load has not finished."""
        if self.discharge_finished_at is None or self.revolutions_at_discharge is None:
            return None
        return judge_haul(
            self.batched_at,
            self.discharge_finished_at,
            self.revolutions_at_discharge,
            limits,
        )

    def describe(self) -> str:
        """One line for a delivery log."""
        total = self.total_time
        span = "in progress" if total is None else f"{total.total_seconds() / 60:.0f} min"
        water = f", {self.water_added.format(1)} added" if self.water_additions else ""
        return f"{self.ticket_number}  {self.truck_code}  {span}{water}"
