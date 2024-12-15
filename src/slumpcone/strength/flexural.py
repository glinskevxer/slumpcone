"""Flexural strength, and the branch that depends on where the beam broke.

Paving is bought on flexural strength rather than compressive, because a slab
on grade fails in bending. A beam is loaded at the third points and the modulus
of rupture is read off the load at failure, but which formula applies depends
on where the crack came out.

Inside the middle third, the beam broke where the bending moment is uniform and
the simple formula holds. Outside it by a small margin, the moment at the crack
is lower than the maximum and a correction is applied. Outside it by more than
five percent of the span, the result is thrown away: the beam broke at a flaw,
not at the load.

That third branch is the one people skip, and skipping it lets a beam that
broke early at a stone pocket into an average it has no business being in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# How far outside the middle third a fracture may fall and still be corrected
# rather than discarded, as a share of the span.
CORRECTION_LIMIT = Percent(5.0)

# ACI's estimate of modulus of rupture from compressive strength, in the form
# fr = factor * sqrt(f'c) with both in psi.
DEFAULT_RUPTURE_FACTOR = 7.5


class FractureLocation(Enum):
    """Where the beam cracked, relative to the middle third."""

    MIDDLE_THIRD = "middle third"
    JUST_OUTSIDE = "just outside"
    WELL_OUTSIDE = "well outside"

    def __str__(self) -> str:
        return self.value

    @property
    def is_usable(self) -> bool:
        """True when a result from this break counts."""
        return self is not FractureLocation.WELL_OUTSIDE

    @property
    def needs_correction(self) -> bool:
        """True when the simple formula overstates the strength."""
        return self is FractureLocation.JUST_OUTSIDE


def locate_fracture(span: Quantity, distance_from_support: Quantity) -> FractureLocation:
    """Which branch a fracture falls in, from where it came out.

    ``distance_from_support`` is measured to the nearer support, which is how a
    technician measures it and what the correction formula wants.
    """
    for name, value in (("span", span), ("distance", distance_from_support)):
        if value.dimension.value != "length":
            raise ValidationError(f"a {name} is a length", field=name)
    if span.value <= 0.0:
        raise ValidationError("a span has to be positive", field="span")
    if distance_from_support.value < 0.0:
        raise ValidationError("a distance cannot be negative", field="distance")
    share = distance_from_support.base_value / span.base_value
    if share > 0.5:
        share = 1.0 - share
    if share >= (1.0 / 3.0) - 1e-9:
        return FractureLocation.MIDDLE_THIRD
    if share >= (1.0 / 3.0) - CORRECTION_LIMIT.fraction - 1e-9:
        return FractureLocation.JUST_OUTSIDE
    return FractureLocation.WELL_OUTSIDE


@dataclass(frozen=True, slots=True)
class FlexuralBreak:
    """One beam taken to failure at the third points."""

    specimen_code: str
    span: Quantity
    width: Quantity
    depth: Quantity
    max_load: Quantity
    fracture_from_support: Quantity
    age_days: float = 28.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "specimen_code", normalize_code(self.specimen_code, field="specimen_code")
        )
        for name, value in (
            ("span", self.span),
            ("width", self.width),
            ("depth", self.depth),
        ):
            if value.dimension.value != "length":
                raise ValidationError(f"a beam {name} is a length", field=name)
            if value.value <= 0.0:
                raise ValidationError(f"a beam {name} has to be positive", field=name)
        if self.max_load.dimension.value != "force":
            raise ValidationError("a machine load is a force", field="max_load")
        if self.max_load.value <= 0.0:
            raise ValidationError("a machine load has to be positive", field="max_load")
        if self.age_days <= 0.0:
            raise ValidationError("an age at test has to be positive", field="age_days")

    @property
    def location(self) -> FractureLocation:
        """Where the beam cracked."""
        return locate_fracture(self.span, self.fracture_from_support)

    @property
    def is_usable(self) -> bool:
        """True when this beam produces a result at all."""
        return self.location.is_usable

    @property
    def modulus_of_rupture(self) -> Quantity:
        """The flexural strength, with the correction where it applies.

        Inside the middle third the moment arm is a third of the span. Outside
        it, the arm is the measured distance to the nearer support, which is
        shorter, so the same load gives a lower strength.
        """
        if not self.is_usable:
            raise ValidationError(
                f"{self.specimen_code} broke well outside the middle third and does "
                "not give a result",
                field="fracture_from_support",
            )
        load = self.max_load.to("lbf").value
        width = self.width.to("in").value
        depth = self.depth.to("in").value
        if self.location is FractureLocation.MIDDLE_THIRD:
            arm = self.span.to("in").value / 3.0
        else:
            arm = self.fracture_from_support.to("in").value
            if arm > self.span.to("in").value / 2.0:
                arm = self.span.to("in").value - arm
        return Quantity(3.0 * load * arm / (width * depth * depth), "psi")

    def describe(self) -> str:
        """One line for a beam sheet."""
        if not self.is_usable:
            return f"{self.specimen_code}  discarded, broke {self.location}"
        return (
            f"{self.specimen_code}  {self.age_days:g} d  "
            f"{self.modulus_of_rupture.format(0)}  {self.location}"
        )


def estimated_rupture(
    compressive: Quantity, factor: float = DEFAULT_RUPTURE_FACTOR
) -> Quantity:
    """Modulus of rupture estimated from compressive strength.

    The relation is a rule of thumb and the factor is the argument people have
    about: seven and a half is ACI's, paving agencies use anything from seven
    to nine, and a mixture with a crushed aggregate sits at the top of that
    range. It is an estimate for proportioning, never a substitute for a beam.
    """
    if compressive.dimension.value != "pressure":
        raise ValidationError("a compressive strength is a pressure", field="compressive")
    if compressive.value <= 0.0:
        raise ValidationError("a compressive strength has to be positive", field="compressive")
    if factor <= 0.0:
        raise ValidationError("a rupture factor has to be positive", field="factor")
    return Quantity(factor * math.sqrt(compressive.to("psi").value), "psi")


def equivalent_compressive(
    rupture: Quantity, factor: float = DEFAULT_RUPTURE_FACTOR
) -> Quantity:
    """The compressive strength a modulus of rupture implies, by the same rule."""
    if rupture.dimension.value != "pressure":
        raise ValidationError("a modulus of rupture is a pressure", field="rupture")
    if rupture.value <= 0.0:
        raise ValidationError("a modulus of rupture has to be positive", field="rupture")
    if factor <= 0.0:
        raise ValidationError("a rupture factor has to be positive", field="factor")
    return Quantity((rupture.to("psi").value / factor) ** 2, "psi")


def average_rupture(breaks: list[FlexuralBreak]) -> Quantity:
    """The flexural test result, over the beams that count."""
    usable = [beam for beam in breaks if beam.is_usable]
    if not usable:
        raise ValidationError("every beam broke well outside the middle third", field="breaks")
    running = Quantity.zero("psi")
    for beam in usable:
        running = running + beam.modulus_of_rupture
    return running * (1.0 / len(usable))
