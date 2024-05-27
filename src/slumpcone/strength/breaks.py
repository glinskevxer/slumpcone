"""Breaking a cylinder, and the corrections between the load and the strength.

The machine reports a load. Turning it into a strength takes the measured area,
not the nominal one, and then a correction if the cylinder is short. A specimen
whose length has been ground or capped down to less than one and three quarter
diameters reads high, and C39 gives a factor to take that back out.

Two checks belong here rather than in a reviewer's head. A cylinder whose two
diameters differ by more than two percent is not testable at all. And a
fracture pattern that says the specimen was loaded off centre or capped badly
means the number is about the setup, not the concrete.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# Two diameters further apart than this and the cylinder is out of round.
MAX_DIAMETER_DIFFERENCE = Percent(2.0)

# Below this length to diameter ratio the reported strength needs correcting.
CORRECTION_THRESHOLD = 1.75

# C39's correction factors, coarsest first. Anything between two rows is
# interpolated; anything below the last row cannot be corrected at all.
_CORRECTIONS: tuple[tuple[float, float], ...] = (
    (1.75, 0.98),
    (1.50, 0.96),
    (1.25, 0.93),
    (1.00, 0.87),
)


class FractureType(Enum):
    """The pattern the cylinder broke in, by C39's numbering."""

    CONE = "cone"
    CONE_AND_SPLIT = "cone_and_split"
    COLUMNAR = "columnar"
    DIAGONAL = "diagonal"
    SIDE_FRACTURE = "side_fracture"
    POINTED_END = "pointed_end"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> FractureType:
        """Read a fracture type off a break sheet."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown fracture type {text!r}", field="fracture")

    @property
    def suggests_a_testing_fault(self) -> bool:
        """True when the pattern says the setup was wrong, not the concrete.

        A side fracture usually means the specimen was not centred, and a
        pointed end means the caps were not plane. Both give a low reading and
        neither is the concrete's fault.
        """
        return self in {FractureType.SIDE_FRACTURE, FractureType.POINTED_END}


def length_diameter_correction(ratio: float) -> float:
    """C39's correction factor for a short cylinder."""
    if ratio <= 0.0:
        raise ValidationError("a length to diameter ratio has to be positive", field="ratio")
    if ratio >= CORRECTION_THRESHOLD:
        return 1.0
    if ratio < _CORRECTIONS[-1][0]:
        raise ValidationError(
            f"a length to diameter ratio of {ratio:.2f} is below the {_CORRECTIONS[-1][0]:.2f} "
            "the correction table covers",
            field="ratio",
        )
    for (high_ratio, high_factor), (low_ratio, low_factor) in zip(
        _CORRECTIONS, _CORRECTIONS[1:], strict=False
    ):
        if low_ratio <= ratio <= high_ratio:
            span = high_ratio - low_ratio
            share = (ratio - low_ratio) / span
            return low_factor + share * (high_factor - low_factor)
    return 1.0


@dataclass(frozen=True, slots=True)
class BreakResult:
    """One cylinder taken to failure."""

    specimen_code: str
    tested_at: datetime
    age_days: float
    diameter_one: Quantity
    diameter_two: Quantity
    length: Quantity
    max_load: Quantity
    fracture: FractureType = FractureType.CONE
    tested_by: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "specimen_code", normalize_code(self.specimen_code, field="specimen_code")
        )
        if self.tested_by is not None:
            object.__setattr__(
                self, "tested_by", normalize_code(self.tested_by, field="tested_by")
            )
        for name, amount in (
            ("diameter_one", self.diameter_one),
            ("diameter_two", self.diameter_two),
            ("length", self.length),
        ):
            if amount.dimension.value != "length":
                raise ValidationError(f"{name} is a length", field=name)
            if amount.value <= 0.0:
                raise ValidationError(f"{name} has to be positive", field=name)
        if self.max_load.dimension.value != "force":
            raise ValidationError("a machine load is a force", field="max_load")
        if self.max_load.value <= 0.0:
            raise ValidationError("a machine load has to be positive", field="max_load")
        if self.age_days <= 0.0:
            raise ValidationError("an age at test has to be positive", field="age_days")

    @property
    def diameter(self) -> Quantity:
        """The average of the two measured diameters."""
        return (self.diameter_one + self.diameter_two.to(self.diameter_one.unit)) * 0.5

    @property
    def diameter_difference(self) -> Percent:
        """How far apart the two diameters are, as a share of the average."""
        spread = abs(self.diameter_one - self.diameter_two.to(self.diameter_one.unit))
        return Percent.from_fraction(spread.base_value / self.diameter.base_value)

    @property
    def is_out_of_round(self) -> bool:
        """True when the cylinder should not have been tested at all."""
        return self.diameter_difference > MAX_DIAMETER_DIFFERENCE

    @property
    def area(self) -> float:
        """Cross sectional area in square inches, from the measured diameter."""
        inches = self.diameter.to("in").value
        return math.pi * inches * inches / 4.0

    @property
    def length_diameter_ratio(self) -> float:
        """Length over average diameter, which decides whether to correct."""
        return self.length.base_value / self.diameter.base_value

    @property
    def needs_correction(self) -> bool:
        """True when the cylinder is short enough to read high."""
        return self.length_diameter_ratio < CORRECTION_THRESHOLD

    @property
    def correction(self) -> float:
        """The factor applied to the uncorrected strength."""
        return length_diameter_correction(self.length_diameter_ratio)

    @property
    def uncorrected_strength(self) -> Quantity:
        """Load over measured area, before any correction."""
        return Quantity(self.max_load.to("lbf").value / self.area, "psi")

    @property
    def strength(self) -> Quantity:
        """The strength as it goes on the report."""
        return self.uncorrected_strength * self.correction

    def describe(self) -> str:
        """One line for a break sheet."""
        flag = " out of round" if self.is_out_of_round else ""
        return (
            f"{self.specimen_code}  {self.age_days:g} d  {self.strength.format(0)}  "
            f"{self.fracture}{flag}"
        )
