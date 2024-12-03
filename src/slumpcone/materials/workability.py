"""Reading a combined gradation: the coarseness chart and the power curve.

Two ways of looking at the same combined curve, and they answer different
questions.

The coarseness factor and workability factor put one mixture on a chart as a
single point, and the zone that point lands in says how it will behave: well
graded, sandy and sticky, rocky and prone to segregation, or gap graded. The
workability factor is adjusted for cementitious content, because paste does
some of the work sand would otherwise have to.

The power curve asks a narrower question: how far the combined grading departs
from the maximum density line through the nominal maximum size. A curve that
sits above the line is sand heavy and a curve below it is stone heavy, and the
size of the departure is what a placement crew feels.

The zone boundaries are the ones this plant has drawn on its own chart. They
are constants here rather than literals in the code so a plant that draws them
somewhere else can say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.materials.gradation import Gradation, sieve
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# The cementitious content the workability factor is quoted against, and how
# much the factor moves per hundredweight away from it.
REFERENCE_CEMENTITIOUS = Quantity(564.0, "lb")
WORKABILITY_PER_CWT = 2.5

# Where the zones sit on the chart.
ROCKY_ABOVE = 75.0
FINE_BELOW = 45.0
TREND_SLOPE = 0.5
TREND_LOWER = 3.33
TREND_UPPER = 8.33


class WorkabilityZone(Enum):
    """Where a mixture lands on the coarseness chart."""

    WELL_GRADED = "well graded"
    SANDY = "sandy"
    ROCKY = "rocky"
    GAP_GRADED = "gap graded"
    FINE = "fine"

    def __str__(self) -> str:
        return self.value

    @property
    def places_well(self) -> bool:
        """True for the one zone a placement crew is happy with."""
        return self is WorkabilityZone.WELL_GRADED


def coarseness_factor(grading: Gradation) -> float:
    """Cumulative retained on the 3/8 inch, as a share of that on the No. 8.

    A high number means most of the coarse material is genuinely coarse; a low
    one means the mixture's "stone" is really intermediate sized.
    """
    on_eighth = grading.retained_on("3/8 in")
    on_eight = grading.retained_on("No. 8")
    if on_eighth is None or on_eight is None:
        raise ValidationError(
            "the coarseness factor needs the 3/8 in and No. 8 sieves", field="grading"
        )
    if on_eight.value <= 0.0:
        raise ValidationError(
            "nothing is retained on the No. 8, so there is no coarseness factor",
            field="grading",
        )
    return 100.0 * on_eighth.value / on_eight.value


def workability_factor(grading: Gradation, cementitious: Quantity | None = None) -> float:
    """Percent passing the No. 8, adjusted for cementitious content."""
    passing = grading.passing_on("No. 8")
    if passing is None:
        raise ValidationError("the workability factor needs the No. 8 sieve", field="grading")
    if cementitious is None:
        return passing.value
    if cementitious.dimension.value != "mass":
        raise ValidationError("a cementitious content is a mass", field="cementitious")
    hundredweights = (
        cementitious.to("lb").value - REFERENCE_CEMENTITIOUS.to("lb").value
    ) / 94.0
    return passing.value + hundredweights * WORKABILITY_PER_CWT


def zone_of(coarseness: float, workability: float) -> WorkabilityZone:
    """Which zone a point on the chart falls in."""
    if coarseness > ROCKY_ABOVE:
        return WorkabilityZone.ROCKY
    if coarseness < FINE_BELOW:
        return WorkabilityZone.FINE
    lower = TREND_SLOPE * coarseness + TREND_LOWER
    upper = TREND_SLOPE * coarseness + TREND_UPPER
    if workability > upper:
        return WorkabilityZone.SANDY
    if workability < lower:
        return WorkabilityZone.GAP_GRADED
    return WorkabilityZone.WELL_GRADED


@dataclass(frozen=True, slots=True)
class ChartPoint:
    """One mixture's position on the coarseness chart."""

    coarseness: float
    workability: float

    @property
    def zone(self) -> WorkabilityZone:
        """Which zone the point is in."""
        return zone_of(self.coarseness, self.workability)

    @property
    def distance_from_trend(self) -> float:
        """How far above or below the middle of the well graded band it sits."""
        middle = TREND_SLOPE * self.coarseness + (TREND_LOWER + TREND_UPPER) / 2.0
        return self.workability - middle

    def describe(self) -> str:
        """One line for a gradation report."""
        return (
            f"CF {self.coarseness:.1f}, WF {self.workability:.1f} -> {self.zone} "
            f"({self.distance_from_trend:+.1f} from the trend)"
        )


def chart_point(grading: Gradation, cementitious: Quantity | None = None) -> ChartPoint:
    """Put a combined gradation on the coarseness chart."""
    return ChartPoint(coarseness_factor(grading), workability_factor(grading, cementitious))


def power_line(nominal_max_size: Quantity, opening_mm: float, exponent: float = 0.45) -> float:
    """Percent passing on the maximum density line, at one sieve opening."""
    if nominal_max_size.dimension.value != "length":
        raise ValidationError("a nominal maximum size is a length", field="nominal_max_size")
    top = nominal_max_size.to("mm").value
    if top <= 0.0:
        raise ValidationError(
            "a nominal maximum size has to be positive", field="nominal_max_size"
        )
    if opening_mm >= top:
        return 100.0
    return float(100.0 * (opening_mm / top) ** exponent)


@dataclass(frozen=True, slots=True)
class PowerDeviation:
    """How far a combined curve sits from the maximum density line."""

    sieve_label: str
    measured: Percent
    line: float

    @property
    def deviation(self) -> float:
        """Measured less the line, positive when the curve is sand heavy."""
        return self.measured.value - self.line

    def describe(self) -> str:
        """One line for a gradation report."""
        return (
            f"{self.sieve_label}: {self.measured.format(1)} against "
            f"{self.line:.1f} on the line ({self.deviation:+.1f})"
        )


def power_deviations(
    grading: Gradation, nominal_max_size: Quantity, exponent: float = 0.45
) -> tuple[PowerDeviation, ...]:
    """The departure from the maximum density line, sieve by sieve."""
    found: list[PowerDeviation] = []
    for sieve_, passing in grading.passing:
        found.append(
            PowerDeviation(
                sieve_.label,
                passing,
                power_line(nominal_max_size, sieve_.opening_mm, exponent),
            )
        )
    return tuple(found)


def largest_departure(
    grading: Gradation, nominal_max_size: Quantity, exponent: float = 0.45
) -> PowerDeviation:
    """The sieve furthest from the line, which is where the trouble is."""
    deviations = power_deviations(grading, nominal_max_size, exponent)
    if not deviations:
        raise ValidationError("an empty gradation has no departure", field="grading")
    return max(deviations, key=lambda entry: abs(entry.deviation))


def is_sand_heavy(grading: Gradation, nominal_max_size: Quantity) -> bool:
    """True when the curve sits above the line where it matters most.

    Judged on the No. 8, because that is the sieve the sand share shows up on
    and the one a finisher notices.
    """
    passing = grading.passing_on("No. 8")
    if passing is None:
        raise ValidationError("this test needs the No. 8 sieve", field="grading")
    return passing.value > power_line(nominal_max_size, sieve("No. 8").opening_mm)
