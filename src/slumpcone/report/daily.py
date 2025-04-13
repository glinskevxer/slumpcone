"""The one page a plant manager reads before anything else.

Everything else in this package answers a question somebody went looking for.
This answers the question nobody asks out loud: what happened yesterday and is
anything on fire. It is deliberately one page, and the ordering is the order a
manager triages in -- what stopped, what failed, what is about to run out, then
how much went out of the gate.

Nothing here computes anything new. It calls the same functions the individual
reports call, so a figure on this page and the same figure on its own report
cannot disagree.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from slumpcone.fresh.acceptance import LoadOutcome, judge_load
from slumpcone.percent import Percent
from slumpcone.register import Register
from slumpcone.report.compliance import (
    blocking,
    calendar,
    from_catalog,
    from_plant,
    from_trucks,
)
from slumpcone.report.inventory_report import reorder_list, silo_status
from slumpcone.report.nonconformance import (
    NonConformance,
    Severity,
    counts_by_severity,
    from_haul,
    from_load,
    from_ticket,
    register_from,
)
from slumpcone.report.production import totals
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class DaySummary:
    """One day, as the morning meeting sees it."""

    on: date
    loads: int
    volume: Quantity
    returned: Quantity
    tested_loads: int
    rejected_loads: int
    retests_outstanding: int
    findings: tuple[NonConformance, ...]
    blocked_now: int
    expiring_soon: int
    reorders: int

    @property
    def tested_share(self) -> Percent:
        """How much of the day's work carried a fresh test."""
        if not self.loads:
            return Percent(0.0)
        return Percent.from_fraction(self.tested_loads / self.loads)

    @property
    def major_findings(self) -> int:
        """How many findings need a written response today."""
        return counts_by_severity(self.findings)[Severity.MAJOR]

    @property
    def needs_attention(self) -> bool:
        """True when something on the page has to be acted on."""
        return bool(
            self.major_findings or self.blocked_now or self.rejected_loads or self.reorders
        )

    def describe(self) -> str:
        """One line, for a message rather than a page."""
        verdict = "attention" if self.needs_attention else "clear"
        return (
            f"{self.on.isoformat()}: {self.loads} loads, {self.volume.format(1)}, "
            f"{self.major_findings} major finding(s), {verdict}"
        )


def summarise_day(register: Register, on: date, *, plant_code: str | None = None) -> DaySummary:
    """Gather one day out of the register."""
    tickets = [
        ticket
        for ticket in register.batches.between(on, on)
        if plant_code is None or ticket.plant_code == plant_code.strip().upper()
    ]
    deliveries = list(register.deliveries.between(on, on))
    by_ticket = {delivery.ticket_number: delivery for delivery in deliveries}
    groups: list[tuple[NonConformance, ...]] = []
    tested = rejected = outstanding = 0
    for ticket in tickets:
        groups.append(from_ticket(ticket))
        tests = register.fresh.for_ticket(ticket.number)
        if tests:
            tested += 1
            design = register.mixes.get(ticket.mix_code, ticket.mix_revision)
            verdict = judge_load(ticket.number, tests, design)
            if verdict.outcome is LoadOutcome.REJECTED:
                rejected += 1
            if verdict.outcome is LoadOutcome.RETEST_DUE:
                outstanding += 1
            groups.append(from_load(verdict, on))
        delivery = by_ticket.get(ticket.number)
        if delivery is not None:
            haul = delivery.haul_verdict()
            if haul is not None:
                groups.append(from_haul(haul, ticket.number, on))
    figures = totals(tickets, deliveries, start=on, end=on)
    items = list(from_catalog(register.materials.load_catalog(), on))
    plants = register.plants.all()
    for plant in plants:
        if plant_code is None or plant.code == plant_code.strip().upper():
            items.extend(from_plant(plant))
    items.extend(from_trucks(register.deliveries.trucks()))
    reorders = 0
    for plant in plants:
        if plant_code is not None and plant.code != plant_code.strip().upper():
            continue
        silos = register.plants.silos(plant.code)
        ledger = register.inventory.ledger(plant.code)
        reorders += len(reorder_list(silo_status(silos, ledger, on, on)))
    return DaySummary(
        on,
        figures.loads,
        figures.volume,
        figures.returned,
        tested,
        rejected,
        outstanding,
        register_from(groups),
        len(blocking(items, on)),
        len(calendar(items, on, horizon_days=14)),
        reorders,
    )


def render_day(summary: DaySummary, *, findings_shown: int = 10) -> str:
    """The whole page."""
    parts = [
        heading(f"Plant day, {summary.on.isoformat()}"),
        render_pairs(
            [
                ("loads", summary.loads),
                ("volume", summary.volume.format(1)),
                ("returned", summary.returned.format(2)),
                ("loads tested", f"{summary.tested_loads} ({summary.tested_share.format(0)})"),
                ("loads rejected", summary.rejected_loads),
                ("retests outstanding", summary.retests_outstanding),
                ("major findings", summary.major_findings),
                ("blocked now", summary.blocked_now),
                ("expiring in 14 days", summary.expiring_soon),
                ("silos to reorder", summary.reorders),
                ("verdict", "attention" if summary.needs_attention else "clear"),
            ]
        ),
    ]
    if summary.findings:
        shown = summary.findings[:findings_shown]
        parts.extend(
            [
                "",
                heading("Findings", underline="-"),
                render_table(
                    (
                        Column("severity"),
                        Column("code"),
                        Column("subject"),
                        Column("detail"),
                    ),
                    [
                        [
                            str(finding.severity),
                            finding.code,
                            finding.subject,
                            finding.detail,
                        ]
                        for finding in shown
                    ],
                ),
            ]
        )
        if len(summary.findings) > findings_shown:
            parts.append(f"and {len(summary.findings) - findings_shown} more")
    return "\n".join(parts)


def render_week(summaries: Sequence[DaySummary]) -> str:
    """A week of days, one line each."""
    columns = (
        Column("day"),
        Column("loads", Align.RIGHT),
        Column("volume", Align.RIGHT),
        Column("tested", Align.RIGHT),
        Column("rejected", Align.RIGHT),
        Column("major", Align.RIGHT),
        Column("verdict"),
    )
    rows = [
        [
            summary.on.isoformat(),
            summary.loads,
            summary.volume.format(1),
            summary.tested_loads,
            summary.rejected_loads,
            summary.major_findings,
            "attention" if summary.needs_attention else "clear",
        ]
        for summary in summaries
    ]
    return render_table(columns, rows)
