"""Judging a footprint against a published limit.

A procurement rule does not ask what a mixture carries. It asks whether the
mixture is under a number, and the number depends on the strength class, because
a 6000 psi mix that meets a 3000 psi limit does not exist. So a benchmark table
is a set of limits indexed by strength, and reading it means finding the class a
mixture falls in rather than interpolating between two.

Interpolating is the tempting mistake and it is wrong in a way that always
favours the plant. The published tables are step functions on purpose: a class
covers a range and every mixture in the range gets the same limit. Reading a
4200 psi mix against a number two thirds of the way from the 4000 limit to the
5000 one gives it allowance it was never granted. This module steps.

Two more rules come with these programmes and both are refusals rather than
arithmetic. A declaration has to be backed by a product EPD, not an industry
average, and the EPD has to be current. A footprint that beats the limit on
numbers taken from a five year old industry table has not met anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from slumpcone.carbon.factors import CarbonError, FactorBook
from slumpcone.carbon.footprint import Footprint
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class BenchmarkClass:
    """One row of a published table: a strength floor and the limit it carries."""

    floor: Quantity
    limit_kg_per_m3: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.floor.value <= 0.0:
            raise CarbonError(
                "BENCHMARK_FLOOR_NOT_POSITIVE", "a strength class needs a positive floor"
            )
        if self.limit_kg_per_m3 <= 0.0:
            raise CarbonError(
                "BENCHMARK_LIMIT_NOT_POSITIVE", "a benchmark limit has to be positive"
            )

    def covers(self, strength: Quantity) -> bool:
        """Whether a specified strength falls at or above this floor."""
        return strength.to("psi").value >= self.floor.to("psi").value - 1e-9

    def describe(self) -> str:
        """One line."""
        name = self.label or f"{self.floor.format(0)} and up"
        return f"{name}: {self.limit_kg_per_m3:.0f} kg CO2e/m3"


# The shape of a regional benchmark table, carrying figures near the published
# national member averages. Every programme publishes its own and a plant loads
# the one it is being measured against, so these exist to be replaced.
DEFAULT_CLASSES: tuple[BenchmarkClass, ...] = (
    BenchmarkClass(Quantity(2500, "psi"), 261.0, "2500 to 2999 psi"),
    BenchmarkClass(Quantity(3000, "psi"), 274.0, "3000 to 3999 psi"),
    BenchmarkClass(Quantity(4000, "psi"), 307.0, "4000 to 4999 psi"),
    BenchmarkClass(Quantity(5000, "psi"), 342.0, "5000 to 5999 psi"),
    BenchmarkClass(Quantity(6000, "psi"), 375.0, "6000 to 7999 psi"),
    BenchmarkClass(Quantity(8000, "psi"), 435.0, "8000 psi and up"),
)


class BenchmarkTable:
    """A published table of limits, read by strength class."""

    def __init__(self, classes: Sequence[BenchmarkClass], name: str = "") -> None:
        if not classes:
            raise CarbonError("BENCHMARK_EMPTY_TABLE", "a benchmark table needs a row")
        self._classes = tuple(
            sorted(classes, key=lambda row: row.floor.to("psi").value, reverse=True)
        )
        self.name = name

    @classmethod
    def defaults(cls) -> BenchmarkTable:
        """The shipped table shape."""
        return cls(DEFAULT_CLASSES, "shipped national average shape")

    @property
    def classes(self) -> tuple[BenchmarkClass, ...]:
        """Every row, strongest first."""
        return self._classes

    def limit_for(self, strength: Quantity) -> BenchmarkClass:
        """The row a specified strength falls in.

        The table steps rather than interpolating, so a 4200 psi mixture is read
        against the 4000 psi limit and gets no credit for the eight hundred
        pounds it does not have.
        """
        for row in self._classes:
            if row.covers(strength):
                return row
        weakest = self._classes[-1]
        raise CarbonError(
            "BENCHMARK_BELOW_TABLE",
            f"{strength.format(0)} falls below the weakest class, {weakest.floor.format(0)}",
        )


@dataclass(frozen=True, slots=True)
class Assessment:
    """One footprint judged against one limit."""

    mix_code: str
    strength: Quantity
    found_kg_per_m3: float
    limit: BenchmarkClass
    declarable: bool
    stale_factors: tuple[str, ...] = ()

    @property
    def margin(self) -> float:
        """How far under the limit, in kilograms per cubic metre. Negative is over."""
        return self.limit.limit_kg_per_m3 - self.found_kg_per_m3

    @property
    def under_limit(self) -> bool:
        """Whether the number alone clears."""
        return self.margin >= -1e-9

    @property
    def below_by(self) -> Percent:
        """How far under, as a share of the limit."""
        return Percent.from_fraction(self.margin / self.limit.limit_kg_per_m3)

    @property
    def can_be_declared(self) -> bool:
        """Whether this could be submitted, not just whether the number is small.

        Three things have to hold: the mixture is under the limit, every factor
        behind the number is a product EPD, and none of them has aged out.
        """
        return self.under_limit and self.declarable and not self.stale_factors

    @property
    def blockers(self) -> tuple[str, ...]:
        """What stands between this and a declaration, in the order to fix it."""
        reasons = []
        if not self.under_limit:
            reasons.append(f"over the limit by {abs(self.margin):.1f} kg CO2e/m3")
        if not self.declarable:
            reasons.append("the factors are not all product EPDs")
        if self.stale_factors:
            named = ", ".join(self.stale_factors)
            reasons.append(f"these declarations have aged out: {named}")
        return tuple(reasons)

    def describe(self) -> str:
        """One line."""
        verdict = "declarable" if self.can_be_declared else "not declarable"
        return (
            f"{self.mix_code}: {self.found_kg_per_m3:.1f} against "
            f"{self.limit.limit_kg_per_m3:.0f} kg CO2e/m3, {verdict}"
        )


def assess(
    footprint: Footprint,
    strength: Quantity,
    table: BenchmarkTable,
    book: FactorBook,
    on: date,
    *,
    years: int = 5,
) -> Assessment:
    """Judge a footprint against a table, and say whether it could be declared."""
    counted = {line.material_code for line in footprint.contributions}
    used = [factor for factor in book.as_mapping().values() if factor.material_code in counted]
    declarable = bool(used) and all(factor.provenance.is_declarable for factor in used)
    stale = tuple(
        sorted(factor.material_code for factor in used if factor.is_stale(on, years=years))
    )
    return Assessment(
        footprint.mix_code,
        strength,
        footprint.per_cubic_metre,
        table.limit_for(strength),
        declarable,
        stale,
    )
