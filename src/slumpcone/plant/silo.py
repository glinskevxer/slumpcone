"""Silos, bins and tanks, and what is in them right now.

A storage vessel is tied to exactly one material at a time. Switching a silo
from one cement to another is a real operation with a real cost, because
whatever is left in the cone blends into the first few loads of the new
product, so the switch is recorded rather than edited in place.

Levels here are a running figure kept by drawdown, not a measured one. A plant
that trusts them without a physical check every so often will find the two have
drifted apart, which is why the reconciliation is a first class operation and
not a correction typed over the top.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


class SiloState(Enum):
    """How much room is left, in the terms the plant talks about."""

    EMPTY = "empty"
    LOW = "low"
    WORKING = "working"
    FULL = "full"

    def __str__(self) -> str:
        return self.value

    @property
    def needs_a_delivery(self) -> bool:
        """True when the plant should be ordering more."""
        return self in {SiloState.EMPTY, SiloState.LOW}


@dataclass(frozen=True, slots=True)
class Silo:
    """One vessel, its material and its running level."""

    code: str
    name: str
    material_code: str
    capacity: Quantity
    level: Quantity
    low_level: Quantity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="silo_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="silo_name"))
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        for name, amount in (("capacity", self.capacity), ("level", self.level)):
            if amount.dimension.value != "mass":
                raise ValidationError(f"a silo {name} is a mass", field=name)
        if self.capacity.value <= 0.0:
            raise ValidationError("a silo capacity has to be positive", field="capacity")
        if self.level.value < 0.0:
            raise ValidationError("a silo level cannot be negative", field="level")
        if self.level > self.capacity:
            raise ValidationError(
                f"level {self.level} is above the {self.capacity} capacity", field="level"
            )
        if self.low_level is not None:
            if self.low_level.dimension.value != "mass":
                raise ValidationError("a low level mark is a mass", field="low_level")
            if self.low_level.value < 0.0:
                raise ValidationError("a low level mark cannot be negative", field="low_level")
            if self.low_level > self.capacity:
                raise ValidationError(
                    "a low level mark cannot be above the capacity", field="low_level"
                )

    @property
    def headroom(self) -> Quantity:
        """How much more this vessel will take."""
        return self.capacity - self.level

    @property
    def fill(self) -> Percent:
        """How full it is."""
        return Percent.from_fraction(self.level.base_value / self.capacity.base_value)

    @property
    def state(self) -> SiloState:
        """Where the level sits against the marks."""
        if self.level.is_zero():
            return SiloState.EMPTY
        if self.low_level is not None and self.level <= self.low_level:
            return SiloState.LOW
        if self.headroom.is_zero():
            return SiloState.FULL
        return SiloState.WORKING

    def can_draw(self, amount: Quantity) -> bool:
        """True when there is enough in the vessel to draw ``amount``."""
        if amount.dimension.value != "mass":
            raise ValidationError("a drawdown is a mass", field="amount")
        return amount <= self.level

    def draw(self, amount: Quantity) -> Silo:
        """Take ``amount`` out, refusing to go below empty.

        Refusing rather than clamping is deliberate. A plant that draws more
        than it has is either mis-assigned or its level is wrong, and both need
        somebody to look rather than a silently floored number.
        """
        if amount.dimension.value != "mass":
            raise ValidationError("a drawdown is a mass", field="amount")
        if amount.value < 0.0:
            raise ValidationError("a drawdown cannot be negative", field="amount")
        if not self.can_draw(amount):
            raise RuleViolationError(
                "SILO_SHORT",
                f"{self.code} holds {self.level.format(0)} and the batch wants "
                f"{amount.format(0)}",
            )
        return replace(self, level=self.level - amount)

    def receive(self, amount: Quantity) -> Silo:
        """Put ``amount`` in, refusing to overfill."""
        if amount.dimension.value != "mass":
            raise ValidationError("a receipt is a mass", field="amount")
        if amount.value < 0.0:
            raise ValidationError("a receipt cannot be negative", field="amount")
        if amount > self.headroom:
            raise RuleViolationError(
                "SILO_OVERFILL",
                f"{self.code} has {self.headroom.format(0)} of headroom and the "
                f"delivery is {amount.format(0)}",
            )
        return replace(self, level=self.level + amount)

    def reconcile(self, measured: Quantity) -> tuple[Silo, Quantity]:
        """Set the level to a measured figure and report the correction."""
        if measured.dimension.value != "mass":
            raise ValidationError("a measured level is a mass", field="measured")
        if measured.value < 0.0:
            raise ValidationError("a measured level cannot be negative", field="measured")
        if measured > self.capacity:
            raise ValidationError(
                "a measured level cannot be above the capacity", field="measured"
            )
        return replace(self, level=measured), measured - self.level

    def assign(self, material_code: str) -> Silo:
        """Switch the vessel to another material, which empties it."""
        return replace(
            self,
            material_code=normalize_code(material_code, field="material_code"),
            level=Quantity.zero(self.level.unit),
        )

    def describe(self) -> str:
        """One line for a listing."""
        return (
            f"{self.code}  {self.name}  {self.material_code}  "
            f"{self.level.format(0)} of {self.capacity.format(0)}  "
            f"{self.fill.format(0)}  {self.state}"
        )
