"""The discharge limits, and the three things that move them.

C94 gives a load ninety minutes from the water hitting the cement, or three
hundred drum revolutions, whichever comes first. Two limits, not one, and a
truck idling on a job for an hour with the drum turning can run out of
revolutions long before it runs out of time.

Three things change the limits. A retarding or stabilising admixture extends
the time, because that is what it is for. Hot concrete shortens it, because
everything happens faster. And the purchaser may waive the time limit
altogether if the concrete is still placeable, which is a decision that has to
be recorded against the load rather than assumed.

The revolution limit is not waivable and no admixture extends it. Three hundred
revolutions is a mechanical limit on how much the aggregate can be ground
against itself before the mixture is a different material.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from slumpcone.errors import ValidationError
from slumpcone.units.temperature import Temperature

BASE_TIME_LIMIT = timedelta(minutes=90)
HOT_WEATHER_TIME_LIMIT = timedelta(minutes=60)
RETARDED_TIME_LIMIT = timedelta(minutes=180)
REVOLUTION_LIMIT = 300

# Above this the load is in hot weather and the clock runs shorter.
HOT_CONCRETE = Temperature(90.0, "F")


@dataclass(frozen=True, slots=True)
class HaulLimits:
    """The two limits that apply to one particular load."""

    time_limit: timedelta | None
    revolution_limit: int
    basis: str

    @property
    def time_is_waived(self) -> bool:
        """True when the purchaser lifted the clock."""
        return self.time_limit is None

    def describe(self) -> str:
        """One line for a ticket audit."""
        clock = (
            "waived"
            if self.time_limit is None
            else f"{int(self.time_limit.total_seconds() // 60)} min"
        )
        return f"{clock}, {self.revolution_limit} revolutions ({self.basis})"


def haul_limits(
    *,
    has_retarder: bool = False,
    concrete_temperature: Temperature | None = None,
    time_waived: bool = False,
) -> HaulLimits:
    """Work out the limits for a load from what is known about it.

    Hot weather beats a retarder. A stabilised load in ninety five degree
    concrete is still a load that is going to stiffen faster than the admixture
    can hold it, and the shorter clock is the one that applies.
    """
    if time_waived:
        return HaulLimits(None, REVOLUTION_LIMIT, "time limit waived by the purchaser")
    if concrete_temperature is not None and concrete_temperature > HOT_CONCRETE:
        return HaulLimits(HOT_WEATHER_TIME_LIMIT, REVOLUTION_LIMIT, "hot weather")
    if has_retarder:
        return HaulLimits(RETARDED_TIME_LIMIT, REVOLUTION_LIMIT, "retarded mixture")
    return HaulLimits(BASE_TIME_LIMIT, REVOLUTION_LIMIT, "standard")


@dataclass(frozen=True, slots=True)
class HaulVerdict:
    """One load's haul against the limits that applied to it."""

    batched_at: datetime
    discharged_at: datetime
    revolutions: int
    limits: HaulLimits

    @property
    def elapsed(self) -> timedelta:
        """How long the load was on the truck."""
        return self.discharged_at - self.batched_at

    @property
    def elapsed_minutes(self) -> float:
        """The same, in minutes."""
        return self.elapsed.total_seconds() / 60.0

    @property
    def over_time(self) -> bool:
        """True when the clock ran out before discharge finished."""
        if self.limits.time_limit is None:
            return False
        return self.elapsed > self.limits.time_limit

    @property
    def over_revolutions(self) -> bool:
        """True when the drum turned more than the limit."""
        return self.revolutions > self.limits.revolution_limit

    @property
    def conforms(self) -> bool:
        """True when neither limit was passed."""
        return not (self.over_time or self.over_revolutions)

    @property
    def reasons(self) -> tuple[str, ...]:
        """Which limits were passed, if any."""
        found: list[str] = []
        if self.over_time and self.limits.time_limit is not None:
            allowed = int(self.limits.time_limit.total_seconds() // 60)
            found.append(
                f"discharged {self.elapsed_minutes:.0f} minutes after batching, "
                f"the limit is {allowed}"
            )
        if self.over_revolutions:
            found.append(
                f"drum turned {self.revolutions} times, the limit is "
                f"{self.limits.revolution_limit}"
            )
        return tuple(found)

    def describe(self) -> str:
        """One line for a ticket audit."""
        if self.conforms:
            return (
                f"discharged in {self.elapsed_minutes:.0f} minutes and "
                f"{self.revolutions} revolutions, inside {self.limits.describe()}"
            )
        return "; ".join(self.reasons)


def judge_haul(
    batched_at: datetime,
    discharged_at: datetime,
    revolutions: int,
    limits: HaulLimits | None = None,
) -> HaulVerdict:
    """Judge one load's haul, using the standard limits unless told otherwise."""
    if discharged_at < batched_at:
        raise ValidationError(
            "a load cannot be discharged before it was batched", field="discharged_at"
        )
    if revolutions < 0:
        raise ValidationError("a revolution count cannot be negative", field="revolutions")
    return HaulVerdict(batched_at, discharged_at, revolutions, limits or haul_limits())
