"""Whether the tests on file were run by somebody who was allowed to run them.

A slump reading is not a measurement, it is evidence, and evidence has a
provenance. A specification that calls for ACI Grade I field testing is saying
that a number taken by anybody else does not count, whatever the number is. So
the useful audit is not "did the load pass" but "would this result stand up if
somebody asked who took it".

One rule here is worth stating loudly because it is the one people get backwards
in both directions.

**A card is judged on the day of the test, not today.** A technician whose card
lapsed last month was perfectly entitled to run a test in March, and every March
result stands. Judging historical tests against today's roster condemns work
that was fine. The mirror mistake is worse: a card that has since been renewed
does not retroactively cover a test taken while it was lapsed, and a system that
looks up "is this person certified" without a date will quietly say it does.

The other rule is that a test with no technician written on it is a finding, not
a blank. It is the most common one, it is the cheapest to fix, and reporting it
as "unknown" rather than as a problem is how it stays at the top of the list for
years.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.people.certification import Technician, TestKind

# Which certification each fresh test falls under. Both air methods sit under
# the same one: C231 and C173 measure the same property by different means and
# the certification does not distinguish them.
CERTIFIED_AS: Mapping[FreshTestKind, TestKind] = {
    FreshTestKind.SLUMP: TestKind.SLUMP,
    FreshTestKind.AIR_PRESSURE: TestKind.AIR,
    FreshTestKind.AIR_VOLUMETRIC: TestKind.AIR,
    FreshTestKind.TEMPERATURE: TestKind.TEMPERATURE,
    FreshTestKind.UNIT_WEIGHT: TestKind.UNIT_WEIGHT,
}


class WitnessProblem(Enum):
    """Why a result would not stand."""

    NOBODY_NAMED = "no technician written on the test"
    NOT_ON_FILE = "the technician named is not on file"
    NOT_CERTIFIED = "the technician holds no card for this test"
    CARD_LAPSED = "the technician's card had lapsed on the day"

    def __str__(self) -> str:
        return self.value

    @property
    def is_a_records_problem(self) -> bool:
        """Whether the fix is paperwork rather than a retest.

        A missing name or a technician nobody filed can often be resolved by
        finding out who it was. A lapsed or absent card cannot: the test was run
        by somebody who was not entitled to, and no amount of filing changes it.
        """
        return self in {WitnessProblem.NOBODY_NAMED, WitnessProblem.NOT_ON_FILE}


@dataclass(frozen=True, slots=True)
class WitnessFinding:
    """One result that would not stand, and why."""

    ticket_number: str
    kind: FreshTestKind
    technician: str
    problem: WitnessProblem

    def describe(self) -> str:
        """One line."""
        who = self.technician or "nobody"
        return f"{self.ticket_number} {self.kind}: {who}, {self.problem}"


@dataclass(frozen=True, slots=True)
class WitnessAudit:
    """A run of tests, checked."""

    checked: int
    findings: tuple[WitnessFinding, ...]

    @property
    def sound(self) -> int:
        """How many results would stand."""
        return self.checked - len(self.findings)

    @property
    def is_clean(self) -> bool:
        """Whether every result checked out."""
        return not self.findings

    def of_problem(self, problem: WitnessProblem) -> tuple[WitnessFinding, ...]:
        """Every finding of one kind."""
        return tuple(one for one in self.findings if one.problem is problem)

    @property
    def needs_retest(self) -> tuple[WitnessFinding, ...]:
        """The findings that paperwork cannot fix."""
        return tuple(one for one in self.findings if not one.problem.is_a_records_problem)

    def counts(self) -> dict[WitnessProblem, int]:
        """How many of each problem, every problem present."""
        tally = dict.fromkeys(WitnessProblem, 0)
        for one in self.findings:
            tally[one.problem] += 1
        return tally

    def describe(self) -> str:
        """One line."""
        if self.is_clean:
            return f"{self.checked} result(s) checked, every one stands"
        return (
            f"{self.checked} result(s) checked, {len(self.findings)} would not stand, "
            f"{len(self.needs_retest)} of those need a retest"
        )


def audit_witnesses(
    tests: Sequence[FreshTest], technicians: Iterable[Technician]
) -> WitnessAudit:
    """Check every result against the roster, each on its own day."""
    roster = {person.code: person for person in technicians}
    findings: list[WitnessFinding] = []
    for test in tests:
        named = (test.technician or "").strip()
        if not named:
            findings.append(
                WitnessFinding(test.ticket_number, test.kind, "", WitnessProblem.NOBODY_NAMED)
            )
            continue
        person = roster.get(named.upper())
        if person is None:
            findings.append(
                WitnessFinding(test.ticket_number, test.kind, named, WitnessProblem.NOT_ON_FILE)
            )
            continue
        kind = CERTIFIED_AS[test.kind]
        on = test.taken_at.date()
        if person.may_run(kind, on):
            continue
        # The card exists but not on that day, against the card not existing at
        # all. Both stop the result standing and they are fixed differently.
        problem = (
            WitnessProblem.CARD_LAPSED
            if kind in person.qualified_for()
            else WitnessProblem.NOT_CERTIFIED
        )
        findings.append(WitnessFinding(test.ticket_number, test.kind, named, problem))
    return WitnessAudit(len(tests), tuple(findings))
