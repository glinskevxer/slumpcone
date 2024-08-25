"""The non-conformance register.

Everything the register knows how to object to ends up here in one shape, so a
quality manager reads one list rather than six screens. The shape is
deliberately flat: a code, how bad it is, what it is about, when, and one line
of detail.

Severity is a property of the rule, not of the number. A load discharged two
minutes late and a load discharged forty minutes late are the same finding with
the same remedy; what differs is the detail line. Grading by magnitude would
mean the register's own thresholds, on top of the standards' thresholds, and
two sets of thresholds is one too many.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.haul import HaulVerdict
from slumpcone.fresh.acceptance import LoadOutcome, LoadVerdict
from slumpcone.strength.acceptance import AcceptanceReport, StrengthStatus
from slumpcone.textout import Align, Column, render_table


class Severity(Enum):
    """How much attention a finding needs."""

    OBSERVATION = "observation"
    MINOR = "minor"
    MAJOR = "major"

    def __str__(self) -> str:
        return self.value

    @property
    def rank(self) -> int:
        """Sort order, worst first."""
        return {"major": 0, "minor": 1, "observation": 2}[self.value]

    @property
    def needs_a_response(self) -> bool:
        """True when somebody has to write something down about it."""
        return self is not Severity.OBSERVATION


# Which severity each finding code carries. Keeping it in one table means the
# grading is visible and arguable rather than scattered through the code that
# raises each finding.
_SEVERITY: dict[str, Severity] = {
    "BATCH_WEIGHT_OUT_OF_TOLERANCE": Severity.MINOR,
    "ADMIXTURE_DOSE_OUT_OF_TOLERANCE": Severity.MINOR,
    "TICKET_INCOMPLETE": Severity.MINOR,
    "LOAD_REJECTED": Severity.MAJOR,
    "LOAD_RETEST_OUTSTANDING": Severity.OBSERVATION,
    "DISCHARGE_LATE": Severity.MAJOR,
    "REVOLUTIONS_EXCEEDED": Severity.MAJOR,
    "STRENGTH_INVESTIGATE": Severity.MAJOR,
    "WATER_ADDED_PAST_DESIGN": Severity.MAJOR,
    "SILO_SHORT": Severity.MINOR,
}


def severity_of(code: str) -> Severity:
    """How bad a finding code is. Unknown codes are minor, never ignored."""
    return _SEVERITY.get(code, Severity.MINOR)


@dataclass(frozen=True, slots=True)
class NonConformance:
    """One thing the register objects to."""

    code: str
    subject: str
    raised_on: date
    detail: str
    source: str = ""

    @property
    def severity(self) -> Severity:
        """How bad this finding is."""
        return severity_of(self.code)

    def describe(self) -> str:
        """One line for a register listing."""
        return (
            f"{self.raised_on.isoformat()}  {self.severity}  {self.code}  "
            f"{self.subject}  {self.detail}"
        )


def from_ticket(ticket: BatchTicket) -> tuple[NonConformance, ...]:
    """Findings a delivery ticket raises on its own."""
    raised_on = ticket.batched_at.date()
    found: list[NonConformance] = []
    for result in ticket.out_of_tolerance:
        found.append(
            NonConformance(
                "BATCH_WEIGHT_OUT_OF_TOLERANCE",
                f"ticket {ticket.number}",
                raised_on,
                result.describe(),
                "batch record",
            )
        )
    for dose in ticket.admixtures_out_of_tolerance:
        found.append(
            NonConformance(
                "ADMIXTURE_DOSE_OUT_OF_TOLERANCE",
                f"ticket {ticket.number}",
                raised_on,
                f"{dose.material_code} called for {dose.called_for.format(1)} and "
                f"dispensed {dose.dispensed.format(1)}",
                "batch record",
            )
        )
    missing = ticket.missing_required_fields()
    if missing:
        found.append(
            NonConformance(
                "TICKET_INCOMPLETE",
                f"ticket {ticket.number}",
                raised_on,
                f"no {', '.join(missing)} on the ticket",
                "batch record",
            )
        )
    return tuple(found)


def from_load(verdict: LoadVerdict, raised_on: date) -> tuple[NonConformance, ...]:
    """Findings the fresh tests on one load raise."""
    if verdict.outcome is LoadOutcome.REJECTED:
        detail = "; ".join(entry.describe() for entry in verdict.failures)
        return (
            NonConformance(
                "LOAD_REJECTED",
                f"ticket {verdict.ticket_number}",
                raised_on,
                detail,
                "field test",
            ),
        )
    if verdict.outcome is LoadOutcome.RETEST_DUE:
        return (
            NonConformance(
                "LOAD_RETEST_OUTSTANDING",
                f"ticket {verdict.ticket_number}",
                raised_on,
                "a property failed and no retest is on file",
                "field test",
            ),
        )
    return ()


def from_haul(
    verdict: HaulVerdict, ticket_number: str, raised_on: date
) -> tuple[NonConformance, ...]:
    """Findings the haul of one load raises."""
    found: list[NonConformance] = []
    if verdict.over_time:
        found.append(
            NonConformance(
                "DISCHARGE_LATE",
                f"ticket {ticket_number}",
                raised_on,
                verdict.reasons[0],
                "delivery record",
            )
        )
    if verdict.over_revolutions:
        found.append(
            NonConformance(
                "REVOLUTIONS_EXCEEDED",
                f"ticket {ticket_number}",
                raised_on,
                f"drum turned {verdict.revolutions} times",
                "delivery record",
            )
        )
    return tuple(found)


def from_strength(report: AcceptanceReport, raised_on: date) -> tuple[NonConformance, ...]:
    """Findings a mixture's strength record raises."""
    if report.status is not StrengthStatus.INVESTIGATE:
        return ()
    return tuple(
        NonConformance(
            "STRENGTH_INVESTIGATE",
            f"mix {report.mix_code}",
            raised_on,
            reason,
            "strength record",
        )
        for reason in report.reasons
    )


def register_from(
    findings: Iterable[Iterable[NonConformance]],
) -> tuple[NonConformance, ...]:
    """Flatten and sort findings, worst and oldest first."""
    collected = [entry for group in findings for entry in group]
    return tuple(
        sorted(
            collected,
            key=lambda entry: (entry.severity.rank, entry.raised_on, entry.code, entry.subject),
        )
    )


def render_register(entries: Sequence[NonConformance]) -> str:
    """The register as a plain text table."""
    columns = (
        Column("raised"),
        Column("severity"),
        Column("code"),
        Column("subject"),
        Column("detail"),
        Column("source", Align.LEFT),
    )
    rows = [
        [
            entry.raised_on.isoformat(),
            str(entry.severity),
            entry.code,
            entry.subject,
            entry.detail,
            entry.source,
        ]
        for entry in entries
    ]
    return render_table(columns, rows)


def counts_by_severity(entries: Sequence[NonConformance]) -> dict[Severity, int]:
    """How many findings of each severity, including the empty ones."""
    tally = dict.fromkeys(Severity, 0)
    for entry in entries:
        tally[entry.severity] += 1
    return tally
