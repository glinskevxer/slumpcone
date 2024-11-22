"""Water soluble chloride, added up across the mixture.

This lives beside the mix design rather than beside the exposure classes it is
judged against, because the calculation needs the proportions and the exposure
classes do not know about those. Putting it in ``spec`` made the two packages
import each other.

The limit is written as a percentage by mass of *cementitious* material, but
the chloride does not all come from the cement. Aggregate dredged near the
coast carries it, some admixtures carry it deliberately, and reclaimed water
concentrates it. So the numerator is a sum over every ingredient and the
denominator is only the binder, which means adding cement to a mixture lowers
its chloride content without removing any chloride at all.

An ingredient with no assay on file is not treated as zero. It is reported, and
the result says the calculation is incomplete, because a chloride figure
computed with the aggregate left out is exactly the figure that passes when it
should not.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# Materials whose chloride is worth chasing when it has not been assayed. Water
# and admixtures are metered rather than weighed, so their contribution comes
# through a different route and is small enough that an absent assay on them is
# not what makes a calculation unusable.
_WORTH_ASSAYING = {
    MaterialClass.CEMENT,
    MaterialClass.SCM,
    MaterialClass.COARSE_AGGREGATE,
    MaterialClass.FINE_AGGREGATE,
}


@dataclass(frozen=True, slots=True)
class ChlorideContribution:
    """What one ingredient puts into the mixture."""

    material_code: str
    material_class: MaterialClass
    charge: Quantity
    assay: Percent | None

    @property
    def chloride(self) -> Quantity:
        """The chloride this ingredient contributes to one unit volume."""
        if self.assay is None:
            return Quantity.zero(self.charge.unit)
        return self.charge * self.assay.fraction

    @property
    def is_assayed(self) -> bool:
        """True when this ingredient has a figure on file."""
        return self.assay is not None

    @property
    def matters(self) -> bool:
        """True when an absent assay on this ingredient spoils the result."""
        return self.material_class in _WORTH_ASSAYING

    def describe(self) -> str:
        """One line for a chloride report."""
        assay = "not assayed" if self.assay is None else self.assay.format(3)
        return (
            f"{self.material_code}  {self.charge.format(0)}  {assay}  {self.chloride.format(3)}"
        )


@dataclass(frozen=True, slots=True)
class ChlorideResult:
    """The mixture's chloride content and how complete the figure is."""

    contributions: tuple[ChlorideContribution, ...]
    cementitious: Quantity

    @property
    def total(self) -> Quantity:
        """Chloride in one unit volume, from everything that was assayed."""
        running = Quantity.zero(self.cementitious.unit)
        for entry in self.contributions:
            running = running + entry.chloride.to(self.cementitious.unit)
        return running

    @property
    def content(self) -> Percent:
        """Chloride as a share of the cementitious content."""
        if self.cementitious.is_zero():
            raise ValidationError(
                "a mixture with no cementitious material has no chloride content",
                field="cementitious",
            )
        return Percent.from_fraction(self.total.base_value / self.cementitious.base_value)

    @property
    def unassayed(self) -> tuple[str, ...]:
        """Ingredients whose absent assay makes the figure incomplete."""
        return tuple(
            entry.material_code
            for entry in self.contributions
            if entry.matters and not entry.is_assayed
        )

    @property
    def is_complete(self) -> bool:
        """True when every ingredient worth assaying has been."""
        return not self.unassayed

    def describe(self) -> str:
        """One line for a submittal."""
        tail = (
            "" if self.is_complete else f", incomplete: {', '.join(self.unassayed)} not assayed"
        )
        return f"chloride is {self.content.format(3)} of the binder{tail}"


def chloride_content(proportions: Proportions, catalog: MaterialCatalog) -> ChlorideResult:
    """Add up the chloride every ingredient contributes."""
    one_unit = Quantity(1.0, proportions.volume_unit)
    weights = proportions.batch_weights(one_unit)
    contributions: list[ChlorideContribution] = []
    for charge in proportions.charges:
        material = catalog.get(charge.material_code)
        contributions.append(
            ChlorideContribution(
                charge.material_code,
                charge.material_class,
                weights[charge.material_code],
                material.chloride_content,
            )
        )
    return ChlorideResult(tuple(contributions), proportions.cementitious.times(one_unit))


def check_chloride(design: MixDesign, catalog: MaterialCatalog) -> tuple[str, ...]:
    """Judge a design's chloride against the limit its exposure imposes."""
    limit = design.exposure.max_chloride
    result = chloride_content(design.proportions, catalog)
    findings: list[str] = []
    if not result.is_complete:
        findings.append(
            f"{', '.join(result.unassayed)} has no chloride assay, so the content "
            "cannot be shown to meet the limit"
        )
    if limit is not None and result.content.value > limit.value + 1e-9:
        governing = design.exposure.governing_class("max_chloride")
        findings.append(
            f"chloride is {result.content.format(3)} of the binder and "
            f"{governing} allows {limit.format(2)}"
        )
    return tuple(findings)
