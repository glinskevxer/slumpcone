"""Predicting how much slump a load loses on the way to the job.

This is a model, not a measurement, and it is here because dispatch has to
answer a question nobody can measure in advance: will this load still be
placeable when it gets there. A truck sent forty minutes away with a four inch
slump on a ninety degree day arrives at two, and the crew adds water, and the
strength goes with it.

The model is deliberately simple and its constants are plant settings rather
than physics. Loss is a rate per hour, the rate doubles for every twenty
degrees above the reference temperature, and a retarding admixture halves it. A
plant that measures its own loss rate should put its own number in; the shape
of the curve is what is worth having, not the default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature

REFERENCE_TEMPERATURE = Temperature(70.0, "F")
DEFAULT_RATE = Quantity(1.0, "in")
DOUBLING_INTERVAL = 20.0
RETARDER_FACTOR = 0.5

# Below this a load is not placeable by ordinary means whatever the ticket says.
UNPLACEABLE_BELOW = Quantity(1.0, "in")


@dataclass(frozen=True, slots=True)
class SlumpLossModel:
    """One plant's own loss rate, and how it moves with temperature."""

    rate_per_hour: Quantity = DEFAULT_RATE
    reference: Temperature = REFERENCE_TEMPERATURE
    doubling_interval: float = DOUBLING_INTERVAL

    def __post_init__(self) -> None:
        if self.rate_per_hour.dimension.value != "length":
            raise ValidationError("a slump loss rate is a length", field="rate_per_hour")
        if self.rate_per_hour.value < 0.0:
            raise ValidationError("a slump loss rate cannot be negative", field="rate_per_hour")
        if self.doubling_interval <= 0.0:
            raise ValidationError(
                "a doubling interval has to be positive", field="doubling_interval"
            )

    def rate_at(self, temperature: Temperature, *, has_retarder: bool = False) -> Quantity:
        """The loss rate at a concrete temperature."""
        degrees = temperature.fahrenheit - self.reference.fahrenheit
        factor = float(2.0 ** (degrees / self.doubling_interval))
        if has_retarder:
            factor *= RETARDER_FACTOR
        return self.rate_per_hour * factor

    def slump_after(
        self,
        initial: Quantity,
        elapsed: timedelta,
        temperature: Temperature,
        *,
        has_retarder: bool = False,
    ) -> Quantity:
        """The slump the model expects after a haul, floored at nothing."""
        if initial.dimension.value != "length":
            raise ValidationError("a slump is a length", field="initial")
        if elapsed.total_seconds() < 0.0:
            raise ValidationError("elapsed time cannot be negative", field="elapsed")
        hours = elapsed.total_seconds() / 3600.0
        lost = self.rate_at(temperature, has_retarder=has_retarder) * hours
        remaining = initial.to("in").value - lost.to("in").value
        return Quantity(max(remaining, 0.0), "in")

    def time_to(
        self,
        initial: Quantity,
        target: Quantity,
        temperature: Temperature,
        *,
        has_retarder: bool = False,
    ) -> timedelta:
        """How long until the slump falls to a target."""
        if target > initial:
            raise ValidationError(
                "a load does not gain slump on the way to the job", field="target"
            )
        rate = self.rate_at(temperature, has_retarder=has_retarder)
        if rate.is_zero():
            raise ValidationError(
                "at a zero loss rate the slump never reaches the target", field="target"
            )
        hours = (initial.to("in").value - target.to("in").value) / rate.to("in").value
        return timedelta(hours=hours)

    def workable_window(
        self,
        initial: Quantity,
        temperature: Temperature,
        *,
        floor: Quantity = UNPLACEABLE_BELOW,
        has_retarder: bool = False,
    ) -> timedelta:
        """How long the load stays above a placeable slump."""
        return self.time_to(initial, floor, temperature, has_retarder=has_retarder)


@dataclass(frozen=True, slots=True)
class ArrivalForecast:
    """What one load is expected to arrive at."""

    initial: Quantity
    elapsed: timedelta
    temperature: Temperature
    predicted: Quantity
    window: timedelta

    @property
    def is_placeable(self) -> bool:
        """True when the load should still go in the forms on arrival."""
        return self.predicted >= UNPLACEABLE_BELOW

    @property
    def margin(self) -> timedelta:
        """How much of the workable window is left on arrival."""
        return self.window - self.elapsed

    def describe(self) -> str:
        """One line for a dispatch board."""
        minutes = int(round(self.margin.total_seconds() / 60.0))
        verdict = "placeable" if self.is_placeable else "too stiff"
        return (
            f"{self.initial.format(1)} at {self.temperature} arrives at "
            f"{self.predicted.format(1)} after "
            f"{int(round(self.elapsed.total_seconds() / 60.0))} minutes, "
            f"{verdict} with {minutes} minutes of window left"
        )


def forecast(
    initial: Quantity,
    elapsed: timedelta,
    temperature: Temperature,
    *,
    model: SlumpLossModel | None = None,
    has_retarder: bool = False,
) -> ArrivalForecast:
    """What a load is expected to arrive at, and how much window is left."""
    chosen = model or SlumpLossModel()
    return ArrivalForecast(
        initial,
        elapsed,
        temperature,
        chosen.slump_after(initial, elapsed, temperature, has_retarder=has_retarder),
        chosen.workable_window(initial, temperature, has_retarder=has_retarder),
    )
