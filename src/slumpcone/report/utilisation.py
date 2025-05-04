"""What the fleet actually did with its day.

A plant's yard cost is trucks and drivers, and the only figure that connects
them to revenue is yards per truck hour. Everything else on this page exists to
say where the hours that did not turn into yards went.

The split matters more than the total. An hour a truck spent driving is an hour
nobody could have saved without moving the plant. An hour it spent waiting at a
job with a full drum is an hour the contractor bought and mostly did not pay
for, and it is the one figure on this page a dispatcher can act on tomorrow.

Two rules keep the numbers honest.

A delivery that is missing its moments contributes nothing rather than a zero.
Averaging a missing haul time in as zero makes the fleet look faster than it is,
and the records that go unfilled are exactly the ones from the bad days.

Nothing here divides by a count without saying what the count was. Yards per
truck hour off two loads is not a rate, it is an anecdote, and the report says
how many loads are behind every figure it prints.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class TruckDay:
    """One truck's day."""

    truck_code: str
    loads: int
    volume: Quantity
    driving: timedelta
    waiting: timedelta
    discharging: timedelta
    complete_records: int

    @property
    def working(self) -> timedelta:
        """Every hour the truck was out, whatever it was doing."""
        return self.driving + self.waiting + self.discharging

    @property
    def yards_per_hour(self) -> float:
        """Volume over hours out. Zero hours reads zero rather than raising."""
        hours = self.working.total_seconds() / 3600
        if hours <= 0.0:
            return 0.0
        return self.volume.to("yd3").value / hours

    @property
    def waiting_share(self) -> Percent:
        """How much of the day went on waiting at jobs."""
        total = self.working.total_seconds()
        if total <= 0.0:
            return Percent(0.0)
        return Percent.from_fraction(self.waiting.total_seconds() / total)

    @property
    def average_load(self) -> Quantity:
        """Mean load size, which says whether the truck is being filled."""
        if not self.loads:
            return Quantity(0.0, "yd3")
        return Quantity(self.volume.to("yd3").value / self.loads, "yd3")

    @property
    def is_thin(self) -> bool:
        """Whether too few records back the figures to quote them."""
        return self.complete_records < 3

    def describe(self) -> str:
        """One line."""
        tail = " (thin)" if self.is_thin else ""
        return (
            f"{self.truck_code}: {self.loads} load(s), {self.volume.format(1)}, "
            f"{self.yards_per_hour:.1f} yd3/h{tail}"
        )


@dataclass(frozen=True, slots=True)
class FleetDay:
    """Every truck, added up."""

    trucks: tuple[TruckDay, ...]

    @property
    def loads(self) -> int:
        """Every load the fleet carried."""
        return sum(one.loads for one in self.trucks)

    @property
    def volume(self) -> Quantity:
        """Everything delivered."""
        total = 0.0
        for one in self.trucks:
            total += one.volume.to("yd3").value
        return Quantity(total, "yd3")

    @property
    def working(self) -> timedelta:
        """Every truck hour."""
        total = timedelta(0)
        for one in self.trucks:
            total = total + one.working
        return total

    @property
    def waiting(self) -> timedelta:
        """Every hour spent waiting at a job."""
        total = timedelta(0)
        for one in self.trucks:
            total = total + one.waiting
        return total

    @property
    def yards_per_hour(self) -> float:
        """The fleet rate, which is not the mean of the truck rates.

        A truck that did one load in ten minutes has a spectacular rate and
        contributed almost nothing. Averaging the rates lets it drown out a
        truck that ran all day, so the fleet figure divides the totals.
        """
        hours = self.working.total_seconds() / 3600
        if hours <= 0.0:
            return 0.0
        return self.volume.value / hours

    @property
    def waiting_share(self) -> Percent:
        """How much of the fleet's day went on waiting."""
        total = self.working.total_seconds()
        if total <= 0.0:
            return Percent(0.0)
        return Percent.from_fraction(self.waiting.total_seconds() / total)

    def busiest(self) -> TruckDay | None:
        """The truck that carried the most."""
        if not self.trucks:
            return None
        return max(self.trucks, key=lambda one: one.volume.to("yd3").value)

    def worst_waiter(self) -> TruckDay | None:
        """The truck that lost the most time standing at jobs."""
        if not self.trucks:
            return None
        return max(self.trucks, key=lambda one: one.waiting)

    def ranked(self) -> tuple[TruckDay, ...]:
        """Every truck, most delivered first."""
        return tuple(
            sorted(self.trucks, key=lambda one: one.volume.to("yd3").value, reverse=True)
        )

    def describe(self) -> str:
        """One line."""
        return (
            f"{len(self.trucks)} truck(s), {self.loads} load(s), "
            f"{self.volume.format(1)}, {self.yards_per_hour:.1f} yd3/h, "
            f"{self.waiting_share.format(0)} waiting"
        )


def utilisation(tickets: Sequence[BatchTicket], deliveries: Sequence[Delivery]) -> FleetDay:
    """Work the fleet's day out of the tickets and the delivery records.

    Volume comes off the ticket because that is what was sold. Time comes off
    the delivery record because that is what was spent. A delivery with no
    ticket carries time and no volume, which is right: the truck still went.
    """
    volumes = {ticket.number: ticket.volume for ticket in tickets}
    codes: list[str] = []
    loads: dict[str, int] = {}
    carried: dict[str, float] = {}
    driving: dict[str, timedelta] = {}
    waiting: dict[str, timedelta] = {}
    discharging: dict[str, timedelta] = {}
    complete: dict[str, int] = {}

    for delivery in deliveries:
        code = delivery.truck_code
        if code not in loads:
            codes.append(code)
            loads[code] = 0
            carried[code] = 0.0
            driving[code] = timedelta(0)
            waiting[code] = timedelta(0)
            discharging[code] = timedelta(0)
            complete[code] = 0
        loads[code] += 1
        volume = volumes.get(delivery.ticket_number)
        if volume is not None:
            carried[code] += volume.to("yd3").value
        haul = delivery.haul_time
        wait = delivery.wait_time
        discharge = delivery.discharge_time
        if haul is not None:
            # The run home is not recorded, so the loaded run stands for both.
            driving[code] = driving[code] + haul * 2
        if wait is not None:
            waiting[code] = waiting[code] + wait
        if discharge is not None:
            discharging[code] = discharging[code] + discharge
        if haul is not None and wait is not None and discharge is not None:
            complete[code] += 1

    return FleetDay(
        tuple(
            TruckDay(
                code,
                loads[code],
                Quantity(carried[code], "yd3"),
                driving[code],
                waiting[code],
                discharging[code],
                complete[code],
            )
            for code in codes
        )
    )
