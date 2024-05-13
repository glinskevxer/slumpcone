"""Temperature limits, which are a table in two directions at once.

The minimum temperature concrete may be placed at depends on how thick the
section is: a thin slab loses heat fast and has to start warmer. The minimum it
has to be *mixed* at depends on the same thickness and on how cold the air is,
because a colder day takes more heat out of the load between the plant and the
forms.

So there are two limits, they come from the same table read two ways, and only
one of them is a property of the concrete alone. The placement limit is the one
an inspector holds a load to. The mixing limit is the one the plant has to hit
so the placement limit is still met when the truck arrives.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature

# Above this the mixture is in hot weather territory whatever the specification
# says, and a lower ceiling is common on mass sections and on long hauls.
DEFAULT_MAX_PLACEMENT = Temperature(95.0, "F")

# The conversion out of millimetres lands a float ulp under a whole number of
# inches, so a bare comparison puts a twelve inch section in the wrong band.
_EDGE = 1e-9


class SectionSize(Enum):
    """How thick the least dimension of the section being placed is."""

    THIN = "thin"
    MODERATE = "moderate"
    THICK = "thick"
    MASS = "mass"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def of(cls, least_dimension: Quantity) -> SectionSize:
        """Which band a section falls in, from its least dimension."""
        if least_dimension.dimension.value != "length":
            raise ValidationError("a section dimension is a length", field="least_dimension")
        if least_dimension.value <= 0.0:
            raise ValidationError(
                "a section dimension has to be positive", field="least_dimension"
            )
        # The conversion out of millimetres lands a float ulp under a whole
        # number of inches often enough that a bare comparison puts a twelve
        # inch section in the wrong band.
        inches = least_dimension.to("in").value
        if inches < 12.0 - _EDGE:
            return cls.THIN
        if inches < 36.0 - _EDGE:
            return cls.MODERATE
        if inches <= 72.0 + _EDGE:
            return cls.THICK
        return cls.MASS

    @property
    def min_placement(self) -> Temperature:
        """The lowest temperature this section may be placed at."""
        table = {
            SectionSize.THIN: 55.0,
            SectionSize.MODERATE: 50.0,
            SectionSize.THICK: 45.0,
            SectionSize.MASS: 40.0,
        }
        return Temperature(table[self], "F")


class AmbientBand(Enum):
    """How cold it is outside, in the three bands the table uses."""

    ABOVE_FREEZING = "above_freezing"
    COLD = "cold"
    SEVERE = "severe"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def of(cls, ambient: Temperature) -> AmbientBand:
        """Which band an air temperature falls in."""
        degrees = ambient.fahrenheit
        if degrees > 30.0:
            return cls.ABOVE_FREEZING
        if degrees >= 0.0:
            return cls.COLD
        return cls.SEVERE

    @property
    def extra_over_placement(self) -> float:
        """Degrees F the mixing minimum sits above the placement minimum."""
        table = {
            AmbientBand.ABOVE_FREEZING: 5.0,
            AmbientBand.COLD: 10.0,
            AmbientBand.SEVERE: 15.0,
        }
        return table[self]


def min_mixing_temperature(section: SectionSize, ambient: Temperature) -> Temperature:
    """The lowest temperature a load may leave the plant at."""
    return Temperature(
        section.min_placement.fahrenheit + AmbientBand.of(ambient).extra_over_placement, "F"
    )


@dataclass(frozen=True, slots=True)
class TemperatureVerdict:
    """One concrete temperature against the limits that apply to it."""

    reading: Temperature
    section: SectionSize
    minimum: Temperature
    maximum: Temperature
    is_mixing_check: bool

    @property
    def too_cold(self) -> bool:
        """True when the load is below the floor."""
        return self.reading < self.minimum

    @property
    def too_hot(self) -> bool:
        """True when the load is above the ceiling."""
        return self.reading > self.maximum

    @property
    def conforms(self) -> bool:
        """True when the reading is inside both limits."""
        return not (self.too_cold or self.too_hot)

    def describe(self) -> str:
        """One line naming which limit was missed."""
        stage = "as mixed" if self.is_mixing_check else "as placed"
        if self.too_cold:
            return (
                f"{self.reading} {stage} is below the {self.minimum} floor "
                f"for a {self.section} section"
            )
        if self.too_hot:
            return f"{self.reading} {stage} is above the {self.maximum} ceiling"
        return f"{self.reading} {stage} is inside {self.minimum} to {self.maximum}"


def judge_placement_temperature(
    reading: Temperature,
    least_dimension: Quantity,
    *,
    maximum: Temperature = DEFAULT_MAX_PLACEMENT,
) -> TemperatureVerdict:
    """Judge a temperature taken at the point of placement."""
    section = SectionSize.of(least_dimension)
    return TemperatureVerdict(reading, section, section.min_placement, maximum, False)


def judge_mixing_temperature(
    reading: Temperature,
    least_dimension: Quantity,
    ambient: Temperature,
    *,
    maximum: Temperature = DEFAULT_MAX_PLACEMENT,
) -> TemperatureVerdict:
    """Judge a temperature taken as the load leaves the plant."""
    section = SectionSize.of(least_dimension)
    return TemperatureVerdict(
        reading, section, min_mixing_temperature(section, ambient), maximum, True
    )
