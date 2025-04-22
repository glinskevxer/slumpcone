"""Emission factors, and where a figure came from.

Every number in a concrete carbon calculation is a global warming potential per
unit mass of an ingredient, and every one of them is arguable. A plant reporting
against a Buy Clean threshold is asked not only what the number is but where it
came from, so a factor here carries its source and its vintage as well as its
value. A factor with no source is still usable, and still says so.

The stage matters as much as the number. Cradle to gate covers raw material
supply, transport to the plant and manufacturing, which is A1 through A3 in the
EN 15804 lettering that every concrete EPD uses. A factor measured over a
different stage cannot be added to one measured over A1 through A3, and this
module refuses to rather than quietly producing a total that means nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.errors import RuleViolationError
from slumpcone.identity import normalize_code
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.quantity import Quantity


class CarbonError(RuleViolationError):
    """A carbon figure that cannot be produced honestly."""


class Stage(Enum):
    """The life cycle stages a factor covers, in EN 15804 lettering."""

    A1_A3 = "A1-A3"
    A4 = "A4"
    A5 = "A5"

    def __str__(self) -> str:
        return self.value

    @property
    def label(self) -> str:
        """What the stage covers, in words."""
        return {
            Stage.A1_A3: "cradle to gate: supply, transport in, manufacture",
            Stage.A4: "transport from the gate to the site",
            Stage.A5: "placing, and what is wasted doing it",
        }[self]


class Provenance(Enum):
    """How much weight a factor carries."""

    PRODUCT_EPD = "product epd"
    INDUSTRY_AVERAGE = "industry average"
    ESTIMATE = "estimate"

    def __str__(self) -> str:
        return self.value

    @property
    def is_declarable(self) -> bool:
        """Only a product EPD can be quoted against a procurement threshold."""
        return self is Provenance.PRODUCT_EPD


@dataclass(frozen=True, slots=True)
class EmissionFactor:
    """Kilograms of carbon dioxide equivalent per unit mass of one material."""

    material_code: str
    material_class: MaterialClass
    kg_co2e_per_kg: float
    stage: Stage = Stage.A1_A3
    provenance: Provenance = Provenance.INDUSTRY_AVERAGE
    source: str = ""
    published_on: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        if self.kg_co2e_per_kg < 0.0:
            raise CarbonError(
                "CARBON_FACTOR_NEGATIVE",
                f"{self.material_code} cannot have a negative emission factor",
            )
        if self.provenance is Provenance.PRODUCT_EPD and not self.source:
            raise CarbonError(
                "CARBON_EPD_WITHOUT_SOURCE",
                f"{self.material_code} claims a product EPD but names no document",
            )

    def emissions(self, mass: Quantity) -> float:
        """What this much of the material carries, in kilograms."""
        return self.kg_co2e_per_kg * mass.to("kg").value

    def is_stale(self, on: date, *, years: int = 5) -> bool:
        """Whether the declaration has aged out.

        An EPD is valid for five years from publication. A factor with no date
        cannot be shown to be current, so it reads as stale rather than fresh.
        """
        if self.published_on is None:
            return True
        return (on - self.published_on).days > years * 365

    def describe(self) -> str:
        """One line."""
        tail = f", {self.source}" if self.source else ""
        return (
            f"{self.material_code}: {self.kg_co2e_per_kg:.4f} kg CO2e/kg "
            f"({self.stage}, {self.provenance}{tail})"
        )


# Industry average cradle to gate figures, close enough to the published North
# American ones to be worth shipping as a starting point and clearly labelled so
# nobody reports off them. A plant replaces these with its suppliers' EPDs.
DEFAULT_FACTORS: tuple[EmissionFactor, ...] = (
    EmissionFactor("OPC", MaterialClass.CEMENT, 0.922, source="NRMCA industry average"),
    EmissionFactor("PLC", MaterialClass.CEMENT, 0.846, source="NRMCA industry average"),
    EmissionFactor("FLYASH", MaterialClass.SCM, 0.027, source="allocation at the stack"),
    EmissionFactor("SLAG", MaterialClass.SCM, 0.143, source="granulation and grinding"),
    EmissionFactor("SILICA", MaterialClass.SCM, 0.014, source="allocation at the stack"),
    EmissionFactor("COARSE", MaterialClass.COARSE_AGGREGATE, 0.0075),
    EmissionFactor("FINE", MaterialClass.FINE_AGGREGATE, 0.0048),
    EmissionFactor("WATER", MaterialClass.WATER, 0.0003),
    EmissionFactor("ADMIX", MaterialClass.ADMIXTURE, 1.88, source="EFCA average"),
)


class FactorBook:
    """The factors a plant reports against, looked up by material code."""

    def __init__(self, factors: Iterable[EmissionFactor] = ()) -> None:
        self._by_code: dict[str, EmissionFactor] = {}
        for factor in factors:
            self.add(factor)

    @classmethod
    def defaults(cls) -> FactorBook:
        """A book carrying the shipped industry averages."""
        return cls(DEFAULT_FACTORS)

    def add(self, factor: EmissionFactor) -> EmissionFactor:
        """File a factor, replacing any earlier one for the same material."""
        self._by_code[factor.material_code] = factor
        return factor

    def get(self, material_code: str) -> EmissionFactor:
        """The factor for one material."""
        key = normalize_code(material_code, field="material_code")
        factor = self._by_code.get(key)
        if factor is None:
            raise CarbonError("CARBON_NO_FACTOR", f"no emission factor on file for {key}")
        return factor

    def has(self, material_code: str) -> bool:
        """Whether a material has a factor."""
        return normalize_code(material_code, field="material_code") in self._by_code

    def missing(self, material_codes: Iterable[str]) -> tuple[str, ...]:
        """Which of these materials has no factor, in the order asked."""
        return tuple(code for code in material_codes if not self.has(code))

    def stale(self, on: date, *, years: int = 5) -> tuple[EmissionFactor, ...]:
        """Every factor whose declaration has aged out."""
        return tuple(
            factor
            for factor in sorted(self._by_code.values(), key=lambda one: one.material_code)
            if factor.is_stale(on, years=years)
        )

    def declarable(self) -> tuple[EmissionFactor, ...]:
        """The factors backed by a product EPD."""
        return tuple(
            factor
            for factor in sorted(self._by_code.values(), key=lambda one: one.material_code)
            if factor.provenance.is_declarable
        )

    def same_stage(self) -> Stage:
        """The stage every factor in the book covers.

        Adding a cradle to gate figure to a delivery figure gives a number that
        is not a total of anything, so the book refuses to be read as one until
        somebody separates them.
        """
        stages = {factor.stage for factor in self._by_code.values()}
        if not stages:
            raise CarbonError("CARBON_EMPTY_BOOK", "the factor book is empty")
        if len(stages) > 1:
            named = ", ".join(sorted(str(stage) for stage in stages))
            raise CarbonError(
                "CARBON_MIXED_STAGES",
                f"the book mixes life cycle stages ({named}) and cannot be totalled",
            )
        return stages.pop()

    def as_mapping(self) -> Mapping[str, EmissionFactor]:
        """A read only view, for callers that want to iterate."""
        return dict(self._by_code)

    def __len__(self) -> int:
        return len(self._by_code)

    def __contains__(self, material_code: object) -> bool:
        return isinstance(material_code, str) and self.has(material_code)
