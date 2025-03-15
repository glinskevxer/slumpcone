"""The charges that go on a ticket besides the concrete.

Ready-mix is not sold by the yard alone. A three yard load costs nearly as much
to make and deliver as a nine yard one, so it carries a short load charge. A
truck held on a job past its unloading allowance carries standby, because that
truck is not available to anybody else. And a load ordered for a Saturday, or
in February, costs the plant more to produce than the same load on a Tuesday in
June.

Every one of these is a plant setting rather than a fact about concrete, so the
schedule is data. What is not negotiable is the *shape*: a short load charge is
per load, standby is per minute past an allowance, and a fuel surcharge is a
share of the concrete value. Getting a basis wrong is how a plant bills three
yards of standby.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.money import Money, total
from slumpcone.percent import Percent
from slumpcone.units.checks import require_volume
from slumpcone.units.quantity import Quantity

# Loads at or above this are full loads and carry no short load charge.
DEFAULT_SMALL_LOAD = Quantity(5.0, "yd3")

# The unloading allowance: a flat grace plus so many minutes per unit volume.
DEFAULT_STANDBY_GRACE_MINUTES = 5.0
DEFAULT_MINUTES_PER_UNIT = 5.0


class ChargeBasis(Enum):
    """What a charge is reckoned against."""

    PER_LOAD = "per load"
    PER_UNIT = "per unit"
    PER_MINUTE = "per minute"
    PERCENT_OF_CONCRETE = "percent of concrete"

    def __str__(self) -> str:
        return self.value


class ChargeKind(Enum):
    """The charges a ticket can carry."""

    SHORT_LOAD = "short load"
    STANDBY = "standby"
    AFTER_HOURS = "after hours"
    WEEKEND = "weekend"
    FUEL = "fuel"
    WINTER_HEAT = "winter heat"
    COLD_WEATHER_ADMIXTURE = "cold weather admixture"
    WASHOUT = "washout"
    RETURNED_CONCRETE = "returned concrete"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> ChargeKind:
        """Read a charge kind off a schedule."""
        key = text.strip().lower().replace("_", " ")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown charge kind {text!r}", field="kind")

    @property
    def natural_basis(self) -> ChargeBasis:
        """The basis this charge is nearly always written on."""
        table = {
            ChargeKind.SHORT_LOAD: ChargeBasis.PER_LOAD,
            ChargeKind.STANDBY: ChargeBasis.PER_MINUTE,
            ChargeKind.AFTER_HOURS: ChargeBasis.PER_LOAD,
            ChargeKind.WEEKEND: ChargeBasis.PER_LOAD,
            ChargeKind.FUEL: ChargeBasis.PERCENT_OF_CONCRETE,
            ChargeKind.WINTER_HEAT: ChargeBasis.PER_UNIT,
            ChargeKind.COLD_WEATHER_ADMIXTURE: ChargeBasis.PER_UNIT,
            ChargeKind.WASHOUT: ChargeBasis.PER_LOAD,
            ChargeKind.RETURNED_CONCRETE: ChargeBasis.PER_UNIT,
        }
        return table[self]


@dataclass(frozen=True, slots=True)
class ChargeRule:
    """One line of a plant's charge schedule."""

    kind: ChargeKind
    rate: Money
    basis: ChargeBasis | None = None

    def __post_init__(self) -> None:
        if self.basis is None:
            object.__setattr__(self, "basis", self.kind.natural_basis)
        if self.rate.amount < 0:
            raise ValidationError("a charge rate cannot be negative", field="rate")

    @property
    def reckoned_on(self) -> ChargeBasis:
        """The basis this rule is reckoned on."""
        assert self.basis is not None
        return self.basis

    def apply(self, quantity: float, concrete_value: Money) -> Money:
        """What this rule comes to for a given quantity."""
        if quantity < 0.0:
            raise ValidationError("a charge quantity cannot be negative", field="quantity")
        if self.reckoned_on is ChargeBasis.PERCENT_OF_CONCRETE:
            return concrete_value * (self.rate.amount / 100)
        if self.reckoned_on is ChargeBasis.PER_LOAD:
            return self.rate if quantity > 0.0 else Money.zero(self.rate.currency)
        return self.rate * quantity

    def describe(self) -> str:
        """One line for a schedule listing."""
        if self.reckoned_on is ChargeBasis.PERCENT_OF_CONCRETE:
            return f"{self.kind}  {self.rate.amount:g}% of the concrete"
        return f"{self.kind}  {self.rate} {self.reckoned_on}"


@dataclass(frozen=True, slots=True)
class AppliedCharge:
    """One charge as it lands on a ticket."""

    kind: ChargeKind
    quantity: float
    amount: Money
    reason: str = ""

    def describe(self) -> str:
        """One line for a ticket."""
        tail = f"  ({self.reason})" if self.reason else ""
        return f"{self.kind}  {self.amount}{tail}"


class ChargeSchedule:
    """A plant's charge schedule."""

    def __init__(
        self,
        rules: Iterable[ChargeRule] = (),
        *,
        small_load_below: Quantity = DEFAULT_SMALL_LOAD,
        standby_grace_minutes: float = DEFAULT_STANDBY_GRACE_MINUTES,
        minutes_per_unit: float = DEFAULT_MINUTES_PER_UNIT,
    ) -> None:
        self._rules: dict[ChargeKind, ChargeRule] = {rule.kind: rule for rule in rules}
        require_volume(small_load_below, "a short load threshold", field="small_load_below")
        if standby_grace_minutes < 0.0 or minutes_per_unit < 0.0:
            raise ValidationError(
                "an unloading allowance cannot be negative", field="standby_grace_minutes"
            )
        self.small_load_below = small_load_below
        self.standby_grace_minutes = standby_grace_minutes
        self.minutes_per_unit = minutes_per_unit

    def __len__(self) -> int:
        return len(self._rules)

    def add(self, rule: ChargeRule) -> ChargeRule:
        """Add or replace one rule."""
        self._rules[rule.kind] = rule
        return rule

    def rule(self, kind: ChargeKind) -> ChargeRule:
        """One rule by kind."""
        found = self._rules.get(kind)
        if found is None:
            raise NotFoundError("charge rule", str(kind))
        return found

    def has(self, kind: ChargeKind) -> bool:
        """True when the schedule carries a rule for a kind."""
        return kind in self._rules

    def kinds(self) -> tuple[ChargeKind, ...]:
        """Every kind the schedule carries, in enum order."""
        return tuple(kind for kind in ChargeKind if kind in self._rules)

    def unloading_allowance(self, volume: Quantity) -> float:
        """Free unloading minutes for a load of that size."""
        require_volume(volume, "a load size", field="volume")
        return self.standby_grace_minutes + self.minutes_per_unit * volume.to("yd3").value

    def standby_minutes(self, volume: Quantity, on_site_minutes: float) -> float:
        """Minutes past the allowance, floored at nothing."""
        if on_site_minutes < 0.0:
            raise ValidationError("time on site cannot be negative", field="on_site_minutes")
        return max(on_site_minutes - self.unloading_allowance(volume), 0.0)

    def charges_for(
        self,
        volume: Quantity,
        concrete_value: Money,
        *,
        on_site_minutes: float | None = None,
        after_hours: bool = False,
        weekend: bool = False,
        returned: Quantity | None = None,
        winter: bool = False,
    ) -> tuple[AppliedCharge, ...]:
        """Every charge this load earns, in schedule order."""
        require_volume(volume, "a load size", field="volume")
        applied: list[AppliedCharge] = []
        if self.has(ChargeKind.SHORT_LOAD) and volume < self.small_load_below:
            rule = self.rule(ChargeKind.SHORT_LOAD)
            applied.append(
                AppliedCharge(
                    rule.kind,
                    1.0,
                    rule.apply(1.0, concrete_value),
                    f"{volume.format(1)} is under {self.small_load_below.format(1)}",
                )
            )
        if self.has(ChargeKind.STANDBY) and on_site_minutes is not None:
            minutes = self.standby_minutes(volume, on_site_minutes)
            if minutes > 0.0:
                rule = self.rule(ChargeKind.STANDBY)
                applied.append(
                    AppliedCharge(
                        rule.kind,
                        minutes,
                        rule.apply(minutes, concrete_value),
                        f"{minutes:.0f} minutes past a "
                        f"{self.unloading_allowance(volume):.0f} minute allowance",
                    )
                )
        for kind, wanted in (
            (ChargeKind.AFTER_HOURS, after_hours),
            (ChargeKind.WEEKEND, weekend),
        ):
            if wanted and self.has(kind):
                rule = self.rule(kind)
                applied.append(AppliedCharge(kind, 1.0, rule.apply(1.0, concrete_value)))
        for kind in (ChargeKind.WINTER_HEAT, ChargeKind.COLD_WEATHER_ADMIXTURE):
            if winter and self.has(kind):
                rule = self.rule(kind)
                units = volume.to("yd3").value
                applied.append(AppliedCharge(kind, units, rule.apply(units, concrete_value)))
        if self.has(ChargeKind.RETURNED_CONCRETE) and returned is not None:
            units = returned.to("yd3").value
            if units > 0.0:
                rule = self.rule(ChargeKind.RETURNED_CONCRETE)
                applied.append(
                    AppliedCharge(
                        rule.kind,
                        units,
                        rule.apply(units, concrete_value),
                        f"{returned.format(2)} came back",
                    )
                )
        if self.has(ChargeKind.FUEL):
            rule = self.rule(ChargeKind.FUEL)
            applied.append(AppliedCharge(rule.kind, 1.0, rule.apply(1.0, concrete_value)))
        return tuple(applied)


def charges_total(charges: Iterable[AppliedCharge], currency: str = "USD") -> Money:
    """Everything a set of charges comes to."""
    return total([charge.amount for charge in charges], currency)


def share_of_load(charges: Iterable[AppliedCharge], concrete_value: Money) -> Percent:
    """The charges as a share of the concrete itself."""
    if concrete_value.is_zero():
        return Percent(0.0)
    return Percent.from_fraction(
        charges_total(charges, concrete_value.currency).ratio_to(concrete_value)
    )
