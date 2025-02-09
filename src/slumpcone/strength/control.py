"""Standards of control: how consistent the plant and the lab actually are.

Two different variations and they are the responsibility of two different
people. Overall variation is the spread between strength tests, and it belongs
to the plant: batching, materials, moisture. Within-test variation is the
spread between the cylinders of one test, and it belongs to the laboratory:
making them, curing them, capping them, breaking them.

Separating them is the whole point. A record with a wide overall spread and a
tight within-test spread is a batching problem. One with a tight overall spread
and a wide within-test spread is a testing problem, and no amount of extra
cement will fix it.

Within-test variation is estimated from the average range between companions
divided by a constant that depends on how many companions there are. Using the
two-cylinder constant on three-cylinder sets overstates the lab's consistency
by about a third, which is the mistake that makes a struggling lab look fine.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity

# The divisor that turns an average range into a standard deviation, by how
# many results the range was taken over.
_RANGE_CONSTANT: dict[int, float] = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326}

# The fewest tests a standard of control can be read off at all.
MIN_TESTS = 10


class ControlStandard(Enum):
    """How ACI grades a record's consistency."""

    EXCELLENT = "excellent"
    VERY_GOOD = "very good"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"

    def __str__(self) -> str:
        return self.value

    @property
    def needs_attention(self) -> bool:
        """True when the grade is one a quality manager acts on."""
        return self in {ControlStandard.FAIR, ControlStandard.POOR}


def range_constant(companions: int) -> float:
    """The divisor for an average range over that many results."""
    if companions not in _RANGE_CONSTANT:
        raise ValidationError(
            f"no range constant for {companions} companions", field="companions"
        )
    return _RANGE_CONSTANT[companions]


def overall_standard(deviation: Quantity) -> ControlStandard:
    """Grade the spread between tests, for ordinary construction."""
    if deviation.dimension.value != "pressure":
        raise ValidationError("a standard deviation is a pressure", field="deviation")
    psi = deviation.to("psi").value
    if psi < 400.0:
        return ControlStandard.EXCELLENT
    if psi < 500.0:
        return ControlStandard.VERY_GOOD
    if psi < 600.0:
        return ControlStandard.GOOD
    if psi < 700.0:
        return ControlStandard.FAIR
    return ControlStandard.POOR


def within_test_standard(variation: Percent) -> ControlStandard:
    """Grade the spread between companions, for ordinary construction."""
    value = variation.value
    if value < 3.0:
        return ControlStandard.EXCELLENT
    if value < 4.0:
        return ControlStandard.VERY_GOOD
    if value < 5.0:
        return ControlStandard.GOOD
    if value < 6.0:
        return ControlStandard.FAIR
    return ControlStandard.POOR


@dataclass(frozen=True, slots=True)
class ControlReading:
    """One record's two variations, and what they grade as."""

    test_count: int
    mean: Quantity
    overall_deviation: Quantity
    within_test_deviation: Quantity
    companions: int

    @property
    def overall_variation(self) -> Percent:
        """The spread between tests, as a share of the mean."""
        return Percent.from_fraction(self.overall_deviation.base_value / self.mean.base_value)

    @property
    def within_test_variation(self) -> Percent:
        """The spread between companions, as a share of the mean."""
        return Percent.from_fraction(
            self.within_test_deviation.base_value / self.mean.base_value
        )

    @property
    def overall_grade(self) -> ControlStandard:
        """How the plant is doing."""
        return overall_standard(self.overall_deviation)

    @property
    def within_test_grade(self) -> ControlStandard:
        """How the laboratory is doing."""
        return within_test_standard(self.within_test_variation)

    @property
    def is_enough_tests(self) -> bool:
        """True when there are enough tests for the grades to mean anything."""
        return self.test_count >= MIN_TESTS

    @property
    def where_the_problem_is(self) -> str:
        """Which of the two needs looking at first."""
        plant = self.overall_grade.needs_attention
        lab = self.within_test_grade.needs_attention
        if plant and lab:
            return "both the plant and the laboratory"
        if lab:
            return "the laboratory"
        if plant:
            return "the plant"
        return "neither"

    def describe(self) -> str:
        """One line for a control report."""
        tail = "" if self.is_enough_tests else f" (only {self.test_count} tests)"
        return (
            f"overall {self.overall_deviation.format(0)} "
            f"({self.overall_variation.format(1)}, {self.overall_grade}), "
            f"within test {self.within_test_variation.format(1)} "
            f"({self.within_test_grade}){tail}"
        )


def read_control(tests: Sequence[StrengthTest]) -> ControlReading:
    """Work both variations out of a record of strength tests.

    Only sets with the same number of companions are used for the within-test
    figure, because the range constant depends on that number. Mixing two and
    three cylinder sets and dividing by one constant is the error this refuses
    to make.
    """
    usable = [test for test in tests if test.counts_for_acceptance]
    if len(usable) < 2:
        raise ValidationError("a standard of control needs at least two tests", field="tests")
    strengths = [test.average.to("psi").value for test in usable]
    mean = sum(strengths) / len(strengths)
    variance = sum((value - mean) ** 2 for value in strengths) / (len(strengths) - 1)
    overall = Quantity(math.sqrt(variance), "psi")
    counts = [len(test.breaks) for test in usable]
    common = max(set(counts), key=counts.count)
    matching = [test for test in usable if len(test.breaks) == common]
    ranges = [test.within_test_range.to("psi").value for test in matching]
    within = Quantity(sum(ranges) / len(ranges) / range_constant(common), "psi")
    return ControlReading(len(usable), Quantity(mean, "psi"), overall, within, common)
