"""What a mix design carries, per unit volume, and how that reads.

Three things about a concrete carbon number decide whether it is worth
anything, and none of them is the arithmetic.

The first is what got counted. A footprint that quietly skipped the admixtures
because nobody gave them a density is smaller than one that counted them, and
looks identical. So a footprint carries the list of what it could not count and
says so out loud rather than folding the omission into the total.

The second is per what. Concrete is bought by the cubic yard in one half of the
industry and the cubic metre in the other, and the benchmarks are published per
cubic metre. Getting that wrong is a factor of 1.3, which is larger than almost
any reduction a plant can actually achieve.

The third is against what. A total on its own says nothing. The useful figures
are the share the cement carries, which is where nearly all of it is, and the
carbon per unit of strength delivered, which is the only one that lets a rich
mix and a lean one be compared at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from slumpcone.carbon.factors import CarbonError, FactorBook, Stage
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import MixDesign
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

CUBIC_YARD = Quantity(1.0, "yd3")


@dataclass(frozen=True, slots=True)
class Contribution:
    """One ingredient's share of the total."""

    material_code: str
    material_class: MaterialClass
    mass: Quantity
    kg_co2e: float

    def share_of(self, total_kg: float) -> Percent:
        """This line as a share of a total. Zero over zero is zero, not an error."""
        if total_kg == 0.0:
            return Percent(0.0)
        return Percent.from_fraction(self.kg_co2e / total_kg)

    def describe(self) -> str:
        """One line."""
        return f"{self.material_code}: {self.mass.format(1)} carries {self.kg_co2e:.1f} kg"


@dataclass(frozen=True, slots=True)
class Footprint:
    """A mixture's cradle to gate emissions over a stated volume."""

    mix_code: str
    revision: int
    volume: Quantity
    stage: Stage
    contributions: tuple[Contribution, ...]
    uncounted: tuple[str, ...] = ()

    @property
    def total_kg(self) -> float:
        """Everything that was counted, in kilograms."""
        return sum(line.kg_co2e for line in self.contributions)

    @property
    def per_cubic_yard(self) -> float:
        """Kilograms per cubic yard."""
        return self.total_kg / self.volume.to("yd3").value

    @property
    def per_cubic_metre(self) -> float:
        """Kilograms per cubic metre, which is what the benchmarks are published in."""
        return self.total_kg / self.volume.to("m3").value

    @property
    def is_complete(self) -> bool:
        """Whether every ingredient in the design was counted."""
        return not self.uncounted

    def of_class(self, material_class: MaterialClass) -> float:
        """What one class of material carries."""
        return sum(
            line.kg_co2e for line in self.contributions if line.material_class is material_class
        )

    @property
    def cement_share(self) -> Percent:
        """How much of the total the portland cement is."""
        return Percent.from_fraction(
            0.0 if self.total_kg == 0.0 else self.of_class(MaterialClass.CEMENT) / self.total_kg
        )

    @property
    def binder_share(self) -> Percent:
        """Cement and supplementary materials together."""
        binder = self.of_class(MaterialClass.CEMENT) + self.of_class(MaterialClass.SCM)
        return Percent.from_fraction(0.0 if self.total_kg == 0.0 else binder / self.total_kg)

    def largest(self) -> Contribution | None:
        """The single heaviest line."""
        if not self.contributions:
            return None
        return max(self.contributions, key=lambda line: line.kg_co2e)

    def ranked(self) -> tuple[Contribution, ...]:
        """Every line, heaviest first."""
        return tuple(sorted(self.contributions, key=lambda line: line.kg_co2e, reverse=True))

    def intensity(self, specified_strength: Quantity) -> float:
        """Kilograms per cubic metre per megapascal of specified strength.

        This is the figure that lets a 3000 psi mix and a 6000 psi mix be
        compared. Without it the lean mix always wins, which tells you nothing
        you did not already know.
        """
        strength = specified_strength.to("MPa").value
        if strength <= 0.0:
            raise CarbonError(
                "CARBON_NO_STRENGTH", "an intensity needs a positive specified strength"
            )
        return self.per_cubic_metre / strength

    def describe(self) -> str:
        """One line."""
        tail = "" if self.is_complete else f", {len(self.uncounted)} ingredient(s) not counted"
        return (
            f"{self.mix_code} r{self.revision}: {self.per_cubic_yard:.1f} kg CO2e/yd3 "
            f"({self.per_cubic_metre:.1f} per m3){tail}"
        )


def footprint_of(
    design: MixDesign,
    book: FactorBook,
    *,
    volume: Quantity = CUBIC_YARD,
    admixture_density: Mapping[str, MassPerVolume] | None = None,
) -> Footprint:
    """Work out what one mixture carries over ``volume``.

    Admixtures are dosed by volume, so counting them needs a density as well as
    a factor. A plant that has not supplied one gets a footprint without them,
    named in ``uncounted``, rather than a smaller number with no explanation.
    """
    if volume.base_value <= 0.0:
        raise CarbonError("CARBON_NO_VOLUME", "a footprint needs a positive volume")
    stage = book.same_stage()
    densities = dict(admixture_density or {})
    lines: list[Contribution] = []
    uncounted: list[str] = []

    for material_code, mass in design.proportions.batch_weights(volume).items():
        if not book.has(material_code):
            uncounted.append(material_code)
            continue
        factor = book.get(material_code)
        lines.append(
            Contribution(material_code, factor.material_class, mass, factor.emissions(mass))
        )

    for material_code, dose in design.proportions.admixture_charges(volume).items():
        density = densities.get(material_code)
        if density is None or not book.has(material_code):
            uncounted.append(material_code)
            continue
        factor = book.get(material_code)
        mass = density.times(dose)
        lines.append(
            Contribution(material_code, MaterialClass.ADMIXTURE, mass, factor.emissions(mass))
        )

    return Footprint(
        design.code, design.revision, volume, stage, tuple(lines), tuple(uncounted)
    )


def compare(footprints: Sequence[Footprint]) -> tuple[Footprint, ...]:
    """Footprints ordered lightest first, per cubic metre.

    Comparing totals rather than intensities across different volumes is the
    mistake this ordering exists to make harder.
    """
    return tuple(sorted(footprints, key=lambda one: one.per_cubic_metre))


def reduction(baseline: Footprint, revised: Footprint) -> Percent:
    """How much lighter ``revised`` is than ``baseline``, per cubic metre.

    A positive number is a reduction. A negative one means the change made it
    worse, which happens often enough with a replacement that hurts strength.
    """
    before = baseline.per_cubic_metre
    if before <= 0.0:
        raise CarbonError(
            "CARBON_NO_BASELINE", "a reduction needs a baseline that carries something"
        )
    return Percent.from_fraction((before - revised.per_cubic_metre) / before)
