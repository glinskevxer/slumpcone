"""Whether a test record may be used to set a required average strength.

A standard deviation is only worth anything if the record it came out of
actually resembles the work it is being used for. ACI puts four conditions on
that and every one of them has been quietly ignored somewhere: enough
consecutive tests, a long enough stretch of time, a specified strength close to
the one being designed for, and similar materials and control.

The last one cannot be checked by software and is recorded as a declaration
rather than inferred. What the code can do is refuse to let it default to true
silently, which is why it is a field on the record and not an argument to the
function that uses it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.strength.required import (
    FULL_RECORD_TESTS,
    MIN_RECORD_TESTS,
    sample_standard_deviation,
)
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity

# How far the record's own specified strength may sit from the one being
# designed for.
MAX_STRENGTH_DIFFERENCE = Quantity(1000.0, "psi")

# The shortest stretch of time a record may cover.
MIN_SPAN_DAYS = 45


@dataclass(frozen=True, slots=True)
class TestRecord:
    """A run of consecutive strength tests from one mixture."""

    mix_code: str
    specified: Quantity
    tests: tuple[StrengthTest, ...]
    materials_are_similar: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "mix_code", normalize_code(self.mix_code, field="mix_code"))
        if self.specified.dimension.value != "pressure":
            raise ValidationError("a specified strength is a pressure", field="specified")
        if self.specified.value <= 0.0:
            raise ValidationError("a specified strength has to be positive", field="specified")
        codes = [test.set_code for test in self.tests]
        if len(set(codes)) != len(codes):
            raise ValidationError("the same set appears twice in a record", field="tests")

    @property
    def usable_tests(self) -> tuple[StrengthTest, ...]:
        """The tests in the record that count, oldest first."""
        return tuple(
            sorted(
                (test for test in self.tests if test.counts_for_acceptance),
                key=lambda test: (test.tested_on, test.set_code),
            )
        )

    @property
    def count(self) -> int:
        """How many usable tests the record holds."""
        return len(self.usable_tests)

    @property
    def strengths(self) -> tuple[Quantity, ...]:
        """Each usable test's result, oldest first."""
        return tuple(test.average for test in self.usable_tests)

    @property
    def span_days(self) -> int:
        """How many days the record covers, first break to last."""
        usable = self.usable_tests
        if len(usable) < 2:
            return 0
        return (usable[-1].tested_on - usable[0].tested_on).days

    @property
    def deviation(self) -> Quantity:
        """The sample standard deviation of the record."""
        return sample_standard_deviation(self.strengths)

    @property
    def mean(self) -> Quantity:
        """The average of every usable test in the record."""
        if not self.strengths:
            raise ValidationError("an empty record has no mean", field="tests")
        total = Quantity.zero("psi")
        for strength in self.strengths:
            total = total + strength.to("psi")
        return total * (1.0 / len(self.strengths))

    def disqualifications(self, target: Quantity) -> tuple[str, ...]:
        """Why this record may not be used for ``target``, if it may not."""
        found: list[str] = []
        if self.count < MIN_RECORD_TESTS:
            found.append(f"{self.count} usable tests, at least {MIN_RECORD_TESTS} are needed")
        if self.span_days < MIN_SPAN_DAYS:
            found.append(f"covers {self.span_days} days, at least {MIN_SPAN_DAYS} are needed")
        difference = abs(self.specified - target.to(self.specified.unit))
        if difference > MAX_STRENGTH_DIFFERENCE:
            found.append(
                f"produced at {self.specified.format(0)}, which is "
                f"{difference.format(0)} from {target.format(0)}"
            )
        if not self.materials_are_similar:
            found.append("materials and control have not been declared similar")
        return tuple(found)

    def qualifies_for(self, target: Quantity) -> bool:
        """True when this record may set a required average strength."""
        return not self.disqualifications(target)

    @property
    def is_full(self) -> bool:
        """True when the record is long enough to use its deviation as it is."""
        return self.count >= FULL_RECORD_TESTS

    def describe(self) -> str:
        """One line for a submittal."""
        return (
            f"{self.mix_code}  {self.count} tests over {self.span_days} days at "
            f"{self.specified.format(0)}  mean {self.mean.format(0)}  "
            f"s = {self.deviation.format(0)}"
        )


def statistical_average_deviation(first: TestRecord, second: TestRecord) -> Quantity:
    """Combine two records' deviations into one, the way ACI allows.

    This is not the deviation of the two records pooled together. It is a
    weighted average of their variances, which is a different number, and using
    the pooled deviation instead credits the plant with variability it has not
    demonstrated.
    """
    counts = (first.count, second.count)
    if min(counts) < 2:
        raise ValidationError("both records need at least two tests to combine", field="tests")
    numerator = (counts[0] - 1) * first.deviation.to("psi").value ** 2 + (
        counts[1] - 1
    ) * second.deviation.to("psi").value ** 2
    return Quantity(math.sqrt(numerator / (counts[0] + counts[1] - 2)), "psi")


def combined_count(first: TestRecord, second: TestRecord) -> int:
    """How many tests two records hold between them."""
    return first.count + second.count
