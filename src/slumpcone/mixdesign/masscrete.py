"""Heat in a thick section, and the two limits it runs into.

Cement hydrating gives off heat. In a slab it escapes; in a five foot footing
it does not, and the middle of the pour reaches a temperature the outside never
sees. Two things go wrong from there. Above about a hundred and sixty degrees
the concrete forms a mineral that expands years later and cracks the section
from inside. And while the middle is hot and the outside is not, the difference
in expansion cracks it straight away.

The rise is estimated from the binder, and the estimate is where the
substitution pays for itself: slag and fly ash give off much less heat than
portland cement for the same strength, which is why a mass pour is nearly
always a heavy replacement mixture.

Both limits are on the concrete, not on the mixture, so a mixture that fails
one of them can still be used if the placement is cooled, pre-chilled or poured
in lifts. The check says which limit binds, not what to do about it.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import MaterialClass, ScmKind
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.units.checks import require_length
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature, TemperatureDelta

# Degrees Fahrenheit of adiabatic rise per hundred pounds of portland cement.
RISE_PER_CWT = 5.5

# How much heat each supplementary material gives off against portland cement.
_HEAT_SHARE: dict[ScmKind, float] = {
    ScmKind.FLY_ASH_F: 0.50,
    ScmKind.FLY_ASH_C: 0.65,
    ScmKind.SLAG_100: 0.75,
    ScmKind.SLAG_120: 0.75,
    ScmKind.SILICA_FUME: 1.20,
    ScmKind.METAKAOLIN: 1.10,
    ScmKind.NATURAL_POZZOLAN: 0.60,
}

MAX_PEAK = Temperature(160.0, "F")
MAX_DIFFERENTIAL = TemperatureDelta(35.0, "F")

# Below this least dimension the section is not mass concrete and none of this
# applies. Three feet is where most specifications draw it.
MASS_THRESHOLD = Quantity(36.0, "in")


def heat_share(kind: ScmKind) -> float:
    """How much heat a supplementary material gives off, against cement."""
    return _HEAT_SHARE[kind]


def is_mass_concrete(least_dimension: Quantity) -> bool:
    """True when a section is thick enough for any of this to matter."""
    require_length(least_dimension, "a section dimension", field="least_dimension")
    return least_dimension >= MASS_THRESHOLD


@dataclass(frozen=True, slots=True)
class HeatEstimate:
    """The rise a mixture is expected to produce."""

    cement_equivalent: Quantity
    rise: TemperatureDelta

    def peak_from(self, placement: Temperature, retained: float = 1.0) -> Temperature:
        """The peak the middle reaches from a placement temperature.

        ``retained`` is the share of the adiabatic rise the section actually
        keeps: a genuinely massive block keeps nearly all of it, a three foot
        wall rather less.
        """
        if not 0.0 <= retained <= 1.0:
            raise ValidationError(
                "the retained share is between nothing and all of it", field="retained"
            )
        return placement + self.rise * retained

    def describe(self) -> str:
        """One line for a thermal report."""
        return (
            f"{self.cement_equivalent.format(0)} of cement equivalent gives "
            f"{self.rise} of adiabatic rise"
        )


def estimate_heat(proportions: Proportions, catalog: MaterialCatalog) -> HeatEstimate:
    """The adiabatic rise a mixture is expected to produce.

    Every supplementary material is converted to the portland cement that would
    give off the same heat, and the rise comes off that one number. Silica fume
    converts to more than its own weight, which surprises people: it is a very
    reactive material and a mass mixture does not want much of it.
    """
    one_unit = Quantity(1.0, proportions.volume_unit)
    weights = proportions.batch_weights(one_unit)
    equivalent = Quantity.zero("lb")
    for charge in proportions.charges:
        if not charge.material_class.is_cementitious:
            continue
        weight = weights[charge.material_code].to("lb")
        if charge.material_class is MaterialClass.CEMENT:
            equivalent = equivalent + weight
            continue
        # A material filed as an SCM always carries a kind: the catalogue
        # refuses one without. So there is no branch here for a missing kind.
        kind = catalog.get(charge.material_code).scm_kind
        assert kind is not None
        equivalent = equivalent + weight * heat_share(kind)
    rise = TemperatureDelta(equivalent.value / 100.0 * RISE_PER_CWT, "F")
    return HeatEstimate(equivalent, rise)


@dataclass(frozen=True, slots=True)
class ThermalCheck:
    """One placement judged against both thermal limits."""

    peak: Temperature
    surface: Temperature
    max_peak: Temperature = MAX_PEAK
    max_differential: TemperatureDelta = MAX_DIFFERENTIAL

    @property
    def differential(self) -> TemperatureDelta:
        """How far the middle is above the surface."""
        difference = self.peak - self.surface
        assert isinstance(difference, TemperatureDelta)
        return difference

    @property
    def peak_is_too_high(self) -> bool:
        """True when the middle goes past the ceiling."""
        return self.peak > self.max_peak

    @property
    def differential_is_too_high(self) -> bool:
        """True when the middle and the surface are too far apart."""
        return self.differential > self.max_differential

    @property
    def conforms(self) -> bool:
        """True when neither limit is passed."""
        return not (self.peak_is_too_high or self.differential_is_too_high)

    @property
    def binding_limit(self) -> str:
        """Which limit is the one to work on."""
        if self.peak_is_too_high and self.differential_is_too_high:
            return "both"
        if self.peak_is_too_high:
            return "peak temperature"
        if self.differential_is_too_high:
            return "differential"
        return "none"

    def describe(self) -> str:
        """One line for a thermal report."""
        return (
            f"peak {self.peak}, surface {self.surface}, differential "
            f"{self.differential}; limit binding: {self.binding_limit}"
        )


def check_thermal(
    proportions: Proportions,
    catalog: MaterialCatalog,
    placement: Temperature,
    surface: Temperature,
    *,
    retained: float = 1.0,
) -> ThermalCheck:
    """Judge a mixture and a placement against both thermal limits."""
    estimate = estimate_heat(proportions, catalog)
    return ThermalCheck(estimate.peak_from(placement, retained), surface)
