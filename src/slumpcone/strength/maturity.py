"""The maturity method: reading in-place strength off a temperature history.

A cylinder in a curing tank and a slab in the ground are the same concrete at
different temperatures, and they gain strength at different rates. Maturity is
the accounting that puts them on the same scale: the concrete's own age
weighted by how warm it has been.

Two functions do the weighting and they disagree on purpose. The temperature
time factor is a straight sum of degrees above a datum, which is easy to
compute on a data logger and slightly wrong at the extremes. Equivalent age
uses the Arrhenius relation, which is closer to what the chemistry does and
needs an activation energy the mixture has to be tested for.

Neither one predicts anything by itself. Both need a strength-maturity
relationship measured on that mixture, and the relationship is only good for
the mixture it was measured on. Reusing one across a change of cement is the
mistake the method invites.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature

# The datum temperature below which the mixture is taken to gain no strength.
# Zero Celsius is the usual figure for ordinary portland cement mixtures.
DEFAULT_DATUM = Temperature(0.0, "C")

# The activation energy divided by the gas constant, in kelvin. Around 5000 for
# a plain portland mixture; a mixture with a lot of slag runs higher.
DEFAULT_ACTIVATION = 5000.0

REFERENCE_TEMPERATURE = Temperature(20.0, "C")


@dataclass(frozen=True, slots=True)
class TemperatureReading:
    """One logger reading."""

    at: datetime
    temperature: Temperature


def _ordered(readings: Sequence[TemperatureReading]) -> tuple[TemperatureReading, ...]:
    if len(readings) < 2:
        raise ValidationError(
            "a maturity needs at least two readings to have an interval between them",
            field="readings",
        )
    ordered = tuple(sorted(readings, key=lambda entry: entry.at))
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        if later.at == earlier.at:
            raise ValidationError(
                f"two readings share the moment {later.at.isoformat()}", field="readings"
            )
    return ordered


def temperature_time_factor(
    readings: Sequence[TemperatureReading], datum: Temperature = DEFAULT_DATUM
) -> float:
    """Nurse-Saul maturity, in degree Celsius hours.

    Each interval is weighted by the average of the temperatures at its ends,
    less the datum, and an interval spent below the datum contributes nothing
    rather than a negative amount. Concrete does not un-cure.
    """
    ordered = _ordered(readings)
    total = 0.0
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        hours = (later.at - earlier.at).total_seconds() / 3600.0
        average = (earlier.temperature.celsius + later.temperature.celsius) / 2.0
        above = average - datum.celsius
        if above > 0.0:
            total += above * hours
    return total


def equivalent_age(
    readings: Sequence[TemperatureReading],
    *,
    activation: float = DEFAULT_ACTIVATION,
    reference: Temperature = REFERENCE_TEMPERATURE,
) -> float:
    """Arrhenius equivalent age at the reference temperature, in hours.

    The weighting is the ratio of reaction rates at the actual and reference
    temperatures, which means a load cured at the reference temperature has an
    equivalent age exactly equal to its real age, and one cured warmer has a
    larger one.
    """
    if activation <= 0.0:
        raise ValidationError("an activation energy has to be positive", field="activation")
    ordered = _ordered(readings)
    reference_kelvin = reference.celsius + 273.15
    total = 0.0
    for earlier, later in zip(ordered, ordered[1:], strict=False):
        hours = (later.at - earlier.at).total_seconds() / 3600.0
        average = (earlier.temperature.celsius + later.temperature.celsius) / 2.0
        kelvin = average + 273.15
        if kelvin <= 0.0:
            continue
        factor = math.exp(-activation * (1.0 / kelvin - 1.0 / reference_kelvin))
        total += factor * hours
    return total


@dataclass(frozen=True, slots=True)
class MaturityPoint:
    """One cylinder broken at a known maturity."""

    maturity: float
    strength: Quantity

    def __post_init__(self) -> None:
        if self.maturity <= 0.0:
            raise ValidationError("a maturity has to be positive", field="maturity")
        if self.strength.dimension.value != "pressure":
            raise ValidationError("a strength is a pressure", field="strength")
        if self.strength.value <= 0.0:
            raise ValidationError("a strength has to be positive", field="strength")


@dataclass(frozen=True, slots=True)
class MaturityCurve:
    """A strength-maturity relationship measured on one mixture."""

    mix_code: str
    points: tuple[MaturityPoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValidationError(
                "a strength-maturity relationship needs at least three ages",
                field="points",
            )
        ordered = sorted(self.points, key=lambda point: point.maturity)
        object.__setattr__(self, "points", tuple(ordered))

    @property
    def span(self) -> tuple[float, float]:
        """The lowest and highest maturity the curve was measured over."""
        return (self.points[0].maturity, self.points[-1].maturity)

    def covers(self, maturity: float) -> bool:
        """True when a maturity is inside the measured range."""
        low, high = self.span
        return low - 1e-9 <= maturity <= high + 1e-9

    def fit(self) -> tuple[float, float]:
        """A least squares fit of strength against the log of maturity.

        Returns the intercept and slope of ``S = a + b ln(M)``, which is the
        form C1074 uses and the one that stays sensible when it is extrapolated
        a little way past the last point.
        """
        logs = [math.log(point.maturity) for point in self.points]
        strengths = [point.strength.to("psi").value for point in self.points]
        count = len(logs)
        mean_log = sum(logs) / count
        mean_strength = sum(strengths) / count
        covariance = sum(
            (log - mean_log) * (strength - mean_strength)
            for log, strength in zip(logs, strengths, strict=True)
        )
        variance = sum((log - mean_log) ** 2 for log in logs)
        if variance <= 0.0:
            raise ValidationError(
                "every point is at the same maturity, so no curve can be fitted",
                field="points",
            )
        slope = covariance / variance
        return (mean_strength - slope * mean_log, slope)

    def strength_at(self, maturity: float) -> Quantity:
        """The strength the curve predicts at a maturity."""
        if maturity <= 0.0:
            raise ValidationError("a maturity has to be positive", field="maturity")
        intercept, slope = self.fit()
        predicted = intercept + slope * math.log(maturity)
        return Quantity(max(predicted, 0.0), "psi")

    def maturity_for(self, strength: Quantity) -> float:
        """The maturity at which the curve reaches a strength."""
        intercept, slope = self.fit()
        if abs(slope) < 1e-12:
            raise ValidationError("a flat curve never reaches a strength", field="points")
        return math.exp((strength.to("psi").value - intercept) / slope)

    def describe(self) -> str:
        """One line for a maturity report."""
        intercept, slope = self.fit()
        low, high = self.span
        return (
            f"{self.mix_code}: S = {intercept:.0f} + {slope:.0f} ln(M), "
            f"measured from {low:.0f} to {high:.0f}"
        )


@dataclass(frozen=True, slots=True)
class MaturityEstimate:
    """An in-place strength read off a curve, with how far it was trusted."""

    maturity: float
    strength: Quantity
    extrapolated: bool

    def describe(self) -> str:
        """One line for a maturity report."""
        tail = " (extrapolated past the measured range)" if self.extrapolated else ""
        return f"maturity {self.maturity:.0f} gives {self.strength.format(0)}{tail}"


def estimate_in_place(
    curve: MaturityCurve,
    readings: Sequence[TemperatureReading],
    datum: Temperature = DEFAULT_DATUM,
) -> MaturityEstimate:
    """Read an in-place strength off a curve and a temperature history."""
    maturity = temperature_time_factor(readings, datum)
    if maturity <= 0.0:
        raise ValidationError(
            "the history never rose above the datum, so no strength has been gained",
            field="readings",
        )
    return MaturityEstimate(maturity, curve.strength_at(maturity), not curve.covers(maturity))
