"""Trucks, and the two capacities a drum has.

A truck mixer's drum is rated twice over. It may carry concrete up to about
sixty three percent of the drum's gross volume if it is doing the mixing, and
up to eighty percent if the concrete arrives already mixed and the drum is only
agitating it. The same truck therefore holds two different load sizes depending
on what the plant does, and a central mix plant that sizes its loads off the
mixing rating is leaving a fifth of every truck empty.

Overloading past either rating is not a paperwork problem. The concrete at the
back of an overfull drum does not get turned over, and the load comes out
unmixed with the last yard visibly different from the first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.percent import Percent
from slumpcone.plant.plant import MixingMethod
from slumpcone.units.quantity import Quantity

MIXING_CAPACITY = Percent(63.0)
AGITATING_CAPACITY = Percent(80.0)

# How often a mixer has to prove it still mixes uniformly.
UNIFORMITY_TEST_DAYS = 365


@dataclass(frozen=True, slots=True)
class Truck:
    """One truck mixer, by drum size and last uniformity test."""

    code: str
    drum_volume: Quantity
    fleet: str | None = None
    last_uniformity_test: date | None = None
    uniformity_test_days: int = UNIFORMITY_TEST_DAYS
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="truck_code"))
        if self.fleet is not None:
            object.__setattr__(self, "fleet", normalize_name(self.fleet, field="fleet"))
        if self.drum_volume.dimension.value != "volume":
            raise ValidationError("a drum volume is a volume", field="drum_volume")
        if self.drum_volume.value <= 0.0:
            raise ValidationError("a drum volume has to be positive", field="drum_volume")
        if self.uniformity_test_days <= 0:
            raise ValidationError(
                "a uniformity test interval has to be positive", field="uniformity_test_days"
            )

    @property
    def mixing_capacity(self) -> Quantity:
        """The most this truck may carry when it does the mixing."""
        return self.drum_volume * MIXING_CAPACITY.fraction

    @property
    def agitating_capacity(self) -> Quantity:
        """The most this truck may carry when the plant did the mixing."""
        return self.drum_volume * AGITATING_CAPACITY.fraction

    def capacity_for(self, method: MixingMethod) -> Quantity:
        """The rating that applies for a given mixing method."""
        if method.mixes_in_the_drum:
            return self.mixing_capacity
        return self.agitating_capacity

    def can_carry(self, volume: Quantity, method: MixingMethod) -> bool:
        """True when a load of that size fits the applicable rating."""
        if volume.dimension.value != "volume":
            raise ValidationError("a load size is a volume", field="volume")
        return volume <= self.capacity_for(method)

    def require_capacity(self, volume: Quantity, method: MixingMethod) -> None:
        """Refuse a load the drum is not rated to carry."""
        if not self.can_carry(volume, method):
            rating = self.capacity_for(method)
            raise RuleViolationError(
                "TRUCK_OVERLOADED",
                f"{self.code} is rated {rating.format(2)} {method} and the load is "
                f"{volume.format(2)}",
            )

    @property
    def uniformity_due(self) -> date | None:
        """When the mixer next has to prove it mixes, if it ever has."""
        if self.last_uniformity_test is None:
            return None
        return self.last_uniformity_test + timedelta(days=self.uniformity_test_days)

    def uniformity_is_current(self, on: date) -> bool:
        """True when the mixer's uniformity test still covers ``on``."""
        due = self.uniformity_due
        return due is not None and on <= due

    def blocking_reasons(self, on: date) -> tuple[str, ...]:
        """Everything stopping this truck carrying concrete on ``on``."""
        if self.last_uniformity_test is None:
            return ("no mixer uniformity test on file",)
        if not self.uniformity_is_current(on):
            due = self.uniformity_due
            assert due is not None
            return (f"mixer uniformity test lapsed {due.isoformat()}",)
        return ()

    def describe(self) -> str:
        """One line for a fleet listing."""
        fleet = f"  {self.fleet}" if self.fleet else ""
        return (
            f"{self.code}{fleet}  drum {self.drum_volume.format(1)}  "
            f"mixing {self.mixing_capacity.format(2)}  "
            f"agitating {self.agitating_capacity.format(2)}"
        )
