"""Production over a window: how much went out and how much came back.

Volume delivered is the number everybody quotes and it is the least useful one
on its own. The two that tell you something are average load size, which says
whether the plant is filling trucks or running half loads, and returned
concrete, which is the cost of over-ordering and comes straight off the
producer's margin.

Returned concrete is deliberately reported as a share of what was delivered
rather than as a count of loads. One truck coming back full and twelve coming
back with half a yard each are very different problems, and a count of loads
that returned anything cannot tell them apart.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class ProductionTotals:
    """The headline figures for one window."""

    loads: int
    volume: Quantity
    returned: Quantity
    days: int

    @property
    def average_load(self) -> Quantity:
        """Volume divided by loads, which is what fills a truck."""
        if not self.loads:
            return Quantity.zero(self.volume.unit)
        return self.volume * (1.0 / self.loads)

    @property
    def per_day(self) -> Quantity:
        """Volume divided by the days in the window."""
        if self.days <= 0:
            return Quantity.zero(self.volume.unit)
        return self.volume * (1.0 / self.days)

    @property
    def returned_share(self) -> Percent:
        """Returned concrete as a share of what was delivered."""
        if self.volume.is_zero():
            return Percent(0.0)
        return Percent.from_fraction(self.returned.base_value / self.volume.base_value)

    @property
    def placed(self) -> Quantity:
        """What stayed in the forms."""
        return self.volume - self.returned.to(self.volume.unit)


def totals(
    tickets: Sequence[BatchTicket],
    deliveries: Sequence[Delivery] = (),
    *,
    start: date | None = None,
    end: date | None = None,
) -> ProductionTotals:
    """Add up a window's tickets, and the concrete that came back on them."""
    volume = Quantity.zero("yd3")
    for ticket in tickets:
        volume = volume + ticket.volume.to("yd3")
    returned = Quantity.zero("yd3")
    for delivery in deliveries:
        if delivery.returned_volume is not None:
            returned = returned + delivery.returned_volume.to("yd3")
    if start is not None and end is not None:
        days = max((end - start).days + 1, 1)
    elif tickets:
        span = {ticket.batched_at.date() for ticket in tickets}
        days = max((max(span) - min(span)).days + 1, 1)
    else:
        days = 0
    return ProductionTotals(len(tickets), volume, returned, days)


def _group(tickets: Sequence[BatchTicket], key: str) -> dict[str, tuple[int, Quantity]]:
    grouped: dict[str, tuple[int, Quantity]] = {}
    for ticket in tickets:
        name = str(getattr(ticket, key) or "-")
        count, volume = grouped.get(name, (0, Quantity.zero("yd3")))
        grouped[name] = (count + 1, volume + ticket.volume.to("yd3"))
    return dict(sorted(grouped.items()))


def by_mix(tickets: Sequence[BatchTicket]) -> dict[str, tuple[int, Quantity]]:
    """Loads and volume for each mixture."""
    return _group(tickets, "mix_code")


def by_plant(tickets: Sequence[BatchTicket]) -> dict[str, tuple[int, Quantity]]:
    """Loads and volume for each plant."""
    return _group(tickets, "plant_code")


def by_project(tickets: Sequence[BatchTicket]) -> dict[str, tuple[int, Quantity]]:
    """Loads and volume for each job."""
    return _group(tickets, "project")


def by_day(tickets: Sequence[BatchTicket]) -> dict[str, tuple[int, Quantity]]:
    """Loads and volume for each day in the window."""
    grouped: dict[str, tuple[int, Quantity]] = {}
    for ticket in tickets:
        name = ticket.batched_at.date().isoformat()
        count, volume = grouped.get(name, (0, Quantity.zero("yd3")))
        grouped[name] = (count + 1, volume + ticket.volume.to("yd3"))
    return dict(sorted(grouped.items()))


def render_group(grouped: dict[str, tuple[int, Quantity]], label: str) -> str:
    """One of the breakdown tables."""
    columns = (
        Column(label),
        Column("loads", Align.RIGHT),
        Column("volume", Align.RIGHT),
        Column("average", Align.RIGHT),
    )
    rows: list[list[object]] = []
    for name, (count, volume) in grouped.items():
        average = volume * (1.0 / count) if count else Quantity.zero("yd3")
        rows.append([name, count, volume.format(1), average.format(2)])
    return render_table(columns, rows)


def render_totals(figures: ProductionTotals) -> str:
    """The headline block."""
    return render_pairs(
        [
            ("loads", figures.loads),
            ("volume", figures.volume.format(1)),
            ("average load", figures.average_load.format(2)),
            ("per day", figures.per_day.format(1)),
            ("returned", figures.returned.format(1)),
            ("returned share", figures.returned_share.format(2)),
            ("placed", figures.placed.format(1)),
        ]
    )


def render_production_report(
    tickets: Sequence[BatchTicket],
    deliveries: Sequence[Delivery] = (),
    *,
    start: date | None = None,
    end: date | None = None,
) -> str:
    """The whole production report for a window."""
    figures = totals(tickets, deliveries, start=start, end=end)
    window = (
        f"{start.isoformat()} to {end.isoformat()}"
        if start is not None and end is not None
        else "all tickets on file"
    )
    return "\n".join(
        [
            heading(f"Production, {window}"),
            render_totals(figures),
            "",
            heading("By mix", underline="-"),
            render_group(by_mix(tickets), "mix"),
            "",
            heading("By job", underline="-"),
            render_group(by_project(tickets), "job"),
            "",
            heading("By day", underline="-"),
            render_group(by_day(tickets), "day"),
        ]
    )
