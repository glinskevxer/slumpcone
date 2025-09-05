"""Printing a delivery ticket, and auditing a run of them.

Two different documents out of the same record. The ticket print is what goes
to the customer and what an inspector asks for: the header C94 makes mandatory,
then every material with what was called for and what the scale recorded.

The audit is what a quality manager reads at the end of a week: one line per
ticket, and the only thing on it worth looking at is whether anything on that
ticket missed. A hundred clean tickets should take ten seconds to scan, which
means the clean line has to be short.
"""

from __future__ import annotations

from collections.abc import Sequence

from slumpcone.batching.ticket import BatchTicket
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


def render_ticket(ticket: BatchTicket) -> str:
    """One ticket as it prints."""
    header = render_pairs(
        [
            ("ticket", ticket.number),
            ("plant", ticket.plant_code),
            ("batched", ticket.batched_at.isoformat(sep=" ", timespec="minutes")),
            ("truck", ticket.truck_code or "-"),
            ("purchaser", ticket.purchaser or "-"),
            ("job", ticket.project or "-"),
            ("mix", f"{ticket.mix_code} r{ticket.mix_revision}"),
            ("quantity", ticket.volume.format(2)),
            (
                "to date",
                "-" if ticket.cumulative_volume is None else ticket.cumulative_volume.format(2),
            ),
            (
                "water held",
                "-" if ticket.water_held_back is None else ticket.water_held_back.format(0),
            ),
        ]
    )
    columns = (
        Column("material"),
        Column("required", Align.RIGHT),
        Column("actual", Align.RIGHT),
        Column("error", Align.RIGHT),
        Column("allowed", Align.RIGHT),
        Column("verdict"),
    )
    rows = [
        [
            line.material_code,
            line.required.format(0),
            line.actual.format(0),
            line.result.error.format(0),
            line.allowance.format(1),
            "ok" if line.result.conforms else f"out {line.result.side}",
        ]
        for line in ticket.lines
    ]
    parts = [heading(f"Ticket {ticket.number}"), header, "", render_table(columns, rows)]
    if ticket.admixtures:
        dose_columns = (
            Column("admixture"),
            Column("called for", Align.RIGHT),
            Column("dispensed", Align.RIGHT),
            Column("verdict"),
        )
        dose_rows = [
            [
                dose.material_code,
                dose.called_for.format(1),
                dose.dispensed.format(1),
                "ok" if dose.conforms else "out",
            ]
            for dose in ticket.admixtures
        ]
        parts.extend(["", render_table(dose_columns, dose_rows)])
    if ticket.notes:
        parts.extend(["", f"note: {ticket.notes}"])
    return "\n".join(parts)


def ticket_findings(ticket: BatchTicket) -> tuple[str, ...]:
    """One short phrase per thing wrong with a ticket."""
    found: list[str] = []
    for result in ticket.out_of_tolerance:
        found.append(f"{result.material_code} {result.side}")
    for dose in ticket.admixtures_out_of_tolerance:
        found.append(f"{dose.material_code} dose")
    missing = ticket.missing_required_fields()
    if missing:
        found.append(f"no {', '.join(missing)}")
    return tuple(found)


def render_audit(tickets: Sequence[BatchTicket]) -> str:
    """A run of tickets, one line each."""
    columns = (
        Column("ticket"),
        Column("batched"),
        Column("mix"),
        Column("qty", Align.RIGHT),
        Column("findings"),
    )
    rows = [
        [
            ticket.number,
            ticket.batched_at.isoformat(sep=" ", timespec="minutes"),
            f"{ticket.mix_code} r{ticket.mix_revision}",
            ticket.volume.format(2),
            ", ".join(ticket_findings(ticket)) or "ok",
        ]
        for ticket in sorted(tickets, key=lambda entry: (entry.batched_at, entry.number))
    ]
    return render_table(columns, rows)


def audit_summary(tickets: Sequence[BatchTicket]) -> str:
    """The counts under an audit table."""
    total = len(tickets)
    with_findings = sum(1 for ticket in tickets if ticket_findings(ticket))
    # Annotated rather than inferred. Without it the initial None narrows the
    # name to None and the addition below is an error, which is what CI caught.
    volume: Quantity | None = None
    for ticket in tickets:
        volume = ticket.volume if volume is None else volume + ticket.volume
    share = Percent.from_fraction((total - with_findings) / total) if total else Percent(0.0)
    return render_pairs(
        [
            ("tickets", total),
            ("volume", "-" if volume is None else volume.format(1)),
            ("with findings", with_findings),
            ("clean", share.format(1)),
        ]
    )


def render_audit_report(tickets: Sequence[BatchTicket]) -> str:
    """The audit table with its summary under it."""
    return "\n".join(
        [
            heading("Ticket audit"),
            render_audit(tickets),
            "",
            audit_summary(tickets),
        ]
    )
