"""Setting time by penetration resistance.

A technician sieves the mortar out of a sample and pushes needles into it every
half hour, recording the force each needle needs. The resistance climbs, and
the times at which it passes five hundred and four thousand pounds per square
inch are the initial and final set.

Neither of those times is measured directly. They are read off a curve fitted
through the readings, and the fit is done on the logarithms of both axes,
because resistance against time is a straight line there and a curve anywhere
else. Fitting it straight on the raw numbers puts initial set out by twenty
minutes, which is the difference between a finisher waiting and a finisher
going home.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity

INITIAL_SET = Quantity(500.0, "psi")
FINAL_SET = Quantity(4000.0, "psi")

# Readings outside this band say nothing about either set time: below it the
# needle is measuring the sample's own weight, above it the mortar is concrete.
USEFUL_LOW = Quantity(50.0, "psi")
USEFUL_HIGH = Quantity(6000.0, "psi")


@dataclass(frozen=True, slots=True)
class PenetrationReading:
    """One needle, at one elapsed time."""

    elapsed_hours: float
    resistance: Quantity

    def __post_init__(self) -> None:
        if self.elapsed_hours <= 0.0:
            raise ValidationError("an elapsed time has to be positive", field="elapsed_hours")
        if self.resistance.dimension.value != "pressure":
            raise ValidationError("a penetration resistance is a pressure", field="resistance")
        if self.resistance.value <= 0.0:
            raise ValidationError(
                "a penetration resistance has to be positive", field="resistance"
            )

    @property
    def is_useful(self) -> bool:
        """True when this reading is inside the band the fit uses."""
        return USEFUL_LOW <= self.resistance <= USEFUL_HIGH


@dataclass(frozen=True, slots=True)
class SettingCurve:
    """The readings from one sample, and the set times they give."""

    sample_code: str
    readings: tuple[PenetrationReading, ...]

    def __post_init__(self) -> None:
        useful = [reading for reading in self.readings if reading.is_useful]
        if len(useful) < 3:
            raise ValidationError(
                "a setting curve needs at least three readings inside the useful band",
                field="readings",
            )
        object.__setattr__(
            self,
            "readings",
            tuple(sorted(self.readings, key=lambda entry: entry.elapsed_hours)),
        )

    @property
    def useful(self) -> tuple[PenetrationReading, ...]:
        """The readings the fit actually uses."""
        return tuple(reading for reading in self.readings if reading.is_useful)

    def fit(self) -> tuple[float, float]:
        """Least squares on the logarithms, returning intercept and slope.

        The relation is ``ln(R) = a + b ln(t)``, so the slope is the exponent
        of the power law and a steeper slope means a sharper set.
        """
        times = [math.log(reading.elapsed_hours) for reading in self.useful]
        forces = [math.log(reading.resistance.to("psi").value) for reading in self.useful]
        count = len(times)
        mean_time = sum(times) / count
        mean_force = sum(forces) / count
        covariance = sum(
            (time - mean_time) * (force - mean_force)
            for time, force in zip(times, forces, strict=True)
        )
        variance = sum((time - mean_time) ** 2 for time in times)
        if variance <= 0.0:
            raise ValidationError(
                "every reading is at the same time, so no curve can be fitted",
                field="readings",
            )
        slope = covariance / variance
        if slope <= 0.0:
            raise ValidationError(
                "resistance falls with time in these readings, which is not a set",
                field="readings",
            )
        return (mean_force - slope * mean_time, slope)

    def time_at(self, resistance: Quantity) -> timedelta:
        """When the curve reaches a resistance."""
        if resistance.dimension.value != "pressure":
            raise ValidationError("a resistance is a pressure", field="resistance")
        intercept, slope = self.fit()
        hours = math.exp((math.log(resistance.to("psi").value) - intercept) / slope)
        return timedelta(hours=hours)

    @property
    def initial_set(self) -> timedelta:
        """Time to five hundred pounds per square inch."""
        return self.time_at(INITIAL_SET)

    @property
    def final_set(self) -> timedelta:
        """Time to four thousand pounds per square inch."""
        return self.time_at(FINAL_SET)

    @property
    def span(self) -> timedelta:
        """How long the mixture takes to go from initial to final set."""
        return self.final_set - self.initial_set

    @property
    def is_extrapolated(self) -> bool:
        """True when a set time falls outside the readings that were taken.

        A sample nobody stayed late enough to finish gives a final set read off
        the far end of the fit, which is a guess dressed as a measurement.
        """
        highest = max(reading.resistance for reading in self.useful)
        lowest = min(reading.resistance for reading in self.useful)
        return highest < FINAL_SET or lowest > INITIAL_SET

    def describe(self) -> str:
        """One line for a setting report."""
        tail = " (extrapolated)" if self.is_extrapolated else ""
        return (
            f"{self.sample_code}: initial {_hours(self.initial_set)}, "
            f"final {_hours(self.final_set)}{tail}"
        )


def _hours(span: timedelta) -> str:
    total_minutes = int(round(span.total_seconds() / 60.0))
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def curve_from(sample_code: str, readings: Sequence[tuple[float, float]]) -> SettingCurve:
    """Build a curve from ``(hours, psi)`` pairs, which is how a sheet reads."""
    return SettingCurve(
        sample_code,
        tuple(PenetrationReading(hours, Quantity(psi, "psi")) for hours, psi in readings),
    )


def retardation(plain: SettingCurve, dosed: SettingCurve) -> timedelta:
    """How much longer a dosed mixture takes to reach initial set.

    Negative when the admixture accelerated it, which is what an accelerator is
    supposed to do and what a retarder doing it means somebody swapped a drum.
    """
    return dosed.initial_set - plain.initial_set
