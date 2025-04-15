"""Bleeding and segregation, the two ways a mix comes apart while it sits.

Bleeding is water rising. C232 measures it two ways off the same test and they
are not interchangeable: the rate says how fast the finishers have to wait, the
total says how much water left the paste. A mix can bleed slowly and still bleed
a lot.

Segregation is aggregate sinking. C1610 saws a column into three and compares
the coarse aggregate at the top against the bottom. C1611 has an eyeball version
for self consolidating concrete, the visual stability index, which is a number
somebody assigns rather than one anything measures. Both are here because a
plant uses whichever the job asked for.

Bleeding numbers get quoted as percentages of two different denominators in the
field. This module only ever divides by the mixing water in the sample, which is
what C232 says, and every returned percentage says so in its name.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from slumpcone.errors import RuleViolationError
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# Water at room temperature. C232 works in mass and converts with this, and the
# standard is explicit that the density of the bleed water is taken as water's.
WATER_DENSITY_LB_FT3 = 62.4


class BleedingError(RuleViolationError):
    """A bleeding or segregation test that cannot mean anything."""


class VisualStability(Enum):
    """C1611 appendix, the index a technician assigns to an SCC spread."""

    STABLE = 0
    STABLE_WITH_SHEEN = 1
    SLIGHT_HALO = 2
    SEGREGATING = 3

    def __str__(self) -> str:
        return self.name.lower().replace("_", " ")

    @property
    def is_acceptable(self) -> bool:
        """0 and 1 pass, 2 is a warning that most specifiers still take, 3 fails."""
        return self.value <= 2

    @property
    def note(self) -> str:
        """What the technician saw."""
        return {
            VisualStability.STABLE: "no evidence of bleeding or separation",
            VisualStability.STABLE_WITH_SHEEN: "a slight sheen, no mortar halo",
            VisualStability.SLIGHT_HALO: "a mortar halo under 10 mm or a water sheen",
            VisualStability.SEGREGATING: "a mortar halo over 10 mm, aggregate piled centre",
        }[self]


@dataclass(frozen=True, slots=True)
class BleedReading:
    """One draw off the surface, C232 style."""

    elapsed_minutes: float
    water: Quantity

    def __post_init__(self) -> None:
        if self.elapsed_minutes <= 0:
            raise BleedingError("BLEED_READING_NOT_ELAPSED", "a reading needs elapsed time")
        if self.water.base_value < 0:
            raise BleedingError("BLEED_READING_NEGATIVE", "bleed water cannot be negative")


@dataclass(frozen=True, slots=True)
class BleedTest:
    """A C232 test on a sample of known mass drawn from a batch of known water."""

    ticket_number: str
    sample_mass: Quantity
    batch_mass: Quantity
    batch_water: Quantity
    surface_area: Quantity
    readings: tuple[BleedReading, ...] = field(default=())

    def __post_init__(self) -> None:
        for name, value in (
            ("sample", self.sample_mass),
            ("batch", self.batch_mass),
            ("water", self.batch_water),
            ("area", self.surface_area),
        ):
            if value.base_value <= 0:
                raise BleedingError(
                    "BLEED_TEST_NOT_POSITIVE", f"the {name} figure has to be positive"
                )
        if self.sample_mass.to("lb").value > self.batch_mass.to("lb").value:
            raise BleedingError(
                "BLEED_SAMPLE_OVER_BATCH", "the sample cannot outweigh the batch it came from"
            )
        elapsed = [reading.elapsed_minutes for reading in self.readings]
        if elapsed != sorted(elapsed):
            raise BleedingError(
                "BLEED_READINGS_UNORDERED", "readings have to run forward in time"
            )

    @property
    def sample_water(self) -> Quantity:
        """The mixing water carried by the sample, C232 clause 9.1.

        The sample is a known fraction of the batch by mass, so it carries the
        same fraction of the batch water.
        """
        share = self.sample_mass.to("lb").value / self.batch_mass.to("lb").value
        return self.batch_water.to("lb") * share

    @property
    def total_water(self) -> Quantity:
        """Every draw added up."""
        total = Quantity(0.0, "lb")
        for reading in self.readings:
            total = total + reading.water.to("lb")
        return total

    @property
    def duration_minutes(self) -> float:
        """How long the test ran."""
        return self.readings[-1].elapsed_minutes if self.readings else 0.0

    @property
    def bleeding_percent_of_mixing_water(self) -> Percent:
        """Total bleed water over the sample's mixing water."""
        return Percent.from_fraction(self.total_water.value / self.sample_water.to("lb").value)

    @property
    def bleeding_volume_per_area(self) -> float:
        """Bleed water per unit of surface, in cubic inches per square inch.

        This is a depth, and reads as one: the standard reports it in mL/cm2 in
        metric, which is the same quantity.
        """
        volume_ft3 = self.total_water.value / WATER_DENSITY_LB_FT3
        return (volume_ft3 * 1728.0) / self.surface_area.to("in2").value

    def rate_percent_per_hour(self, *, after_minutes: float = 0.0) -> Percent:
        """The average bleeding rate over a stretch of the test.

        Bleeding is fastest early and tails off, so the useful rate is nearly
        always the one measured after the first draw rather than over the whole
        run. That is what after_minutes is for.
        """
        window = [
            reading for reading in self.readings if reading.elapsed_minutes > after_minutes
        ]
        if not window:
            raise BleedingError("BLEED_RATE_NO_WINDOW", "no readings fall after that point")
        drawn = Quantity(0.0, "lb")
        for reading in window:
            drawn = drawn + reading.water.to("lb")
        hours = (window[-1].elapsed_minutes - after_minutes) / 60.0
        share = drawn.value / self.sample_water.to("lb").value
        return Percent.from_fraction(share / hours)

    def describe(self) -> str:
        """One line."""
        return (
            f"{self.ticket_number}: bled "
            f"{self.bleeding_percent_of_mixing_water.format(2)} of its mixing water "
            f"over {self.duration_minutes:.0f} min"
        )


@dataclass(frozen=True, slots=True)
class ColumnSegregation:
    """C1610, a sawn column compared top against bottom."""

    ticket_number: str
    top_coarse: Quantity
    bottom_coarse: Quantity

    def __post_init__(self) -> None:
        if self.top_coarse.base_value < 0 or self.bottom_coarse.base_value < 0:
            raise BleedingError("SEGREGATION_NEGATIVE", "an aggregate mass cannot be negative")
        if self.top_coarse.is_zero() and self.bottom_coarse.is_zero():
            raise BleedingError(
                "SEGREGATION_NO_AGGREGATE", "neither section held any coarse aggregate"
            )

    @property
    def index(self) -> Percent:
        """The static segregation index, C1610 clause 10.

        Twice the difference over the sum, so a column that has not moved reads
        zero and one that has sent everything to the floor reads 200.
        """
        top = self.top_coarse.to("lb").value
        bottom = self.bottom_coarse.to("lb").value
        return Percent.from_fraction(2.0 * (bottom - top) / (bottom + top))

    @property
    def is_acceptable(self) -> bool:
        """Most specifiers cap the index at 10 percent for SCC."""
        return self.index.value <= 10.0

    @property
    def direction(self) -> str:
        """Which way the aggregate went, which is not always down."""
        if abs(self.index.value) < 1.0:
            return "uniform"
        return "settled" if self.index.value > 0 else "risen"

    def describe(self) -> str:
        """One line."""
        return (
            f"{self.ticket_number}: segregation index {self.index.format(1)}, {self.direction}"
        )


def worst_bleeder(tests: Sequence[BleedTest]) -> BleedTest | None:
    """The test that lost the most of its mixing water."""
    if not tests:
        return None
    return max(tests, key=lambda test: test.bleeding_percent_of_mixing_water.value)
