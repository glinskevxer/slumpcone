"""One command to run when something is wrong and nobody knows what.

A plant that has a problem does not know which subsystem has it. The batch
computer will not write a ticket, or the strength numbers stopped making sense,
or a report is empty and nobody can say whether that is because nothing happened
or because something broke. What they need is not eight commands, it is one, and
a list of what it found.

So this runs every check the package already has and gathers the answers. It
adds no new rules of its own, on purpose: a doctor that has its own opinion
about what is wrong drifts from the rules that actually refuse work, and then
there are two answers to the same question.

Three levels, and the difference between them is what somebody should do next.

A **failure** stops work. The register is corrupt, the schema is wrong, a scale
is out of calibration. Nobody batches until it is fixed.

A **warning** does not stop work today and will. A card runs out in three weeks,
a probe is due, a silo needs reordering.

A **note** is neither, and is here because the absence of it would be confusing:
"no technicians on file" is not a problem if the plant does not keep that record
here, and it is very much one if it does.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.people.certification import TestKind
from slumpcone.register import Register
from slumpcone.report.compliance import (
    blocking,
    calendar,
    from_catalog,
    from_plant,
    from_submittals,
    from_technicians,
    from_trucks,
)
from slumpcone.store.maintenance import integrity, space
from slumpcone.store.timing import run_all, unclean

# How far ahead the doctor looks for things about to run out.
HORIZON_DAYS = 30


class Level(Enum):
    """How much of a hurry to be in."""

    FAILURE = "failure"
    WARNING = "warning"
    NOTE = "note"

    def __str__(self) -> str:
        return self.value

    @property
    def stops_work(self) -> bool:
        """Whether a plant should not be batching until this is dealt with."""
        return self is Level.FAILURE


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the doctor found."""

    level: Level
    check: str
    detail: str

    def describe(self) -> str:
        """One line."""
        return f"[{self.level}] {self.check}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Report:
    """Everything the doctor found, and whether the plant can work."""

    on: date
    findings: tuple[Finding, ...]
    checks_run: int

    def of_level(self, level: Level) -> tuple[Finding, ...]:
        """Every finding at one level."""
        return tuple(one for one in self.findings if one.level is level)

    @property
    def failures(self) -> tuple[Finding, ...]:
        """What stops work."""
        return self.of_level(Level.FAILURE)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        """What will stop work soon."""
        return self.of_level(Level.WARNING)

    @property
    def is_well(self) -> bool:
        """Whether nothing stops the plant working today."""
        return not self.failures

    def describe(self) -> str:
        """One line."""
        if not self.findings:
            return f"{self.checks_run} check(s) run, nothing found"
        return (
            f"{self.checks_run} check(s) run, {len(self.failures)} failure(s), "
            f"{len(self.warnings)} warning(s), "
            f"{len(self.of_level(Level.NOTE))} note(s)"
        )


def _register_checks(register: Register) -> list[Finding]:
    """The file itself: pages, references, schema, size and query plans."""
    found: list[Finding] = []
    health = register.health()
    if not health.is_current:
        found.append(
            Finding(
                Level.FAILURE,
                "schema",
                f"register is at {health.schema_version}, this build ships "
                f"{health.expected_version}",
            )
        )
    sound = integrity(register.database)
    for line in sound.page_problems:
        found.append(Finding(Level.FAILURE, "pages", line))
    for line in sound.orphan_rows:
        found.append(Finding(Level.FAILURE, "references", line))
    room = space(register.database)
    if room.is_worth_vacuuming:
        found.append(Finding(Level.WARNING, "size", f"{room.describe()}, worth a vacuum"))
    for reading in unclean(run_all(register.database)):
        found.append(
            Finding(
                Level.WARNING,
                "query plans",
                f"{reading.name} reads {', '.join(reading.unexpected_scans)} whole",
            )
        )
    broken = register.audit.verify()
    if broken:
        found.append(
            Finding(
                Level.FAILURE,
                "audit log",
                f"the chain breaks at entr{'y' if len(broken) == 1 else 'ies'} "
                + ", ".join(str(one) for one in broken),
            )
        )
    return found


def _compliance_checks(register: Register, on: date) -> list[Finding]:
    """Everything with a date on it, across the whole plant."""
    found: list[Finding] = []
    items = list(from_catalog(register.materials.load_catalog(), on))
    for plant in register.plants.all():
        items.extend(from_plant(plant))
    items.extend(from_trucks(register.deliveries.trucks()))
    items.extend(from_technicians(register.people.all(), on))
    for project in register.projects.all():
        items.extend(from_submittals(register.projects.submittals_for(project.code)))
    for item in blocking(items, on):
        found.append(
            Finding(Level.FAILURE, str(item.kind), f"{item.subject} ran out {item.due_on}")
        )
    for item in calendar(items, on, horizon_days=HORIZON_DAYS):
        found.append(
            Finding(Level.WARNING, str(item.kind), f"{item.subject} runs out {item.due_on}")
        )
    return found


def _plant_checks(register: Register, on: date) -> list[Finding]:
    """The probes, the crew and the yard."""
    found: list[Finding] = []
    people = register.people.all()
    if not people:
        found.append(
            Finding(Level.NOTE, "crew", "no technicians on file, so no card is checked")
        )
    else:
        gaps = register.people.gaps(on, list(TestKind))
        if gaps:
            found.append(
                Finding(
                    Level.FAILURE,
                    "crew",
                    f"nobody may run: {', '.join(str(one) for one in gaps)}",
                )
            )
    for plant in register.plants.all():
        for history in register.probes.needing_attention(plant.code, on):
            level = Level.FAILURE if not history.standing(on).may_batch else Level.WARNING
            found.append(
                Finding(
                    level,
                    "moisture probe",
                    f"{plant.code} {history.probe_code} is {history.standing(on)}",
                )
            )
        stranded = [
            one for one in register.reclaim.still_on_the_yard(on) if not one.is_usable()
        ]
        if stranded:
            found.append(
                Finding(
                    Level.WARNING,
                    "returned concrete",
                    f"{len(stranded)} load(s) on the yard are too old to reuse",
                )
            )
    return found


def examine(register: Register, on: date) -> Report:
    """Run everything and gather what it says."""
    groups: list[Sequence[Finding]] = [
        _register_checks(register),
        _compliance_checks(register, on),
        _plant_checks(register, on),
    ]
    findings = [one for group in groups for one in group]
    order = {Level.FAILURE: 0, Level.WARNING: 1, Level.NOTE: 2}
    findings.sort(key=lambda one: (order[one.level], one.check, one.detail))
    return Report(on, tuple(findings), len(groups))
