"""Who is allowed to run which test, and until when.

Nearly every specification that matters says the field tests have to be run by
an ACI Concrete Field Testing Technician Grade I, and nearly every plant finds
out it has a lapsed card the week a job goes to arbitration. The certificate is
not paperwork: a slump test run by somebody whose card expired is not evidence
of anything, and the load it accepted is not accepted.

So this module answers two questions and keeps them apart.

*Is this person certified for this test today* is a question about one date and
one card. It has a yes or no answer and nothing about it is negotiable.

*Which tests can this person run at all* is a question about what their cards
cover, ignoring dates. It is what a lab manager uses to plan a roster, and it is
not the same question, because a roster built on the first question empties
itself every time somebody's renewal is in the post.

The grades here are the real ones and they nest the way the real ones do. A
Grade I field technician can do the field tests. A strength testing technician
can break cylinders and cannot run a slump cone. Laboratory Level 2 covers Level
1. Nothing here invents a grade or lets one imply another that ACI does not.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.errors import RuleViolationError
from slumpcone.identity import normalize_code, normalize_name


class CertificationError(RuleViolationError):
    """A certification claim that cannot stand."""


class TestKind(Enum):
    """The things somebody has to be certified to do."""

    SAMPLING = "sampling"
    SLUMP = "slump"
    AIR = "air"
    TEMPERATURE = "temperature"
    UNIT_WEIGHT = "unit_weight"
    MAKING_CYLINDERS = "making_cylinders"
    BREAKING_CYLINDERS = "breaking_cylinders"
    AGGREGATE_GRADING = "aggregate_grading"
    AGGREGATE_MOISTURE = "aggregate_moisture"

    def __str__(self) -> str:
        return self.value.replace("_", " ")

    @property
    def is_field_test(self) -> bool:
        """Whether this happens at the back of the truck rather than in a lab."""
        return self in FIELD_TESTS


FIELD_TESTS = frozenset(
    {
        TestKind.SAMPLING,
        TestKind.SLUMP,
        TestKind.AIR,
        TestKind.TEMPERATURE,
        TestKind.UNIT_WEIGHT,
        TestKind.MAKING_CYLINDERS,
    }
)


class Grade(Enum):
    """The certifications a plant actually holds."""

    FIELD_GRADE_I = "field grade I"
    STRENGTH_TESTING = "strength testing"
    LAB_LEVEL_1 = "laboratory level 1"
    LAB_LEVEL_2 = "laboratory level 2"
    AGGREGATE_TESTING = "aggregate testing"

    def __str__(self) -> str:
        return self.value

    @property
    def covers(self) -> frozenset[TestKind]:
        """What this grade allows, on its own."""
        return _COVERAGE[self]

    def allows(self, kind: TestKind) -> bool:
        """Whether this grade covers one test."""
        return kind in self.covers


_COVERAGE: dict[Grade, frozenset[TestKind]] = {
    Grade.FIELD_GRADE_I: frozenset(FIELD_TESTS),
    Grade.STRENGTH_TESTING: frozenset({TestKind.BREAKING_CYLINDERS}),
    Grade.LAB_LEVEL_1: frozenset({TestKind.BREAKING_CYLINDERS, TestKind.AGGREGATE_MOISTURE}),
    # Level 2 subsumes Level 1 and adds grading. This is the only nesting ACI
    # actually gives, so it is the only one written down here.
    Grade.LAB_LEVEL_2: frozenset(
        {
            TestKind.BREAKING_CYLINDERS,
            TestKind.AGGREGATE_MOISTURE,
            TestKind.AGGREGATE_GRADING,
        }
    ),
    Grade.AGGREGATE_TESTING: frozenset(
        {TestKind.AGGREGATE_GRADING, TestKind.AGGREGATE_MOISTURE}
    ),
}


@dataclass(frozen=True, slots=True)
class Certification:
    """One card: a grade, held by somebody, until a date."""

    grade: Grade
    number: str
    issued_on: date
    expires_on: date

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "number", normalize_code(self.number, field="certification_number")
        )
        if self.expires_on <= self.issued_on:
            raise CertificationError(
                "CERTIFICATION_EXPIRES_BEFORE_ISSUE",
                f"{self.number} expires on or before the day it was issued",
            )

    def is_current(self, on: date) -> bool:
        """Whether the card is good on a day. The expiry day itself still counts."""
        return self.issued_on <= on <= self.expires_on

    def days_left(self, on: date) -> int:
        """How many days of validity are left. Negative once it has lapsed."""
        return (self.expires_on - on).days

    def expires_within(self, on: date, days: int) -> bool:
        """Whether it is current now and runs out inside a window."""
        return self.is_current(on) and self.days_left(on) <= days

    def describe(self) -> str:
        """One line."""
        return f"{self.grade} {self.number}, expires {self.expires_on.isoformat()}"


@dataclass(frozen=True, slots=True)
class Technician:
    """Somebody who runs tests, and the cards they hold."""

    code: str
    name: str
    certifications: tuple[Certification, ...] = ()
    employer: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="technician_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="technician_name"))
        numbers = [one.number for one in self.certifications]
        if len(set(numbers)) != len(numbers):
            raise CertificationError(
                "CERTIFICATION_TWICE",
                f"{self.code} carries the same certification number twice",
            )

    def current(self, on: date) -> tuple[Certification, ...]:
        """The cards that are good today."""
        return tuple(one for one in self.certifications if one.is_current(on))

    def may_run(self, kind: TestKind, on: date) -> bool:
        """Whether this person may run one test today.

        This is the question that decides whether a test result is evidence.
        """
        return any(one.grade.allows(kind) for one in self.current(on))

    def qualified_for(self) -> frozenset[TestKind]:
        """Everything their cards cover, ignoring whether any of them is current.

        Useful for a roster, useless for accepting a load. The two questions are
        deliberately different methods so nobody reaches for the wrong one.
        """
        covered: set[TestKind] = set()
        for one in self.certifications:
            covered |= one.grade.covers
        return frozenset(covered)

    def lapsed(self, on: date) -> tuple[Certification, ...]:
        """Cards that have run out."""
        return tuple(one for one in self.certifications if one.days_left(on) < 0)

    def expiring(self, on: date, *, days: int = 60) -> tuple[Certification, ...]:
        """Cards that are still good and run out soon, soonest first."""
        return tuple(
            sorted(
                (one for one in self.certifications if one.expires_within(on, days)),
                key=lambda one: one.expires_on,
            )
        )

    def describe(self, on: date) -> str:
        """One line."""
        current = len(self.current(on))
        return (
            f"{self.code} {self.name}: {current} current card(s), {len(self.lapsed(on))} lapsed"
        )


def who_may_run(
    technicians: Iterable[Technician], kind: TestKind, on: date
) -> tuple[Technician, ...]:
    """Everyone certified for one test today, in code order."""
    return tuple(
        sorted(
            (one for one in technicians if one.may_run(kind, on)),
            key=lambda one: one.code,
        )
    )


def uncovered(
    technicians: Sequence[Technician], kinds: Iterable[TestKind], on: date
) -> tuple[TestKind, ...]:
    """The tests nobody on the roster may run today.

    This is the one figure a plant manager needs before a Monday: not who is
    certified, but what nobody is.
    """
    return tuple(
        kind for kind in kinds if not any(one.may_run(kind, on) for one in technicians)
    )
