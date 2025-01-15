"""How close a batcher has to get, which is not one number.

C94 does not give a flat percentage. The tolerance on a cementitious or
aggregate charge depends on how big the charge is relative to the scale it is
weighed on, and it switches rule at thirty percent of scale capacity.

Above that line the tolerance is a straight percentage of what was asked for.
Below it, it is the *lesser* of a percentage of capacity and a wider percentage
of the charge, which is the part people get backwards: a small charge on a big
scale gets a tighter allowance than the plain percentage, not a looser one, and
plants that assume otherwise batch out of tolerance for years without knowing.

Water and admixtures are simpler because they are metered rather than weighed
against a hopper's full range.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.materials.kinds import MaterialClass
from slumpcone.percent import Percent
from slumpcone.tolerance import Band, Side
from slumpcone.units.checks import require_mass, require_not_negative, require_positive
from slumpcone.units.quantity import Quantity

# The charge size, as a share of scale capacity, where the rule changes.
SMALL_CHARGE_THRESHOLD = Percent(30.0)

TOLERANCE_CEMENTITIOUS = Percent(1.0)
TOLERANCE_AGGREGATE = Percent(2.0)
TOLERANCE_WATER = Percent(1.0)
TOLERANCE_ADMIXTURE = Percent(3.0)
TOLERANCE_SMALL_CHARGE = Percent(3.0)
TOLERANCE_OF_CAPACITY = Percent(0.3)


def _large_charge_allowance(material_class: MaterialClass) -> Percent:
    if material_class.is_cementitious:
        return TOLERANCE_CEMENTITIOUS
    if material_class.is_aggregate:
        return TOLERANCE_AGGREGATE
    if material_class is MaterialClass.WATER:
        return TOLERANCE_WATER
    if material_class is MaterialClass.ADMIXTURE:
        return TOLERANCE_ADMIXTURE
    return TOLERANCE_AGGREGATE


def weighing_allowance(
    material_class: MaterialClass,
    required: Quantity,
    scale_capacity: Quantity | None = None,
) -> Quantity:
    """How far off ``required`` a batch of this class is allowed to land.

    With no scale named the plain percentage applies, which is what a metered
    water or admixture charge gets anyway.
    """
    require_mass(required, "a required weight", field="required")
    require_not_negative(required, "a required weight", field="required")
    plain = abs(required) * _large_charge_allowance(material_class).fraction
    weighed = material_class.is_cementitious or material_class.is_aggregate
    if scale_capacity is None or not weighed:
        return plain
    require_mass(scale_capacity, "a scale capacity", field="scale_capacity")
    require_positive(scale_capacity, "a scale capacity", field="scale_capacity")
    share = Percent.from_fraction(required.base_value / scale_capacity.base_value)
    if share >= SMALL_CHARGE_THRESHOLD:
        return plain
    of_capacity = scale_capacity.to(required.unit) * TOLERANCE_OF_CAPACITY.fraction
    of_charge = abs(required) * TOLERANCE_SMALL_CHARGE.fraction
    return min(of_capacity, of_charge, key=lambda q: q.base_value)


def weighing_band(
    material_class: MaterialClass,
    required: Quantity,
    scale_capacity: Quantity | None = None,
) -> Band:
    """The band an actual weight has to land inside."""
    allowance = weighing_allowance(material_class, required, scale_capacity)
    return Band.symmetric(required.value, allowance.to(required.unit).value)


@dataclass(frozen=True, slots=True)
class WeighingResult:
    """One material's required weight against what the scale actually recorded."""

    material_code: str
    material_class: MaterialClass
    required: Quantity
    actual: Quantity
    allowance: Quantity

    @property
    def error(self) -> Quantity:
        """Actual less required."""
        return self.actual - self.required.to(self.actual.unit)

    @property
    def error_percent(self) -> Percent:
        """The error as a share of what was asked for."""
        if self.required.is_zero():
            return Percent(0.0)
        return Percent.from_fraction(self.error.base_value / self.required.base_value)

    @property
    def side(self) -> Side:
        """Which side of the band the charge landed on."""
        band = Band.symmetric(
            self.required.to(self.actual.unit).value,
            self.allowance.to(self.actual.unit).value,
        )
        return band.side(self.actual.value)

    @property
    def conforms(self) -> bool:
        """True when the charge is inside its tolerance."""
        return self.side is Side.IN

    def describe(self) -> str:
        """One line for a ticket audit."""
        verdict = "ok" if self.conforms else f"out {self.side}"
        return (
            f"{self.material_code}  required {self.required.format(0)}  "
            f"actual {self.actual.format(0)}  "
            f"error {self.error.format(0)} ({self.error_percent.format(2)})  "
            f"allowance {self.allowance.format(1)}  {verdict}"
        )


def check_weighing(
    material_code: str,
    material_class: MaterialClass,
    required: Quantity,
    actual: Quantity,
    scale_capacity: Quantity | None = None,
) -> WeighingResult:
    """Judge one weighed charge against the tolerance its class earns."""
    allowance = weighing_allowance(material_class, required, scale_capacity)
    return WeighingResult(material_code, material_class, required, actual, allowance)
