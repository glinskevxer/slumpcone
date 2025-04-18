"""The mixer uniformity test, C94 Annex A1.

A truck mixer or a central mixer has to prove it puts the same concrete in the
front of the load as it does in the back. The test takes two samples out of one
batch, one after fifteen percent has discharged and one after eighty five, runs
six comparisons on them, and asks whether the differences stay under a table of
limits.

Two things about this test catch people out and both are handled here.

The first is that it does not require every comparison to pass. C94 says five of
the six, which means a mixer with one bad line still passes and a report that
says "failed" because one number is over is wrong. :class:`UniformityResult`
counts rather than ands.

The second is that two of the six limits are percentages of an average rather
than absolute differences, and two more are absolute. Mixing those up gives a
verdict that is wrong by a factor of about eighty. Every limit here carries the
basis it is measured on and the comparison reads it rather than assuming.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import RuleViolationError
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# Water at the temperature the unit weight measure is calibrated at. Absolute
# volumes in this test all run through it.
WATER_LB_FT3 = 62.4

# C94 A1.4: the test is judged on five of the six comparisons.
REQUIRED_PASSES = 5


class UniformityError(RuleViolationError):
    """A uniformity test that cannot be judged."""


class Basis(Enum):
    """What a limit is measured against."""

    ABSOLUTE = "absolute"
    SHARE_OF_AVERAGE = "share of average"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class UniformityLimit:
    """One row of C94 Table A1.1."""

    name: str
    limit: float
    basis: Basis
    unit: str = ""

    def difference(self, first: float, second: float) -> float:
        """The figure this row compares against its limit."""
        gap = abs(first - second)
        if self.basis is Basis.ABSOLUTE:
            return gap
        average = (first + second) / 2.0
        if average == 0.0:
            raise UniformityError(
                "UNIFORMITY_ZERO_AVERAGE",
                f"{self.name} averaged zero, so a share of the average means nothing",
            )
        return 100.0 * gap / average

    def judge(self, first: float, second: float) -> Comparison:
        """Run this row on a pair of sample readings."""
        found = self.difference(first, second)
        return Comparison(self.name, found, self.limit, self.basis, self.unit)


@dataclass(frozen=True, slots=True)
class Comparison:
    """One row of the test, run."""

    name: str
    found: float
    limit: float
    basis: Basis
    unit: str = ""

    @property
    def passed(self) -> bool:
        """True when the difference stayed inside the limit."""
        return self.found <= self.limit + 1e-9

    @property
    def margin(self) -> float:
        """How much room is left. Negative means over."""
        return self.limit - self.found

    def describe(self) -> str:
        """One line."""
        tail = "%" if self.basis is Basis.SHARE_OF_AVERAGE else f" {self.unit}".rstrip()
        return (
            f"{self.name}: {self.found:.2f}{tail} against {self.limit:.2f}{tail}, "
            f"{'ok' if self.passed else 'over'}"
        )


# C94 Table A1.1, in the order the standard prints it.
AIR_FREE_UNIT_WEIGHT = UniformityLimit("air free unit weight", 0.8, Basis.ABSOLUTE, "lb/ft3")
AIR_CONTENT = UniformityLimit("air content", 1.0, Basis.ABSOLUTE, "%")
COARSE_AGGREGATE = UniformityLimit("coarse aggregate", 6.0, Basis.ABSOLUTE, "%")
AIR_FREE_MORTAR = UniformityLimit("air free mortar unit weight", 1.6, Basis.SHARE_OF_AVERAGE)
SEVEN_DAY_STRENGTH = UniformityLimit("seven day strength", 7.5, Basis.SHARE_OF_AVERAGE)


def slump_limit(average_slump_in: float) -> UniformityLimit:
    """The slump row, whose limit depends on how wet the batch was.

    C94 gives one inch up to a four inch average and one and a half from four to
    six. Above six the standard stops, because the slump test stops meaning much
    there, and so does this.
    """
    if average_slump_in <= 0.0:
        raise UniformityError(
            "UNIFORMITY_SLUMP_NOT_POSITIVE", "an average slump has to be positive"
        )
    if average_slump_in > 6.0:
        raise UniformityError(
            "UNIFORMITY_SLUMP_OFF_TABLE",
            "C94 does not give a uniformity slump limit above a six inch average",
        )
    return UniformityLimit(
        "slump", 1.0 if average_slump_in <= 4.0 else 1.5, Basis.ABSOLUTE, "in"
    )


@dataclass(frozen=True, slots=True)
class UniformitySample:
    """One of the two samples pulled out of the batch."""

    label: str
    unit_weight: MassPerVolume
    air: Percent
    slump: Quantity
    coarse_retained: Percent
    coarse_specific_gravity: float
    sample_volume: Quantity
    coarse_mass: Quantity
    strength_7day: Quantity | None = None

    def __post_init__(self) -> None:
        if self.coarse_specific_gravity <= 0.0:
            raise UniformityError(
                "UNIFORMITY_NO_GRAVITY", "the coarse aggregate needs a specific gravity"
            )
        if self.sample_volume.base_value <= 0.0:
            raise UniformityError("UNIFORMITY_NO_VOLUME", "the sample needs a measured volume")
        if self.air.value < 0.0 or self.air.value >= 100.0:
            raise UniformityError(
                "UNIFORMITY_AIR_OFF_SCALE", "air content has to sit between 0 and 100 percent"
            )

    @property
    def air_free_unit_weight(self) -> float:
        """Unit weight put back on an air free basis, in lb/ft3."""
        return float(self.unit_weight.to("lb", "ft3").value / (1.0 - self.air.fraction))

    @property
    def sample_mass(self) -> Quantity:
        """What the whole sample weighed, from its unit weight and volume."""
        return Quantity(
            self.unit_weight.to("lb", "ft3").value * self.sample_volume.to("ft3").value, "lb"
        )

    @property
    def air_free_mortar_unit_weight(self) -> float:
        """Unit weight of the mortar with the coarse aggregate and the air taken out.

        C94 A1.4: take the coarse aggregate mass off the sample mass, and take
        the coarse aggregate's absolute volume and the air volume off the sample
        volume. What is left is mortar.
        """
        volume = self.sample_volume.to("ft3").value
        mortar_mass = self.sample_mass.value - self.coarse_mass.to("lb").value
        coarse_volume = self.coarse_mass.to("lb").value / (
            self.coarse_specific_gravity * WATER_LB_FT3
        )
        mortar_volume = volume - coarse_volume - volume * self.air.fraction
        if mortar_volume <= 0.0:
            raise UniformityError(
                "UNIFORMITY_NO_MORTAR",
                f"sample {self.label} has no mortar left once the rock and air come out",
            )
        return float(mortar_mass / mortar_volume)


@dataclass(frozen=True, slots=True)
class UniformityResult:
    """A whole test, judged."""

    mixer: str
    comparisons: tuple[Comparison, ...]

    @property
    def passes(self) -> int:
        """How many rows stayed inside their limit."""
        return sum(1 for row in self.comparisons if row.passed)

    @property
    def failures(self) -> tuple[Comparison, ...]:
        """The rows that went over."""
        return tuple(row for row in self.comparisons if not row.passed)

    @property
    def is_uniform(self) -> bool:
        """C94 asks for five of six, not six of six."""
        return self.passes >= REQUIRED_PASSES

    def describe(self) -> str:
        """One line."""
        verdict = "uniform" if self.is_uniform else "not uniform"
        return (
            f"{self.mixer}: {self.passes} of {len(self.comparisons)} comparisons "
            f"inside the limit, {verdict}"
        )


def compare(mixer: str, first: UniformitySample, second: UniformitySample) -> UniformityResult:
    """Run C94 Table A1.1 on a pair of samples.

    The strength row only appears when both samples were broken at seven days,
    because C94 allows the test to be reported without it and a plant that has
    not waited a week still wants the other five.
    """
    if first.label == second.label:
        raise UniformityError(
            "UNIFORMITY_SAME_SAMPLE", "the two samples have to be told apart by label"
        )
    average_slump = (first.slump.to("in").value + second.slump.to("in").value) / 2.0
    rows = [
        AIR_FREE_UNIT_WEIGHT.judge(first.air_free_unit_weight, second.air_free_unit_weight),
        AIR_CONTENT.judge(first.air.value, second.air.value),
        slump_limit(average_slump).judge(
            first.slump.to("in").value, second.slump.to("in").value
        ),
        COARSE_AGGREGATE.judge(first.coarse_retained.value, second.coarse_retained.value),
        AIR_FREE_MORTAR.judge(
            first.air_free_mortar_unit_weight, second.air_free_mortar_unit_weight
        ),
    ]
    if first.strength_7day is not None and second.strength_7day is not None:
        rows.append(
            SEVEN_DAY_STRENGTH.judge(
                first.strength_7day.to("psi").value, second.strength_7day.to("psi").value
            )
        )
    return UniformityResult(mixer, tuple(rows))


def failing_mixers(results: Sequence[UniformityResult]) -> tuple[str, ...]:
    """The mixers that did not make five of six, in the order they were tested."""
    return tuple(result.mixer for result in results if not result.is_uniform)
