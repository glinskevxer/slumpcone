"""How often a class of concrete has to be sampled.

Three rules, and the answer is the largest of them. At least once a day the
class is placed. At least once for every hundred and fifty cubic yards. And,
for slabs and walls, at least once for every five thousand square feet of
surface, which is the one that catches people out: a thin slab covering a lot
of ground makes the area rule bind long before the volume rule does.

There is also a waiver, and it is narrow. Below fifty cubic yards of a class in
total, strength tests may be waived if the specifying authority accepts other
evidence. It is a waiver of the *strength* tests only, it is not automatic, and
it is against the whole class rather than a day of it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity

VOLUME_PER_SAMPLE = Quantity(150.0, "yd3")
AREA_PER_SAMPLE = Quantity(5000.0, "ft2")
WAIVER_VOLUME = Quantity(50.0, "yd3")


@dataclass(frozen=True, slots=True)
class SamplingRequirement:
    """How many samples a placement calls for, and which rule asked for it."""

    from_days: int
    from_volume: int
    from_area: int

    @property
    def required(self) -> int:
        """The largest of the three, which is the number that applies."""
        return max(self.from_days, self.from_volume, self.from_area)

    @property
    def governing_rule(self) -> str:
        """Which rule set the number."""
        if self.required == 0:
            return "none"
        if self.from_area == self.required and self.from_area > self.from_volume:
            return "surface area"
        if self.from_volume == self.required and self.from_volume > self.from_days:
            return "volume"
        if self.from_days == self.required:
            return "one a day"
        return "volume"

    def describe(self) -> str:
        """One line for a frequency report."""
        return (
            f"{self.required} sample(s) required by the {self.governing_rule} rule "
            f"(days {self.from_days}, volume {self.from_volume}, area {self.from_area})"
        )


def required_samples(
    volume: Quantity, placement_days: int, surface_area: Quantity | None = None
) -> SamplingRequirement:
    """How many samples a class needs over a placement.

    A surface area is only supplied for slabs and walls. Everything else has no
    meaningful surface, and passing one for a footing would invent a
    requirement the specification does not make.
    """
    if volume.dimension.value != "volume":
        raise ValidationError("a placed quantity is a volume", field="volume")
    if volume.value < 0.0:
        raise ValidationError("a placed quantity cannot be negative", field="volume")
    if placement_days < 0:
        raise ValidationError("placement days cannot be negative", field="placement_days")
    if surface_area is not None and surface_area.dimension.value != "area":
        raise ValidationError("a surface area is an area", field="surface_area")
    if volume.is_zero():
        return SamplingRequirement(0, 0, 0)
    from_volume = math.ceil(volume.base_value / VOLUME_PER_SAMPLE.base_value)
    from_area = (
        0
        if surface_area is None
        else math.ceil(surface_area.base_value / AREA_PER_SAMPLE.base_value)
    )
    return SamplingRequirement(max(placement_days, 1), from_volume, from_area)


def may_waive_strength_tests(volume: Quantity) -> bool:
    """True when the total volume of a class is small enough for a waiver.

    A waiver is *available*, not granted. Whether it is taken is the specifying
    authority's decision and belongs on the project record rather than here.
    """
    if volume.dimension.value != "volume":
        raise ValidationError("a placed quantity is a volume", field="volume")
    return volume < WAIVER_VOLUME


@dataclass(frozen=True, slots=True)
class FrequencyFinding:
    """One class that was not sampled often enough."""

    class_code: str
    volume: Quantity
    requirement: SamplingRequirement
    taken: int
    waiver_available: bool

    @property
    def shortfall(self) -> int:
        """How many samples were missed."""
        return max(self.requirement.required - self.taken, 0)

    @property
    def conforms(self) -> bool:
        """True when enough samples were taken, or a waiver is available."""
        return self.shortfall == 0 or self.waiver_available

    def describe(self) -> str:
        """One line for a frequency report."""
        if self.shortfall == 0:
            return f"{self.class_code}: {self.taken} of {self.requirement.required} samples, ok"
        tail = ", but a waiver is available below 50 yd3" if self.waiver_available else ""
        return (
            f"{self.class_code}: {self.taken} of {self.requirement.required} samples on "
            f"{self.volume.format(1)}, {self.shortfall} short{tail}"
        )


def check_frequency(
    class_code: str,
    volume: Quantity,
    placement_days: int,
    samples_taken: int,
    surface_area: Quantity | None = None,
) -> FrequencyFinding:
    """Judge one class's sampling frequency over a placement."""
    if samples_taken < 0:
        raise ValidationError("a sample count cannot be negative", field="samples_taken")
    requirement = required_samples(volume, placement_days, surface_area)
    return FrequencyFinding(
        class_code.strip().upper(),
        volume,
        requirement,
        samples_taken,
        may_waive_strength_tests(volume),
    )
