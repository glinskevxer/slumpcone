"""Proportions: how much of each material goes into a unit volume.

Solids and water are quoted as a mass per unit volume of concrete. Admixtures
are not, because nobody doses an admixture by the yard. They are dosed against
the cementitious content, in fluid ounces per hundred pounds of it, so a mix
that changes its cement content changes its admixture charge without anybody
editing the admixture line.

That dependency is the reason admixture charges are a different type here. A
dose written as a flat quantity per yard silently stops tracking the binder the
first time the binder moves.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.materials.kinds import MaterialClass
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# A hundredweight, the basis admixture dosage is quoted against.
CWT = Quantity(100.0, "lb")


@dataclass(frozen=True, slots=True)
class Charge:
    """One solid or water line of a mix design, as a mass per unit volume."""

    material_code: str
    material_class: MaterialClass
    content: MassPerVolume

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        if self.material_class is MaterialClass.ADMIXTURE:
            raise ValidationError(
                "an admixture is dosed against the binder, not by the yard",
                field="material_class",
            )
        if self.content.value < 0.0:
            raise ValidationError("a charge cannot be negative", field="content")

    def for_volume(self, volume: Quantity) -> Quantity:
        """The mass this charge puts into ``volume``."""
        return self.content.times(volume)

    def __str__(self) -> str:
        return f"{self.material_code} {self.content}"


@dataclass(frozen=True, slots=True)
class AdmixtureCharge:
    """One admixture line, dosed per hundredweight of cementitious."""

    material_code: str
    dose_per_cwt: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        if self.dose_per_cwt.dimension.value != "volume":
            raise ValidationError("an admixture dose is a volume", field="dose_per_cwt")
        if self.dose_per_cwt.value < 0.0:
            raise ValidationError("an admixture dose cannot be negative", field="dose_per_cwt")

    def for_cementitious(self, cementitious: Quantity) -> Quantity:
        """The charge this dose calls for against a mass of cementitious."""
        if cementitious.dimension.value != "mass":
            raise ValidationError("cementitious content is a mass", field="cementitious")
        hundredweights = cementitious.to("lb").value / CWT.value
        return self.dose_per_cwt * hundredweights

    def __str__(self) -> str:
        return f"{self.material_code} {self.dose_per_cwt.format(1)}/cwt"


@dataclass(frozen=True, slots=True)
class Proportions:
    """Every line of a mix design, per unit volume."""

    charges: tuple[Charge, ...]
    admixtures: tuple[AdmixtureCharge, ...] = ()
    design_air: Percent = Percent(0.0)

    def __post_init__(self) -> None:
        if not self.charges:
            raise ValidationError("a mix design needs at least one charge", field="charges")
        seen: set[str] = set()
        for charge in self.charges:
            if charge.material_code in seen:
                raise ValidationError(
                    f"{charge.material_code} appears twice in the proportions", field="charges"
                )
            seen.add(charge.material_code)
        volume_unit = self.charges[0].content.volume_unit
        for charge in self.charges:
            if charge.content.volume_unit != volume_unit:
                raise ValidationError(
                    "every charge is quoted against the same volume", field="charges"
                )
        admix_seen: set[str] = set()
        for admixture in self.admixtures:
            if admixture.material_code in admix_seen:
                raise ValidationError(
                    f"{admixture.material_code} appears twice in the admixtures",
                    field="admixtures",
                )
            admix_seen.add(admixture.material_code)
        if not 0.0 <= self.design_air.value < 30.0:
            raise ValidationError(
                f"design air of {self.design_air} is not a concrete", field="design_air"
            )
        if not self.of_class(MaterialClass.WATER):
            raise ValidationError("a mix design needs a water line", field="charges")
        if not self.cementitious_charges:
            raise ValidationError("a mix design needs cementitious material", field="charges")

    @property
    def volume_unit(self) -> str:
        """The volume every charge is quoted against."""
        return self.charges[0].content.volume_unit

    @property
    def mass_unit(self) -> str:
        """The mass unit the charges are quoted in."""
        return self.charges[0].content.mass_unit

    def of_class(self, material_class: MaterialClass) -> tuple[Charge, ...]:
        """Every charge of one class, in the order they were written."""
        return tuple(c for c in self.charges if c.material_class is material_class)

    def charge(self, material_code: str) -> Charge:
        """One charge by material code."""
        key = normalize_code(material_code, field="material_code")
        for candidate in self.charges:
            if candidate.material_code == key:
                return candidate
        raise ValidationError(f"{key} is not in these proportions", field="material_code")

    def _total(self, charges: tuple[Charge, ...]) -> MassPerVolume:
        total = MassPerVolume(0.0, self.mass_unit, self.volume_unit)
        for charge in charges:
            total = total + charge.content
        return total

    @property
    def cementitious_charges(self) -> tuple[Charge, ...]:
        """Cement and SCM lines together."""
        return tuple(c for c in self.charges if c.material_class.is_cementitious)

    @property
    def cementitious(self) -> MassPerVolume:
        """Total cementitious content."""
        return self._total(self.cementitious_charges)

    @property
    def cement(self) -> MassPerVolume:
        """Portland cement content alone."""
        return self._total(self.of_class(MaterialClass.CEMENT))

    @property
    def supplementary(self) -> MassPerVolume:
        """Supplementary cementitious content alone."""
        return self._total(self.of_class(MaterialClass.SCM))

    @property
    def water(self) -> MassPerVolume:
        """Design water content."""
        return self._total(self.of_class(MaterialClass.WATER))

    @property
    def coarse_aggregate(self) -> MassPerVolume:
        """Coarse aggregate content."""
        return self._total(self.of_class(MaterialClass.COARSE_AGGREGATE))

    @property
    def fine_aggregate(self) -> MassPerVolume:
        """Fine aggregate content."""
        return self._total(self.of_class(MaterialClass.FINE_AGGREGATE))

    @property
    def total_aggregate(self) -> MassPerVolume:
        """Both aggregates together."""
        return self.coarse_aggregate + self.fine_aggregate

    @property
    def water_cementitious_ratio(self) -> float:
        """The design water divided by the design cementitious."""
        if self.cementitious.is_zero():
            raise ValidationError(
                "a mix with no cementitious material has no ratio", field="cementitious"
            )
        return self.water.ratio_to(self.cementitious)

    @property
    def supplementary_replacement(self) -> Percent:
        """The share of the binder that is not portland cement."""
        if self.cementitious.is_zero():
            return Percent(0.0)
        return Percent.from_fraction(self.supplementary.ratio_to(self.cementitious))

    @property
    def fine_aggregate_fraction(self) -> Percent:
        """The share of the total aggregate that is sand, by weight."""
        if self.total_aggregate.is_zero():
            return Percent(0.0)
        return Percent.from_fraction(self.fine_aggregate.ratio_to(self.total_aggregate))

    def batch_weights(self, volume: Quantity) -> dict[str, Quantity]:
        """Every solid and water charge scaled to ``volume``."""
        return {c.material_code: c.for_volume(volume) for c in self.charges}

    def admixture_charges(self, volume: Quantity) -> dict[str, Quantity]:
        """Every admixture dose scaled to the cementitious in ``volume``."""
        cementitious = self.cementitious.times(volume)
        return {a.material_code: a.for_cementitious(cementitious) for a in self.admixtures}

    def scaled_to(self, mass_unit: str, volume_unit: str) -> Proportions:
        """The same proportions restated in another unit pair."""
        return Proportions(
            tuple(
                Charge(c.material_code, c.material_class, c.content.to(mass_unit, volume_unit))
                for c in self.charges
            ),
            self.admixtures,
            self.design_air,
        )
