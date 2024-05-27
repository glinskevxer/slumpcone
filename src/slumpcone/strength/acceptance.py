"""ACI's two strength acceptance rules, which are not the same rule twice.

The first is about the average: every arithmetic average of three consecutive
strength tests has to reach the specified strength. That is the rule the mixture
is designed against, and passing it is what over-designing the mixture buys.

The second is about the individual: no single test may fall more than a fixed
margin below the specified strength. That margin is 500 psi up to a specified
strength of 5000, and a tenth of the specified strength above it, so the two
branches cross exactly at 5000 and a mixture specified at 5000 is judged on the
tighter reading of the two.

They fail independently. A record of consistently high tests with one very low
one passes the first and fails the second, and a record that hovers just under
the specified strength does the opposite.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity

# The specified strength at which the individual test rule changes branch.
BRANCH_STRENGTH = Quantity(5000.0, "psi")
FIXED_MARGIN = Quantity(500.0, "psi")
PROPORTIONAL_MARGIN = 0.10

# How many consecutive tests the moving average runs over.
MOVING_AVERAGE_LENGTH = 3


class StrengthStatus(Enum):
    """Where a record of strength tests stands."""

    NOT_ENOUGH_TESTS = "not_enough_tests"
    SATISFACTORY = "satisfactory"
    INVESTIGATE = "investigate"

    def __str__(self) -> str:
        return self.value

    @property
    def needs_action(self) -> bool:
        """True when somebody has to do something about it."""
        return self is StrengthStatus.INVESTIGATE


def individual_floor(specified: Quantity) -> Quantity:
    """The lowest a single strength test may go.

    Below a specified strength of 5000 psi the margin is a flat 500. Above it
    the margin is a tenth of the specified strength, which is wider in absolute
    terms and tighter as a proportion.
    """
    if specified.dimension.value != "pressure":
        raise ValidationError("a specified strength is a pressure", field="specified")
    if specified.value <= 0.0:
        raise ValidationError("a specified strength has to be positive", field="specified")
    if specified > BRANCH_STRENGTH:
        return specified * (1.0 - PROPORTIONAL_MARGIN)
    return specified - FIXED_MARGIN.to(specified.unit)


@dataclass(frozen=True, slots=True)
class MovingAverage:
    """One window of consecutive tests, averaged."""

    set_codes: tuple[str, ...]
    average: Quantity
    specified: Quantity

    @property
    def meets(self) -> bool:
        """True when the window reaches the specified strength."""
        return self.average >= self.specified

    @property
    def margin(self) -> Quantity:
        """How far above the specified strength the window sits."""
        return self.average - self.specified.to(self.average.unit)

    def describe(self) -> str:
        """One line for a strength report."""
        verdict = "ok" if self.meets else "below"
        return (
            f"{', '.join(self.set_codes)}  {self.average.format(0)}  "
            f"{self.margin.format(0)}  {verdict}"
        )


@dataclass(frozen=True, slots=True)
class LowTest:
    """One strength test that fell below the individual floor."""

    set_code: str
    result: Quantity
    floor: Quantity

    @property
    def shortfall(self) -> Quantity:
        """How far under the floor it landed."""
        return self.floor.to(self.result.unit) - self.result

    def describe(self) -> str:
        """One line for a strength report."""
        return (
            f"{self.set_code}  {self.result.format(0)}  "
            f"{self.shortfall.format(0)} below the {self.floor.format(0)} floor"
        )


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    """A mix's acceptance record against one specified strength."""

    mix_code: str
    specified: Quantity
    tests: tuple[StrengthTest, ...]
    windows: tuple[MovingAverage, ...]
    low_tests: tuple[LowTest, ...]
    status: StrengthStatus

    @property
    def failing_windows(self) -> tuple[MovingAverage, ...]:
        """Every window that did not reach the specified strength."""
        return tuple(window for window in self.windows if not window.meets)

    @property
    def reasons(self) -> tuple[str, ...]:
        """Why the record is unsatisfactory, if it is."""
        found: list[str] = []
        for window in self.failing_windows:
            found.append(
                f"the average of {', '.join(window.set_codes)} is "
                f"{window.average.format(0)}, below the specified "
                f"{self.specified.format(0)}"
            )
        for low in self.low_tests:
            found.append(low.describe())
        return tuple(found)

    def describe(self) -> str:
        """A short report."""
        lines = [
            f"{self.mix_code} against {self.specified.format(0)}: {self.status} "
            f"on {len(self.tests)} tests"
        ]
        lines.extend(f"  {reason}" for reason in self.reasons)
        return "\n".join(lines)


def evaluate_strength(
    mix_code: str, tests: Sequence[StrengthTest], specified: Quantity
) -> AcceptanceReport:
    """Run both acceptance rules over a mix's tests, oldest first.

    Only tests that count for acceptance are used. A field cured set or an
    incomplete set is dropped before either rule runs, because letting one into
    the moving average moves a window that the specification never intended it
    to touch.
    """
    floor = individual_floor(specified)
    usable = tuple(
        test
        for test in sorted(tests, key=lambda t: (t.tested_on, t.set_code))
        if test.counts_for_acceptance
    )
    windows: list[MovingAverage] = []
    for index in range(len(usable) - MOVING_AVERAGE_LENGTH + 1):
        members = usable[index : index + MOVING_AVERAGE_LENGTH]
        total = Quantity.zero("psi")
        for member in members:
            total = total + member.average.to("psi")
        windows.append(
            MovingAverage(
                tuple(member.set_code for member in members),
                total * (1.0 / MOVING_AVERAGE_LENGTH),
                specified,
            )
        )
    low = tuple(
        LowTest(test.set_code, test.average, floor) for test in usable if test.average < floor
    )
    failing = [window for window in windows if not window.meets]
    if not usable:
        status = StrengthStatus.NOT_ENOUGH_TESTS
    elif failing or low:
        status = StrengthStatus.INVESTIGATE
    elif len(usable) < MOVING_AVERAGE_LENGTH:
        status = StrengthStatus.NOT_ENOUGH_TESTS
    else:
        status = StrengthStatus.SATISFACTORY
    return AcceptanceReport(mix_code, specified, usable, tuple(windows), low, status)
