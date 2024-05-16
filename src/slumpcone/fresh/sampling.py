"""Whether a sample was taken in a way that lets its result reject a load.

C172 is specific and the specifics matter. An acceptance sample is composited
from at least two portions taken at regularly spaced intervals out of the
middle of the load, never from the very start or the very end of discharge.
The portions have to be combined within fifteen minutes of each other, and
testing has to start promptly after that: five minutes for slump and air,
fifteen for moulding cylinders.

A sample that misses any of these is not invalid concrete. It is an invalid
*test*, and the difference is the whole argument when a load gets rejected off
a bucket scooped from the first thing out of the chute.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_ticket_number
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# The head and tail of the load an acceptance sample may not come from.
EXCLUDED_END = Quantity(0.25, "yd3")

MIN_PORTIONS = 2
MAX_PORTION_SPAN_MINUTES = 15.0
MAX_START_DELAY_PROPERTY_MINUTES = 5.0
MAX_START_DELAY_SPECIMEN_MINUTES = 15.0


@dataclass(frozen=True, slots=True)
class Sample:
    """How and when a sample was taken off a load."""

    ticket_number: str
    load_volume: Quantity
    discharged_before: Quantity
    portions: int = MIN_PORTIONS
    portion_span_minutes: float = 0.0
    start_delay_minutes: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticket_number", normalize_ticket_number(self.ticket_number))
        for name, amount in (
            ("load_volume", self.load_volume),
            ("discharged_before", self.discharged_before),
        ):
            if amount.dimension.value != "volume":
                raise ValidationError(f"{name} is a volume", field=name)
            if amount.value < 0.0:
                raise ValidationError(f"{name} cannot be negative", field=name)
        if self.load_volume.is_zero():
            raise ValidationError("a load has to have a volume", field="load_volume")
        if self.discharged_before > self.load_volume:
            raise ValidationError(
                "more was discharged before the sample than the load held",
                field="discharged_before",
            )
        if self.portions < 1:
            raise ValidationError("a sample is at least one portion", field="portions")
        if self.portion_span_minutes < 0.0:
            raise ValidationError(
                "a portion span cannot be negative", field="portion_span_minutes"
            )
        if self.start_delay_minutes < 0.0:
            raise ValidationError(
                "a start delay cannot be negative", field="start_delay_minutes"
            )

    @property
    def discharged_fraction(self) -> Percent:
        """How far through the load the sample was taken."""
        return Percent.from_fraction(
            self.discharged_before.base_value / self.load_volume.base_value
        )

    @property
    def remaining(self) -> Quantity:
        """How much was still in the drum when the sample was taken."""
        return self.load_volume - self.discharged_before.to(self.load_volume.unit)

    @property
    def is_from_the_head(self) -> bool:
        """True when the sample came out of the first part of the load."""
        return self.discharged_before < EXCLUDED_END

    @property
    def is_from_the_tail(self) -> bool:
        """True when the sample came out of the last part of the load."""
        return self.remaining < EXCLUDED_END


def check_sample(sample: Sample, *, for_specimens: bool = False) -> tuple[str, ...]:
    """Everything about ``sample`` that stops its result being an acceptance test."""
    faults: list[str] = []
    if sample.is_from_the_head:
        faults.append(
            f"taken after only {sample.discharged_before.format(2)} discharged, "
            f"the first {EXCLUDED_END.format(2)} does not count"
        )
    if sample.is_from_the_tail:
        faults.append(
            f"taken with {sample.remaining.format(2)} left, the last "
            f"{EXCLUDED_END.format(2)} does not count"
        )
    if sample.portions < MIN_PORTIONS:
        faults.append(
            f"composited from {sample.portions} portion, at least {MIN_PORTIONS} are needed"
        )
    if sample.portion_span_minutes > MAX_PORTION_SPAN_MINUTES + 1e-9:
        faults.append(
            f"portions {sample.portion_span_minutes:g} minutes apart, the limit is "
            f"{MAX_PORTION_SPAN_MINUTES:g}"
        )
    limit = (
        MAX_START_DELAY_SPECIMEN_MINUTES if for_specimens else MAX_START_DELAY_PROPERTY_MINUTES
    )
    if sample.start_delay_minutes > limit + 1e-9:
        what = "moulding" if for_specimens else "testing"
        faults.append(
            f"{what} began {sample.start_delay_minutes:g} minutes after the sample, "
            f"the limit is {limit:g}"
        )
    return tuple(faults)


def is_acceptance_sample(sample: Sample, *, for_specimens: bool = False) -> bool:
    """True when a result off this sample may accept or reject the load."""
    return not check_sample(sample, for_specimens=for_specimens)
