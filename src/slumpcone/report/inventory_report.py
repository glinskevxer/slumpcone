"""What is in the yard, what went out of it, and when it runs out.

The level on its own is not useful. A silo holding forty thousand pounds is
comfortable on a quiet week and empty by Wednesday on a busy one, so the figure
a dispatcher actually needs is days of cover: the level divided by how fast the
plant has been drawing it.

Cover is computed from the ledger rather than from a planning figure, because
the plant's own recent usage is the only usage rate that has ever been right.
A silo with no drawdowns at all has no cover figure, and reporting one as
infinite would put an idle silo at the top of a list sorted by comfort.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time

from slumpcone.percent import Percent
from slumpcone.plant.inventory import InventoryLedger, MovementKind
from slumpcone.plant.silo import Silo, SiloState
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity

# Silos with less than this much cover go on the reorder list.
REORDER_DAYS = 3.0


@dataclass(frozen=True, slots=True)
class SiloStatus:
    """One vessel with its level, its recent usage and its cover."""

    silo: Silo
    daily_usage: Quantity | None
    days_of_cover: float | None

    @property
    def needs_reordering(self) -> bool:
        """True when the level or the cover says to order more."""
        if self.silo.state.needs_a_delivery:
            return True
        return self.days_of_cover is not None and self.days_of_cover < REORDER_DAYS

    @property
    def cover_text(self) -> str:
        """Days of cover, or a dash when there is no usage to divide by."""
        if self.days_of_cover is None:
            return "-"
        return f"{self.days_of_cover:.1f}"


def silo_status(
    silos: Sequence[Silo], ledger: InventoryLedger, start: date, end: date
) -> tuple[SiloStatus, ...]:
    """Level, usage and cover for every vessel, in code order."""
    days = max((end - start).days + 1, 1)
    window_start = datetime.combine(start, time.min)
    window_end = datetime.combine(end, time.max)
    built: list[SiloStatus] = []
    for silo in sorted(silos, key=lambda entry: entry.code):
        used = ledger.usage(silo.code, window_start, window_end)
        if used.is_zero():
            built.append(SiloStatus(silo, None, None))
            continue
        daily = used * (1.0 / days)
        cover = silo.level.base_value / daily.base_value
        built.append(SiloStatus(silo, daily, cover))
    return tuple(built)


def render_silos(statuses: Sequence[SiloStatus]) -> str:
    """The silo table."""
    columns = (
        Column("silo"),
        Column("material"),
        Column("level", Align.RIGHT),
        Column("capacity", Align.RIGHT),
        Column("fill", Align.RIGHT),
        Column("per day", Align.RIGHT),
        Column("cover", Align.RIGHT),
        Column("state"),
    )
    rows = [
        [
            status.silo.code,
            status.silo.material_code,
            status.silo.level.format(0),
            status.silo.capacity.format(0),
            status.silo.fill.format(0),
            "-" if status.daily_usage is None else status.daily_usage.format(0),
            status.cover_text,
            str(status.silo.state),
        ]
        for status in statuses
    ]
    return render_table(columns, rows)


def reorder_list(statuses: Sequence[SiloStatus]) -> tuple[SiloStatus, ...]:
    """The vessels worth ordering against, tightest cover first."""
    wanted = [status for status in statuses if status.needs_reordering]
    return tuple(
        sorted(
            wanted,
            key=lambda status: (
                status.days_of_cover if status.days_of_cover is not None else 0.0,
                status.silo.code,
            ),
        )
    )


def usage_by_material(ledger: InventoryLedger, start: date, end: date) -> dict[str, Quantity]:
    """How much of each material went out over a window."""
    window_start = datetime.combine(start, time.min)
    window_end = datetime.combine(end, time.max)
    totals: dict[str, Quantity] = {}
    for code in ledger.silo_codes():
        for movement in ledger.movements_for(code, until=window_end):
            if movement.at < window_start or not movement.kind.removes:
                continue
            running = totals.get(movement.material_code, Quantity.zero("lb"))
            totals[movement.material_code] = running + movement.quantity.to("lb")
    return dict(sorted(totals.items()))


def render_usage(totals: dict[str, Quantity]) -> str:
    """The usage table."""
    columns = (Column("material"), Column("used", Align.RIGHT))
    rows = [[code, amount.format(0)] for code, amount in totals.items()]
    return render_table(columns, rows)


def adjustment_summary(ledger: InventoryLedger) -> str:
    """How much the ledger has been corrected by, per vessel.

    A silo that needs correcting every week is either leaking, mis-weighing or
    being drawn on by something that is not writing a movement. All three are
    worth chasing and none of them shows up in the level.
    """
    rows: list[list[object]] = []
    for code in ledger.silo_codes():
        adjustments = ledger.adjustments(code)
        if not adjustments:
            continue
        total = Quantity.zero("lb")
        for entry in adjustments:
            total = total + entry.signed.to("lb")
        rows.append([code, len(adjustments), total.format(0)])
    columns = (Column("silo"), Column("corrections", Align.RIGHT), Column("net", Align.RIGHT))
    return render_table(columns, rows)


def render_inventory_report(
    plant_code: str,
    silos: Sequence[Silo],
    ledger: InventoryLedger,
    start: date,
    end: date,
) -> str:
    """The whole inventory report for one plant over one window."""
    statuses = silo_status(silos, ledger, start, end)
    reorder = reorder_list(statuses)
    parts = [
        heading(f"Inventory at {plant_code}"),
        render_pairs(
            [
                ("window", f"{start.isoformat()} to {end.isoformat()}"),
                ("vessels", len(silos)),
                ("to reorder", len(reorder)),
            ]
        ),
        "",
        render_silos(statuses),
        "",
        heading("Usage", underline="-"),
        render_usage(usage_by_material(ledger, start, end)),
    ]
    if reorder:
        parts.extend(
            [
                "",
                heading("Reorder", underline="-"),
                render_silos(reorder),
            ]
        )
    return "\n".join(parts)


def counts_by_state(statuses: Sequence[SiloStatus]) -> dict[SiloState, int]:
    """How many vessels are in each state, including the empty ones."""
    tally = dict.fromkeys(SiloState, 0)
    for status in statuses:
        tally[status.silo.state] += 1
    return tally


def total_held(silos: Sequence[Silo]) -> Quantity:
    """Everything in the yard, by weight."""
    total = Quantity.zero("lb")
    for silo in silos:
        total = total + silo.level.to("lb")
    return total


def fill_across(silos: Sequence[Silo]) -> Percent:
    """How full the yard is as a whole."""
    capacity = Quantity.zero("lb")
    for silo in silos:
        capacity = capacity + silo.capacity.to("lb")
    if capacity.is_zero():
        return Percent(0.0)
    return Percent.from_fraction(total_held(silos).base_value / capacity.base_value)


def drawdown_count(ledger: InventoryLedger, silo_code: str) -> int:
    """How many batches have drawn on one vessel."""
    return sum(
        1
        for movement in ledger.movements_for(silo_code)
        if movement.kind is MovementKind.DRAWDOWN
    )
