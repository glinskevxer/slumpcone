"""Absolute volume, and the yield check that falls out of it.

Concrete is proportioned by weight and sold by volume, and the bridge between
the two is absolute volume: the space a material's solid particles actually
occupy, which is its mass divided by its specific gravity and the density of
water. Add the air and the total has to come to exactly the unit volume the
design is written against.

A mix that does not close is not an academic problem. It is a mix that yields
short, and short yield means the last truck on a pour does not fill the forms.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# Density of water at 73 degF, the reference every specific gravity is against.
WATER_DENSITY = MassPerVolume(62.42796, "lb", "ft3")

# How far a mix design's absolute volumes may miss the unit volume before the
# proportions are wrong rather than rounded. Half a percent is a tenth of a
# cubic foot in a cubic yard, which is tighter than a plant can batch and
# looser than any real rounding error.
YIELD_TOLERANCE = 0.005


def absolute_volume(mass: Quantity, specific_gravity: float) -> Quantity:
    """The space ``mass`` of a material with that specific gravity occupies."""
    if mass.dimension.value != "mass":
        raise ValidationError("an absolute volume is taken of a mass", field="mass")
    if specific_gravity <= 0.0:
        raise ValidationError(
            "specific gravity has to be positive to take an absolute volume",
            field="specific_gravity",
        )
    density = WATER_DENSITY * specific_gravity
    return Quantity(mass.to("lb").value / density.to("lb", "ft3").value, "ft3")


@dataclass(frozen=True, slots=True)
class AbsoluteVolumes:
    """The absolute volume of every line in a batch, plus its air."""

    per_material: tuple[tuple[str, Quantity], ...]
    air: Quantity
    per_material_mass: tuple[tuple[str, Quantity], ...]

    @property
    def solids_volume(self) -> Quantity:
        """Everything except the air."""
        total = Quantity.zero("ft3")
        for _, volume in self.per_material:
            total = total + volume.to("ft3")
        return total

    @property
    def total_volume(self) -> Quantity:
        """Solids and air together, which is what the batch yields."""
        return self.solids_volume + self.air.to("ft3")

    @property
    def total_mass(self) -> Quantity:
        """Everything that went in, by weight."""
        total = Quantity.zero("lb")
        for _, mass in self.per_material_mass:
            total = total + mass.to("lb")
        return total

    @property
    def theoretical_density(self) -> MassPerVolume:
        """Density with no air in it at all, the C138 theoretical density."""
        if self.solids_volume.is_zero():
            raise ValidationError("a batch with no solid volume has no density", field="volume")
        return MassPerVolume.of(self.total_mass, self.solids_volume)

    @property
    def design_density(self) -> MassPerVolume:
        """Density with the design air included, what the truck should weigh."""
        if self.total_volume.is_zero():
            raise ValidationError("a batch with no volume has no density", field="volume")
        return MassPerVolume.of(self.total_mass, self.total_volume)

    def volume_of(self, material_code: str) -> Quantity:
        """The absolute volume one material contributes."""
        for code, volume in self.per_material:
            if code == material_code:
                return volume
        raise ValidationError(f"{material_code} is not in this batch", field="material_code")

    def share_of(self, material_code: str) -> Percent:
        """The share of the total volume one material occupies."""
        return Percent.from_fraction(
            self.volume_of(material_code).base_value / self.total_volume.base_value
        )


def compute_volumes(
    proportions: Proportions,
    specific_gravities: Mapping[str, float],
    volume: Quantity | None = None,
) -> AbsoluteVolumes:
    """The absolute volume breakdown of ``proportions`` over ``volume``.

    Water takes a specific gravity of one unless the caller says otherwise,
    which is the only default here. Everything else has to be supplied, because
    guessing an aggregate's specific gravity is how a yield check comes out
    right against numbers that are wrong.
    """
    nominal = Quantity(1.0, proportions.volume_unit) if volume is None else volume
    masses = proportions.batch_weights(nominal)
    volumes: list[tuple[str, Quantity]] = []
    weights: list[tuple[str, Quantity]] = []
    for charge in proportions.charges:
        mass = masses[charge.material_code]
        gravity = specific_gravities.get(charge.material_code)
        if gravity is None:
            if charge.material_class is MaterialClass.WATER:
                gravity = 1.0
            else:
                raise ValidationError(
                    f"no specific gravity for {charge.material_code}",
                    field="specific_gravities",
                )
        volumes.append((charge.material_code, absolute_volume(mass, gravity)))
        weights.append((charge.material_code, mass))
    solids = Quantity.zero("ft3")
    for _, entry in volumes:
        solids = solids + entry
    air = Quantity(
        proportions.design_air.of(nominal.to("ft3").value),
        "ft3",
    )
    return AbsoluteVolumes(tuple(volumes), air, tuple(weights))


@dataclass(frozen=True, slots=True)
class YieldCheck:
    """What a set of proportions actually yields against what it claims to."""

    nominal: Quantity
    computed: Quantity
    tolerance: float = YIELD_TOLERANCE

    @property
    def error(self) -> Quantity:
        """Computed less nominal, positive when the mix over yields."""
        return self.computed - self.nominal.to(self.computed.unit)

    @property
    def relative(self) -> float:
        """Computed divided by nominal."""
        return self.computed.base_value / self.nominal.base_value

    @property
    def conforms(self) -> bool:
        """True when the proportions close on the volume they claim."""
        return abs(self.relative - 1.0) <= self.tolerance + 1e-12

    def describe(self) -> str:
        """One line saying whether the design closes and by how much."""
        verdict = "closes" if self.conforms else "does not close"
        return (
            f"{verdict}: {self.computed.format(3)} against a nominal "
            f"{self.nominal.to(self.computed.unit).format(3)} "
            f"({(self.relative - 1.0) * 100.0:+.2f}%)"
        )


def check_yield(
    proportions: Proportions,
    specific_gravities: Mapping[str, float],
    *,
    tolerance: float = YIELD_TOLERANCE,
) -> YieldCheck:
    """Does one unit volume of these proportions actually come to one unit?"""
    nominal = Quantity(1.0, proportions.volume_unit)
    breakdown = compute_volumes(proportions, specific_gravities, nominal)
    return YieldCheck(nominal, breakdown.total_volume.to(proportions.volume_unit), tolerance)


def relative_yield(measured_density: MassPerVolume, breakdown: AbsoluteVolumes) -> float:
    """Volume actually produced divided by the volume ordered, from C138."""
    if measured_density.is_zero():
        raise ValidationError(
            "a measured density of zero has no yield", field="measured_density"
        )
    produced = breakdown.total_mass.base_value / measured_density.base_value
    return produced / breakdown.total_volume.base_value


def gravimetric_air(measured_density: MassPerVolume, breakdown: AbsoluteVolumes) -> Percent:
    """Air content by the gravimetric method: how far the load fell short.

    This is the check on the pressure meter rather than a replacement for it.
    When the two disagree by more than about a percent, one of the specific
    gravities on file is wrong, and it is usually the sand.
    """
    theoretical = breakdown.theoretical_density
    return Percent.from_fraction(
        (theoretical.base_value - measured_density.base_value) / theoretical.base_value
    )
