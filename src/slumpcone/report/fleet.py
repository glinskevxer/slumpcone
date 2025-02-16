"""Where the trucks go, and where the time goes.

A plant's capacity is not how fast it can batch. It is how fast the trucks come
back, and the difference between those two is the reason a plant with four
mixers can be short of trucks on a Tuesday and idle on a Wednesday.

Turn time is measured between one load and the next off the same truck, because
that is a figure the register already knows: the batch times are on the
tickets. A returned-to-plant timestamp would be better and no plant records it
reliably, so the number here is the one that can actually be computed.

Waiting time is the one worth watching. Haul time is the distance and nobody
can change it, discharge time is the crew, and waiting is the pour running
behind, which is the only one a dispatcher can do anything about on the day.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


def _minutes(span: timedelta | None) -> float | None:
    return None if span is None else span.total_seconds() / 60.0


@dataclass(frozen=True, slots=True)
class CycleParts:
    """One load broken into where its time went."""

    ticket_number: str
    truck_code: str
    loading: float | None
    haul_out: float | None
    waiting: float | None
    discharging: float | None

    @property
    def total(self) -> float | None:
        """Everything that is known, added up."""
        parts = [self.loading, self.haul_out, self.waiting, self.discharging]
        known = [part for part in parts if part is not None]
        return sum(known) if known else None

    @property
    def is_complete(self) -> bool:
        """True when every stage was recorded."""
        return all(
            part is not None
            for part in (self.loading, self.haul_out, self.waiting, self.discharging)
        )

    def describe(self) -> str:
        """One line for a fleet log."""

        def show(value: float | None) -> str:
            return "-" if value is None else f"{value:.0f}"

        return (
            f"{self.ticket_number}  {self.truck_code}  load {show(self.loading)}  "
            f"out {show(self.haul_out)}  wait {show(self.waiting)}  "
            f"discharge {show(self.discharging)}"
        )


def cycle_parts(delivery: Delivery) -> CycleParts:
    """Split one delivery into its stages, in minutes."""
    loading = (
        None
        if delivery.left_plant_at is None
        else _minutes(delivery.left_plant_at - delivery.batched_at)
    )
    return CycleParts(
        delivery.ticket_number,
        delivery.truck_code,
        loading,
        _minutes(delivery.haul_time),
        _minutes(delivery.wait_time),
        _minutes(delivery.discharge_time),
    )


def turn_times(deliveries: Sequence[Delivery]) -> dict[str, tuple[float, ...]]:
    """Minutes between consecutive loads, per truck.

    A truck's first load of the day has no turn time, so a truck that made one
    load contributes nothing and does not drag the average down.
    """
    by_truck: dict[str, list[Delivery]] = {}
    for delivery in deliveries:
        by_truck.setdefault(delivery.truck_code, []).append(delivery)
    turns: dict[str, tuple[float, ...]] = {}
    for code, loads in sorted(by_truck.items()):
        ordered = sorted(loads, key=lambda entry: entry.batched_at)
        gaps = [
            (later.batched_at - earlier.batched_at).total_seconds() / 60.0
            for earlier, later in zip(ordered, ordered[1:], strict=False)
        ]
        turns[code] = tuple(gaps)
    return turns


@dataclass(frozen=True, slots=True)
class TruckSummary:
    """One truck's day."""

    truck_code: str
    loads: int
    volume: Quantity
    turns: tuple[float, ...]

    @property
    def average_turn(self) -> float | None:
        """Average minutes between loads, when there were two or more."""
        if not self.turns:
            return None
        return sum(self.turns) / len(self.turns)

    @property
    def volume_per_load(self) -> Quantity:
        """How full the truck went out on average."""
        if not self.loads:
            return Quantity.zero(self.volume.unit)
        return self.volume * (1.0 / self.loads)

    def utilisation(self, shift_minutes: float, cycle_minutes: float) -> Percent:
        """How much of a shift this truck spent on a load.

        ``cycle_minutes`` is what one load ought to take. Multiplying it by the
        loads made and dividing by the shift gives a figure that is honest
        about what the plant expected, rather than one computed from the
        turns themselves, which would make a truck that sat all morning look
        fully used the moment it moved.
        """
        if shift_minutes <= 0.0:
            raise ValidationError("a shift has to have a length", field="shift_minutes")
        if cycle_minutes <= 0.0:
            raise ValidationError("a cycle has to have a length", field="cycle_minutes")
        return Percent.from_fraction(self.loads * cycle_minutes / shift_minutes)


def summarise_fleet(
    deliveries: Sequence[Delivery], tickets: Sequence[BatchTicket]
) -> tuple[TruckSummary, ...]:
    """One summary per truck, in code order."""
    volumes = {ticket.number: ticket.volume for ticket in tickets}
    turns = turn_times(deliveries)
    by_truck: dict[str, list[Delivery]] = {}
    for delivery in deliveries:
        by_truck.setdefault(delivery.truck_code, []).append(delivery)
    summaries: list[TruckSummary] = []
    for code, loads in sorted(by_truck.items()):
        carried = Quantity.zero("yd3")
        for delivery in loads:
            volume = volumes.get(delivery.ticket_number)
            if volume is not None:
                carried = carried + volume.to("yd3")
        summaries.append(TruckSummary(code, len(loads), carried, turns.get(code, ())))
    return tuple(summaries)


def render_fleet(
    summaries: Sequence[TruckSummary],
    *,
    shift_minutes: float = 600.0,
    cycle_minutes: float = 90.0,
) -> str:
    """The fleet table."""
    columns = (
        Column("truck"),
        Column("loads", Align.RIGHT),
        Column("volume", Align.RIGHT),
        Column("per load", Align.RIGHT),
        Column("avg turn", Align.RIGHT),
        Column("used", Align.RIGHT),
    )
    rows = [
        [
            summary.truck_code,
            summary.loads,
            summary.volume.format(1),
            summary.volume_per_load.format(2),
            "-" if summary.average_turn is None else f"{summary.average_turn:.0f}",
            summary.utilisation(shift_minutes, cycle_minutes).format(0),
        ]
        for summary in summaries
    ]
    return render_table(columns, rows)


def render_stages(deliveries: Sequence[Delivery]) -> str:
    """Where the time went on each load."""
    columns = (
        Column("ticket"),
        Column("truck"),
        Column("load", Align.RIGHT),
        Column("out", Align.RIGHT),
        Column("wait", Align.RIGHT),
        Column("discharge", Align.RIGHT),
        Column("total", Align.RIGHT),
    )
    rows: list[list[object]] = []
    for delivery in sorted(deliveries, key=lambda entry: entry.batched_at):
        parts = cycle_parts(delivery)

        def show(value: float | None) -> str:
            return "-" if value is None else f"{value:.0f}"

        rows.append(
            [
                parts.ticket_number,
                parts.truck_code,
                show(parts.loading),
                show(parts.haul_out),
                show(parts.waiting),
                show(parts.discharging),
                show(parts.total),
            ]
        )
    return render_table(columns, rows)


def render_fleet_report(
    deliveries: Sequence[Delivery],
    tickets: Sequence[BatchTicket],
    *,
    shift_minutes: float = 600.0,
    cycle_minutes: float = 90.0,
) -> str:
    """The whole fleet report."""
    summaries = summarise_fleet(deliveries, tickets)
    waits = [
        parts.waiting for parts in map(cycle_parts, deliveries) if parts.waiting is not None
    ]
    return "\n".join(
        [
            heading("Fleet"),
            render_pairs(
                [
                    ("trucks", len(summaries)),
                    ("loads", sum(summary.loads for summary in summaries)),
                    (
                        "average wait",
                        "-" if not waits else f"{sum(waits) / len(waits):.0f} min",
                    ),
                ]
            ),
            "",
            render_fleet(summaries, shift_minutes=shift_minutes, cycle_minutes=cycle_minutes),
            "",
            heading("Where the time went", underline="-"),
            render_stages(deliveries),
        ]
    )
