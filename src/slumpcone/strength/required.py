"""Required average strength, which is what the mixture is actually designed for.

Nobody proportions a mixture to the specified strength. They proportion it to a
higher number that leaves enough room for the plant's own variability that the
acceptance rules still pass. How much higher depends entirely on how consistent
the plant has proved itself to be.

With a long test record the margin comes out of the record's standard deviation
by two formulas, and the larger answer wins. With a short record the deviation
is inflated by a modification factor first, because a standard deviation from
eighteen tests is itself uncertain. With no record at all the margin is a flat
table lookup, and it is deliberately punitive: a plant with no data pays for it
in cement.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity

# Below this many tests a record cannot be used at all.
MIN_RECORD_TESTS = 15

# At or above this many tests the deviation is taken at face value.
FULL_RECORD_TESTS = 30

# The specified strength at which both tables change branch.
BRANCH_STRENGTH = Quantity(5000.0, "psi")

# Table 26.4.3.1.2, the inflation applied to a deviation from a short record.
_MODIFICATION: tuple[tuple[int, float], ...] = (
    (15, 1.16),
    (20, 1.08),
    (25, 1.03),
    (30, 1.00),
)


def sample_standard_deviation(strengths: Sequence[Quantity]) -> Quantity:
    """The sample standard deviation of a set of strength tests.

    Sample, not population: the divisor is one less than the count, because the
    record is a sample of what the plant can do rather than the whole of it.
    """
    if len(strengths) < 2:
        raise ValidationError(
            "a standard deviation needs at least two tests", field="strengths"
        )
    values = [strength.to("psi").value for strength in strengths]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return Quantity(math.sqrt(variance), "psi")


def modification_factor(test_count: int) -> float:
    """How much a deviation from ``test_count`` tests is inflated by.

    Interpolated between the table rows, which is what the table itself says to
    do. Below fifteen tests there is no factor because there is no usable
    record.
    """
    if test_count < MIN_RECORD_TESTS:
        raise ValidationError(
            f"a record of {test_count} tests is below the {MIN_RECORD_TESTS} needed",
            field="test_count",
        )
    if test_count >= FULL_RECORD_TESTS:
        return 1.0
    for (low_count, low_factor), (high_count, high_factor) in zip(
        _MODIFICATION, _MODIFICATION[1:], strict=False
    ):
        if low_count <= test_count <= high_count:
            span = high_count - low_count
            share = (test_count - low_count) / span
            return low_factor + share * (high_factor - low_factor)
    return 1.0


def required_from_deviation(specified: Quantity, deviation: Quantity) -> Quantity:
    """The required average strength from a known standard deviation.

    Two formulas, larger wins. The first keeps the moving average of three
    above the specified strength; the second keeps individual tests above the
    floor. Which one binds depends on how variable the plant is, and it flips
    around a deviation of about 500 psi.
    """
    if specified.dimension.value != "pressure":
        raise ValidationError("a specified strength is a pressure", field="specified")
    if deviation.dimension.value != "pressure":
        raise ValidationError("a standard deviation is a pressure", field="deviation")
    if specified.value <= 0.0:
        raise ValidationError("a specified strength has to be positive", field="specified")
    if deviation.value < 0.0:
        raise ValidationError("a standard deviation cannot be negative", field="deviation")
    psi = specified.to("psi").value
    sigma = deviation.to("psi").value
    average_rule = psi + 1.34 * sigma
    if specified > BRANCH_STRENGTH:
        individual_rule = 0.90 * psi + 2.33 * sigma
    else:
        individual_rule = psi + 2.33 * sigma - 500.0
    return Quantity(max(average_rule, individual_rule), "psi")


def required_without_record(specified: Quantity) -> Quantity:
    """The required average strength when there is no usable test record."""
    if specified.dimension.value != "pressure":
        raise ValidationError("a specified strength is a pressure", field="specified")
    if specified.value <= 0.0:
        raise ValidationError("a specified strength has to be positive", field="specified")
    psi = specified.to("psi").value
    if psi < 3000.0:
        return Quantity(psi + 1000.0, "psi")
    if psi <= 5000.0:
        return Quantity(psi + 1200.0, "psi")
    return Quantity(1.10 * psi + 700.0, "psi")


@dataclass(frozen=True, slots=True)
class RequiredStrength:
    """The number a mixture is proportioned to, and where it came from."""

    specified: Quantity
    required: Quantity
    basis: str
    deviation: Quantity | None = None
    test_count: int = 0
    factor: float = 1.0

    @property
    def margin(self) -> Quantity:
        """How far above the specified strength the mixture is designed."""
        return self.required - self.specified.to(self.required.unit)

    def describe(self) -> str:
        """One line for a submittal."""
        tail = ""
        if self.deviation is not None:
            tail = (
                f" from {self.test_count} tests, s = {self.deviation.format(0)}"
                f" x {self.factor:.2f}"
            )
        return (
            f"specified {self.specified.format(0)}, required "
            f"{self.required.format(0)} ({self.basis}{tail})"
        )


def required_average_strength(
    specified: Quantity, strengths: Sequence[Quantity] | None = None
) -> RequiredStrength:
    """Work out what a mixture has to be proportioned to.

    A record shorter than fifteen tests is treated as no record at all rather
    than as a weak one, which is what the standard says and is also the only
    safe reading: three tests can look consistent by luck.
    """
    if not strengths or len(strengths) < MIN_RECORD_TESTS:
        return RequiredStrength(
            specified,
            required_without_record(specified),
            "no qualifying record",
            test_count=0 if not strengths else len(strengths),
        )
    raw = sample_standard_deviation(strengths)
    factor = modification_factor(len(strengths))
    adjusted = raw * factor
    return RequiredStrength(
        specified,
        required_from_deviation(specified, adjusted),
        "test record",
        adjusted,
        len(strengths),
        factor,
    )
