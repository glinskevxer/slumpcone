"""Cores, which are what happens after a strength test comes out low.

A low test does not condemn the concrete. It starts an investigation, and if
the investigation reaches the structure, three cores are taken from the area in
question. The acceptance is deliberately looser than for cylinders, because a
core is damaged by being cut and is being asked a different question: not "was
the concrete made right" but "is the structure adequate".

Two thresholds and both have to hold. The average of the three has to reach
eighty five percent of the specified strength, and no single core may fall
below seventy five percent. A set that averages ninety with one core at seventy
fails, which is the point: the low one says there is a bad patch, and an
average cannot see a patch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.strength.breaks import length_diameter_correction
from slumpcone.units.quantity import Quantity

CORES_PER_INVESTIGATION = 3
AVERAGE_THRESHOLD = Percent(85.0)
INDIVIDUAL_THRESHOLD = Percent(75.0)

# A core shorter than this many diameters cannot be corrected into a strength.
MIN_LENGTH_DIAMETER = 1.0


class CoreCondition(Enum):
    """How the core was conditioned before it was tested."""

    AS_RECEIVED = "as received"
    SOAKED = "soaked"
    AIR_DRIED = "air dried"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> CoreCondition:
        """Read a conditioning off a core report."""
        key = text.strip().lower().replace("_", " ")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown core condition {text!r}", field="condition")

    @property
    def matches_service(self) -> bool:
        """True when the conditioning reflects how the structure will be used.

        A soaked core reads lower than a dry one by around ten percent, so the
        conditioning has to match the service condition or the comparison is
        against the wrong number. As received matches neither and is only
        defensible when the structure is genuinely at that moisture.
        """
        return self is not CoreCondition.AS_RECEIVED


@dataclass(frozen=True, slots=True)
class Core:
    """One core, drilled and broken."""

    code: str
    diameter: Quantity
    length: Quantity
    max_load: Quantity
    condition: CoreCondition = CoreCondition.SOAKED
    has_reinforcement: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="core_code"))
        for name, value in (("diameter", self.diameter), ("length", self.length)):
            if value.dimension.value != "length":
                raise ValidationError(f"a core {name} is a length", field=name)
            if value.value <= 0.0:
                raise ValidationError(f"a core {name} has to be positive", field=name)
        if self.max_load.dimension.value != "force":
            raise ValidationError("a machine load is a force", field="max_load")
        if self.max_load.value <= 0.0:
            raise ValidationError("a machine load has to be positive", field="max_load")

    @property
    def length_diameter_ratio(self) -> float:
        """Length over diameter, which decides the correction."""
        return self.length.base_value / self.diameter.base_value

    @property
    def is_testable(self) -> bool:
        """True when the core is long enough to give a strength at all."""
        return self.length_diameter_ratio >= MIN_LENGTH_DIAMETER - 1e-9

    @property
    def area(self) -> float:
        """Cross sectional area in square inches."""
        import math

        inches = self.diameter.to("in").value
        return math.pi * inches * inches / 4.0

    @property
    def strength(self) -> Quantity:
        """The corrected core strength."""
        if not self.is_testable:
            raise ValidationError(
                f"{self.code} is {self.length_diameter_ratio:.2f} diameters long and "
                "cannot be corrected into a strength",
                field="length",
            )
        uncorrected = self.max_load.to("lbf").value / self.area
        return Quantity(
            uncorrected * length_diameter_correction(self.length_diameter_ratio), "psi"
        )

    def describe(self) -> str:
        """One line for a core report."""
        flag = ", contains reinforcement" if self.has_reinforcement else ""
        if not self.is_testable:
            return f"{self.code}  too short to test{flag}"
        return (
            f"{self.code}  L/D {self.length_diameter_ratio:.2f}  "
            f"{self.strength.format(0)}  {self.condition}{flag}"
        )


@dataclass(frozen=True, slots=True)
class CoreInvestigation:
    """A set of cores taken to answer one low strength test."""

    location: str
    specified: Quantity
    cores: tuple[Core, ...]

    def __post_init__(self) -> None:
        if self.specified.dimension.value != "pressure":
            raise ValidationError("a specified strength is a pressure", field="specified")
        if self.specified.value <= 0.0:
            raise ValidationError("a specified strength has to be positive", field="specified")
        if not self.cores:
            raise ValidationError("an investigation needs at least one core", field="cores")

    @property
    def testable(self) -> tuple[Core, ...]:
        """The cores that gave a result."""
        return tuple(core for core in self.cores if core.is_testable)

    @property
    def average(self) -> Quantity:
        """The average of the cores that gave a result."""
        usable = self.testable
        if not usable:
            raise ValidationError("no core in this set gave a result", field="cores")
        running = Quantity.zero("psi")
        for core in usable:
            running = running + core.strength
        return running * (1.0 / len(usable))

    @property
    def lowest(self) -> Quantity:
        """The weakest core that gave a result."""
        usable = self.testable
        if not usable:
            raise ValidationError("no core in this set gave a result", field="cores")
        return min((core.strength for core in usable), key=lambda value: value.base_value)

    @property
    def average_threshold(self) -> Quantity:
        """Eighty five percent of the specified strength."""
        return self.specified * AVERAGE_THRESHOLD.fraction

    @property
    def individual_threshold(self) -> Quantity:
        """Seventy five percent of the specified strength."""
        return self.specified * INDIVIDUAL_THRESHOLD.fraction

    @property
    def has_enough_cores(self) -> bool:
        """True when three cores gave a result."""
        return len(self.testable) >= CORES_PER_INVESTIGATION

    @property
    def is_adequate(self) -> bool:
        """True when the structure passes both thresholds."""
        if not self.has_enough_cores:
            return False
        return (
            self.average >= self.average_threshold and self.lowest >= self.individual_threshold
        )

    def findings(self) -> tuple[str, ...]:
        """Why the structure is not adequate, if it is not."""
        found: list[str] = []
        if not self.has_enough_cores:
            found.append(
                f"{len(self.testable)} of {CORES_PER_INVESTIGATION} cores gave a result"
            )
        if not self.testable:
            return tuple(found)
        if self.average < self.average_threshold:
            found.append(
                f"the average is {self.average.format(0)} and "
                f"{AVERAGE_THRESHOLD.format(0)} of specified is "
                f"{self.average_threshold.format(0)}"
            )
        if self.lowest < self.individual_threshold:
            found.append(
                f"the lowest core is {self.lowest.format(0)} and "
                f"{INDIVIDUAL_THRESHOLD.format(0)} of specified is "
                f"{self.individual_threshold.format(0)}"
            )
        for core in self.cores:
            if core.has_reinforcement:
                found.append(f"{core.code} contains reinforcement")
            if not core.condition.matches_service:
                found.append(f"{core.code} was tested {core.condition}")
        return tuple(found)

    def describe(self) -> str:
        """A short investigation report."""
        lines = [
            f"{self.location} against {self.specified.format(0)}: "
            f"{'adequate' if self.is_adequate else 'not adequate'}"
        ]
        lines.extend(f"  {core.describe()}" for core in self.cores)
        lines.extend(f"  {finding}" for finding in self.findings())
        return "\n".join(lines)


def investigate(location: str, specified: Quantity, cores: Sequence[Core]) -> CoreInvestigation:
    """Judge a set of cores against a specified strength."""
    return CoreInvestigation(location.strip(), specified, tuple(cores))
