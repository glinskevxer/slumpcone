"""Orders, and how much of one has actually turned up.

An order is for a volume of a class, to be placed on a day at a rate. Three of
those four matter to the plant and the fourth, the rate, is what decides whether
the job runs or the trucks queue.

The interesting number is not what was ordered but the running total against
it. A pour that is one load short at the end has a cold joint in it; a pour
that is two loads over has concrete going in a skip and somebody arguing about
who pays. Both are visible from the ticket stream well before the last truck
leaves the plant, and neither is visible from the order alone.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# How far over the ordered volume a pour may run before it is worth a note.
OVERRUN_TOLERANCE = Percent(5.0)


class OrderStatus(Enum):
    """Where an order stands."""

    BOOKED = "booked"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value

    @property
    def accepts_loads(self) -> bool:
        """True when a plant may still batch against this order."""
        return self in {OrderStatus.BOOKED, OrderStatus.IN_PROGRESS}


@dataclass(frozen=True, slots=True)
class Order:
    """One booking: a volume of a class, for a day, at a rate."""

    number: str
    project_code: str
    class_code: str
    volume: Quantity
    placement_date: date
    mix_code: str | None = None
    start_time: time | None = None
    rate: Quantity | None = None
    placement: str | None = None
    status: OrderStatus = OrderStatus.BOOKED
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalize_code(self.number, field="order_number"))
        object.__setattr__(
            self, "project_code", normalize_code(self.project_code, field="project_code")
        )
        object.__setattr__(
            self, "class_code", normalize_code(self.class_code, field="class_code")
        )
        if self.mix_code is not None:
            object.__setattr__(
                self, "mix_code", normalize_code(self.mix_code, field="mix_code")
            )
        if self.placement is not None:
            object.__setattr__(
                self, "placement", normalize_name(self.placement, field="placement")
            )
        if self.volume.dimension.value != "volume":
            raise ValidationError("an ordered quantity is a volume", field="volume")
        if self.volume.value <= 0.0:
            raise ValidationError("an ordered quantity has to be positive", field="volume")
        if self.rate is not None:
            if self.rate.dimension.value != "volume":
                raise ValidationError("a delivery rate is a volume per hour", field="rate")
            if self.rate.value <= 0.0:
                raise ValidationError("a delivery rate has to be positive", field="rate")

    @property
    def loads_at(self) -> str:
        """The order as a dispatcher reads it out."""
        rate = f" at {self.rate.format(1)}/h" if self.rate is not None else ""
        return f"{self.volume.format(1)}{rate}"

    def expected_loads(self, load_size: Quantity) -> int:
        """How many trucks the order takes at a given load size."""
        if load_size.dimension.value != "volume":
            raise ValidationError("a load size is a volume", field="load_size")
        if load_size.value <= 0.0:
            raise ValidationError("a load size has to be positive", field="load_size")
        whole = self.volume.base_value / load_size.base_value
        return int(whole) + (0 if abs(whole - round(whole)) < 1e-9 else 1)

    def describe(self) -> str:
        """One line for a dispatch board."""
        where = f"  {self.placement}" if self.placement else ""
        mix = f"  {self.mix_code}" if self.mix_code else ""
        return (
            f"{self.number}  {self.project_code}/{self.class_code}{mix}  "
            f"{self.placement_date.isoformat()}  {self.loads_at}{where}  {self.status}"
        )


@dataclass(frozen=True, slots=True)
class OrderProgress:
    """An order against what has actually been delivered on it."""

    order: Order
    delivered: Quantity
    load_count: int
    returned: Quantity

    @property
    def placed(self) -> Quantity:
        """What went in the forms, which is delivered less what came back."""
        return self.delivered - self.returned.to(self.delivered.unit)

    @property
    def remaining(self) -> Quantity:
        """What is still to come, floored at nothing."""
        left = self.order.volume - self.delivered.to(self.order.volume.unit)
        if left.value < 0.0:
            return Quantity.zero(self.order.volume.unit)
        return left

    @property
    def completion(self) -> Percent:
        """How far through the order the deliveries are."""
        return Percent.from_fraction(self.delivered.base_value / self.order.volume.base_value)

    @property
    def overrun(self) -> Quantity:
        """How much was delivered past the order, floored at nothing."""
        over = self.delivered.to(self.order.volume.unit) - self.order.volume
        if over.value < 0.0:
            return Quantity.zero(self.order.volume.unit)
        return over

    @property
    def is_over(self) -> bool:
        """True when the pour ran past what was ordered by more than the tolerance."""
        return self.completion.value > 100.0 + OVERRUN_TOLERANCE.value

    @property
    def is_short(self) -> bool:
        """True when the deliveries stopped before the order was filled."""
        return not self.remaining.is_zero()

    def describe(self) -> str:
        """One line for a pour log."""
        return (
            f"{self.order.number}  {self.delivered.format(1)} of "
            f"{self.order.volume.format(1)} in {self.load_count} loads  "
            f"{self.completion.format(0)}"
        )


def progress_of(
    order: Order,
    delivered_volumes: Iterable[Quantity],
    returned_volumes: Iterable[Quantity] = (),
) -> OrderProgress:
    """Add up what has been delivered against an order."""
    unit = order.volume.unit
    delivered = Quantity.zero(unit)
    count = 0
    for volume in delivered_volumes:
        if volume.dimension.value != "volume":
            raise ValidationError("a delivered quantity is a volume", field="delivered_volumes")
        delivered = delivered + volume.to(unit)
        count += 1
    returned = Quantity.zero(unit)
    for volume in returned_volumes:
        returned = returned + volume.to(unit)
    return OrderProgress(order, delivered, count, returned)
