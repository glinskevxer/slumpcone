"""Wash water, reclaimed solids, and what a returned load can become.

Two waste streams come back through the gate and both can lawfully go back into
concrete, under rules that are easy to state and easy to get wrong.

Wash water is what comes off the drum and the chutes. C1602 lets it be used as
mixing water if it clears optional chemical limits and, critically, if the total
solids are low enough. Solids matter because they are cement that has already
started to hydrate: they take up water, they take up volume, and above about
fifty thousand parts per million they start costing strength. The specific
gravity of the water is how a plant measures the solids without a laboratory,
because they are proportional and a hydrometer costs nothing.

Returned concrete is a whole load that came back. C1798 lets a plant hold it and
put it in a later load, up to a limit expressed as a share of the new load, and
the clock that matters is the age of the returned material, not how long it has
been in the drum. A load that sat on the yard for four hours before anybody
decided to reuse it is four hours old.

The two share one rule and it is the one that costs money: **whatever goes back
in has to be counted as water and as cement in the new load's proportions.**
Treating reclaimed water as if it were potable makes every mixture that uses it
wetter than its design says, which is invisible until the breaks come back.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from slumpcone.errors import RuleViolationError
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# C1602 optional limit on total solids in mixing water, as parts per million.
SOLIDS_LIMIT_PPM = 50_000.0

# Water's specific gravity, which is the datum the hydrometer reading is against.
WATER_SPECIFIC_GRAVITY = 1.000

# Cement solids sit near this. Used to turn a specific gravity reading into a
# solids concentration, which is what C1602 states its limit in.
SOLIDS_SPECIFIC_GRAVITY = 2.20

# C1798 caps returned concrete in a new load at this share by volume unless the
# purchaser has agreed otherwise in writing.
RETURNED_SHARE_LIMIT = Percent(15.0)

# And it has to be young enough to still be workable and still gain strength.
RETURNED_AGE_LIMIT = timedelta(hours=2)


class WashWaterError(RuleViolationError):
    """A reuse that the standards do not allow."""


@dataclass(frozen=True, slots=True)
class WashWater:
    """A tank of water off the wash rack, with its measured density."""

    tank: str
    specific_gravity: float
    volume: Quantity

    def __post_init__(self) -> None:
        if self.specific_gravity < WATER_SPECIFIC_GRAVITY:
            raise WashWaterError(
                "WASH_WATER_LIGHTER_THAN_WATER",
                f"{self.tank} reads {self.specific_gravity}, lighter than water, "
                "which means the hydrometer is wrong rather than the water",
            )
        if self.volume.base_value < 0.0:
            raise WashWaterError(
                "WASH_WATER_NEGATIVE_VOLUME", "a tank cannot hold a negative volume"
            )

    @property
    def solids_ppm(self) -> float:
        """Total solids, in parts per million, from the density reading.

        A litre of the mixture weighs ``sg`` kilograms. Of that, the solids
        account for the excess over water, scaled by how much denser than water
        the solids are, which is where the 2.20 comes in.
        """
        excess = self.specific_gravity - WATER_SPECIFIC_GRAVITY
        if excess <= 0.0:
            return 0.0
        fraction = (
            excess
            * SOLIDS_SPECIFIC_GRAVITY
            / (SOLIDS_SPECIFIC_GRAVITY - WATER_SPECIFIC_GRAVITY)
        )
        return fraction * 1_000_000.0 / self.specific_gravity

    @property
    def solids_share(self) -> Percent:
        """Solids as a percentage of the mixture by mass."""
        return Percent(self.solids_ppm / 10_000.0)

    @property
    def meets_solids_limit(self) -> bool:
        """Whether C1602's optional solids limit is cleared."""
        return self.solids_ppm <= SOLIDS_LIMIT_PPM

    def water_in(self, drawn: Quantity) -> Quantity:
        """How much of a draw is actually water rather than solids."""
        if drawn.base_value > self.volume.base_value + 1e-9:
            raise WashWaterError(
                "WASH_WATER_OVERDRAWN",
                f"{self.tank} holds {self.volume.format(1)}, cannot draw {drawn.format(1)}",
            )
        return drawn * (1.0 - self.solids_share.fraction)

    def solids_in(self, drawn: Quantity) -> Quantity:
        """The rest of the draw, which is cement that has already reacted."""
        return drawn - self.water_in(drawn)

    def describe(self) -> str:
        """One line."""
        verdict = "usable" if self.meets_solids_limit else "over the solids limit"
        return (
            f"{self.tank}: sg {self.specific_gravity:.3f}, "
            f"{self.solids_ppm:,.0f} ppm solids, {verdict}"
        )


@dataclass(frozen=True, slots=True)
class ReturnedConcrete:
    """A load that came back, and how old it was when it did."""

    ticket_number: str
    mix_code: str
    volume: Quantity
    age_at_return: timedelta

    def __post_init__(self) -> None:
        if self.volume.base_value <= 0.0:
            raise WashWaterError(
                "RETURNED_NO_VOLUME", "returned concrete has to be a positive volume"
            )
        if self.age_at_return < timedelta(0):
            raise WashWaterError(
                "RETURNED_NEGATIVE_AGE", "a load cannot come back before it was batched"
            )

    def age_at(self, waited: timedelta) -> timedelta:
        """How old it is after sitting on the yard for a while longer."""
        return self.age_at_return + waited

    def is_usable(self, waited: timedelta = timedelta(0)) -> bool:
        """Whether it is still young enough to go into a new load."""
        return self.age_at(waited) <= RETURNED_AGE_LIMIT

    def most_into(self, new_load: Quantity, *, cap: Percent = RETURNED_SHARE_LIMIT) -> Quantity:
        """The largest amount of this that may go into a load of a given size."""
        allowed = new_load * cap.fraction
        return allowed if allowed.base_value <= self.volume.base_value else self.volume

    def describe(self) -> str:
        """One line."""
        minutes = self.age_at_return.total_seconds() / 60
        verdict = "usable" if self.is_usable() else "too old to reuse"
        return (
            f"{self.ticket_number}: {self.volume.format(1)} of {self.mix_code} back at "
            f"{minutes:.0f} min, {verdict}"
        )


def usable_tanks(tanks: Sequence[WashWater]) -> tuple[WashWater, ...]:
    """The tanks clean enough to batch from, cleanest first."""
    return tuple(
        sorted(
            (tank for tank in tanks if tank.meets_solids_limit),
            key=lambda tank: tank.solids_ppm,
        )
    )


def blend_into(
    returned: ReturnedConcrete,
    new_load: Quantity,
    *,
    waited: timedelta = timedelta(0),
    cap: Percent = RETURNED_SHARE_LIMIT,
) -> Quantity:
    """How much returned concrete may go into a new load, or nothing.

    Refusing returns zero rather than raising, because a dispatcher asking this
    of every load on the yard wants a number back for each of them, and the
    answer for most of them is none.
    """
    if not returned.is_usable(waited):
        return Quantity(0.0, new_load.unit)
    return returned.most_into(new_load, cap=cap)
