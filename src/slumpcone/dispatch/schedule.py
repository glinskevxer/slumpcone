"""Turning an order into a run of loads, and working out what it takes to feed it.

A pour is a rate, not a volume. The contractor tells you how many yards they
want and how fast they can place it, and everything else falls out of those two
numbers: how far apart the loads have to leave, how many trucks it takes to keep
that spacing, and when the first one has to be batched so it arrives when the
crew is ready rather than twenty minutes early.

The arithmetic is small and the mistakes are not.

Spacing is load size over pour rate, and it is what the whole schedule hangs on.
A crew placing thirty yards an hour with nine yard loads wants a truck every
eighteen minutes. Send them one every fifteen and you build a queue that ends in
standby charges; send one every twenty five and the pour cold joints.

Truck count is cycle time over spacing, rounded up, and the cycle is the round
trip: load, drive out, discharge, drive back, wash. Leaving the wash out is the
common error and it costs you a truck on any job with a short haul.

The last load is short unless the volume divides exactly, and a short load is
priced differently, so the schedule says which one it is rather than leaving the
dispatcher to notice.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from slumpcone.errors import RuleViolationError
from slumpcone.units.quantity import Quantity

# C94 gives ninety minutes from the water hitting the cement to the end of
# discharge, unless the job has agreed otherwise in writing.
DISCHARGE_LIMIT = timedelta(minutes=90)


class ScheduleError(RuleViolationError):
    """A pour that cannot be scheduled as asked."""


@dataclass(frozen=True, slots=True)
class CycleTime:
    """How long one truck takes to go round once."""

    loading: timedelta
    haul_out: timedelta
    on_site: timedelta
    haul_back: timedelta
    wash: timedelta = timedelta(minutes=5)

    def __post_init__(self) -> None:
        for name, leg in (
            ("loading", self.loading),
            ("haul out", self.haul_out),
            ("on site", self.on_site),
            ("haul back", self.haul_back),
            ("wash", self.wash),
        ):
            if leg < timedelta(0):
                raise ScheduleError("CYCLE_LEG_NEGATIVE", f"the {name} leg cannot be negative")
        if self.total <= timedelta(0):
            raise ScheduleError("CYCLE_EMPTY", "a cycle has to take some time")

    @property
    def total(self) -> timedelta:
        """The whole round trip."""
        return self.loading + self.haul_out + self.on_site + self.haul_back + self.wash

    @property
    def to_site(self) -> timedelta:
        """Batch to arrival, which is what the batch time is set back by."""
        return self.loading + self.haul_out

    @property
    def within_discharge_limit(self) -> bool:
        """Whether a load can reach the site and finish discharging inside the limit."""
        return self.to_site + self.on_site <= DISCHARGE_LIMIT

    def describe(self) -> str:
        """One line."""
        return (
            f"{self.total.total_seconds() / 60:.0f} min round trip, "
            f"{self.to_site.total_seconds() / 60:.0f} min to site"
        )


@dataclass(frozen=True, slots=True)
class ScheduledLoad:
    """One load, with the two times that matter."""

    sequence: int
    volume: Quantity
    batch_at: datetime
    arrive_at: datetime
    is_short: bool = False

    @property
    def discharge_deadline(self) -> datetime:
        """When C94 says this load has to be off the truck."""
        return self.batch_at + DISCHARGE_LIMIT

    def describe(self) -> str:
        """One line."""
        tail = " (short)" if self.is_short else ""
        return (
            f"load {self.sequence}: batch {self.batch_at:%H:%M}, "
            f"arrive {self.arrive_at:%H:%M}, {self.volume.format(1)}{tail}"
        )


@dataclass(frozen=True, slots=True)
class Schedule:
    """A whole pour, laid out."""

    order_number: str
    loads: tuple[ScheduledLoad, ...]
    spacing: timedelta
    cycle: CycleTime
    trucks_needed: int

    @property
    def total_volume(self) -> Quantity:
        """Everything the schedule delivers."""
        total = Quantity(0.0, self.loads[0].volume.unit) if self.loads else Quantity(0.0, "yd3")
        for load in self.loads:
            total = total + load.volume
        return total

    @property
    def first_batch(self) -> datetime | None:
        """When the plant starts."""
        return self.loads[0].batch_at if self.loads else None

    @property
    def last_arrival(self) -> datetime | None:
        """When the last load reaches the site."""
        return self.loads[-1].arrive_at if self.loads else None

    @property
    def duration(self) -> timedelta:
        """Site time from the first arrival to the last."""
        if len(self.loads) < 2:
            return timedelta(0)
        return self.loads[-1].arrive_at - self.loads[0].arrive_at

    @property
    def short_load(self) -> ScheduledLoad | None:
        """The one load that is not a full one, if there is one."""
        for load in self.loads:
            if load.is_short:
                return load
        return None

    def at_or_after(self, moment: datetime) -> tuple[ScheduledLoad, ...]:
        """The loads still to be batched at a moment."""
        return tuple(load for load in self.loads if load.batch_at >= moment)

    def describe(self) -> str:
        """One line."""
        return (
            f"{self.order_number}: {len(self.loads)} load(s), "
            f"{self.total_volume.format(1)}, one every "
            f"{self.spacing.total_seconds() / 60:.0f} min, {self.trucks_needed} truck(s)"
        )


def spacing_for(load_size: Quantity, pour_rate: Quantity, per: timedelta) -> timedelta:
    """How far apart loads have to leave to hold a placing rate."""
    if load_size.base_value <= 0.0:
        raise ScheduleError("SCHEDULE_NO_LOAD_SIZE", "a load size has to be positive")
    if pour_rate.base_value <= 0.0:
        raise ScheduleError("SCHEDULE_NO_POUR_RATE", "a pour rate has to be positive")
    loads_per_period = pour_rate.base_value / load_size.base_value
    return per / loads_per_period


def trucks_for(cycle: CycleTime, spacing: timedelta) -> int:
    """How many trucks it takes to hold a spacing, given a cycle time."""
    if spacing <= timedelta(0):
        raise ScheduleError("SCHEDULE_NO_SPACING", "a spacing has to be positive")
    return max(1, math.ceil(cycle.total / spacing))


def build_schedule(
    order_number: str,
    volume: Quantity,
    load_size: Quantity,
    pour_rate: Quantity,
    first_arrival: datetime,
    cycle: CycleTime,
    *,
    rate_period: timedelta = timedelta(hours=1),
) -> Schedule:
    """Lay a pour out into loads.

    ``first_arrival`` is when the crew wants concrete on site, not when the plant
    starts. The first batch time is set back by the time it takes to load and
    drive out, which is the whole point of asking for the cycle.
    """
    if volume.base_value <= 0.0:
        raise ScheduleError("SCHEDULE_NO_VOLUME", "a pour needs a positive volume")
    if load_size.base_value > volume.base_value:
        load_size = volume
    spacing = spacing_for(load_size, pour_rate, rate_period)
    count = math.ceil(volume.base_value / load_size.base_value - 1e-9)
    full = load_size.to(volume.unit)
    remainder = volume.value - full.value * (count - 1)
    loads = []
    for index in range(count):
        last = index == count - 1
        size = Quantity(remainder, volume.unit) if last else full
        arrive = first_arrival + spacing * index
        loads.append(
            ScheduledLoad(
                index + 1,
                size,
                arrive - cycle.to_site,
                arrive,
                is_short=last and remainder < full.value - 1e-9,
            )
        )
    return Schedule(order_number, tuple(loads), spacing, cycle, trucks_for(cycle, spacing))


def overlaps(schedules: Sequence[Schedule]) -> tuple[tuple[str, str], ...]:
    """Which pours want the plant at the same time.

    Two schedules overlap when either one's batching window contains a batch
    time from the other. This is deliberately crude: it says which pairs to look
    at, not which one to move.
    """
    pairs: list[tuple[str, str]] = []
    for first_index, first in enumerate(schedules):
        for second in schedules[first_index + 1 :]:
            if not first.loads or not second.loads:
                continue
            start = max(first.loads[0].batch_at, second.loads[0].batch_at)
            end = min(first.loads[-1].batch_at, second.loads[-1].batch_at)
            if start <= end:
                pairs.append((first.order_number, second.order_number))
    return tuple(pairs)
