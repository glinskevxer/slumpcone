"""Batching scales, their capacity and their calibration.

Two things about a scale reach the rest of the register. Its capacity, because
the weighing tolerance C94 allows is partly a percentage of capacity rather
than of the load, so a big scale weighing a small charge is allowed a wider
miss than the same charge on a small scale. And its calibration date, because a
scale out of calibration cannot produce a defensible batch record at all.

Capacity is also the reason a plant does not put a fifty pound admixture charge
on a twelve thousand pound aggregate scale. The tolerance would be sixty
pounds, which is larger than the charge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.checks import require_mass, require_positive
from slumpcone.units.quantity import Quantity

# How often a batching scale is verified. Plant certification schemes and most
# state highway specifications both land on six months.
DEFAULT_CALIBRATION_DAYS = 182

# A scale is reported as due before it actually lapses, so a verification can be
# booked without stopping production.
CALIBRATION_WARNING_DAYS = 30


class ScaleState(Enum):
    """Where a scale sits relative to its calibration interval."""

    CURRENT = "current"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"

    def __str__(self) -> str:
        return self.value

    @property
    def blocks_batching(self) -> bool:
        """True when a batch weighed on this scale is not defensible."""
        return self is ScaleState.OVERDUE


@dataclass(frozen=True, slots=True)
class Scale:
    """One weighing device on the plant, with what it may weigh."""

    code: str
    name: str
    capacity: Quantity
    graduation: Quantity
    weighs: tuple[MaterialClass, ...]
    last_calibrated: date
    calibration_days: int = DEFAULT_CALIBRATION_DAYS

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="scale_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="scale_name"))
        require_positive(
            require_mass(self.capacity, "a scale capacity", field="capacity"),
            "a scale capacity",
            field="capacity",
        )
        require_positive(
            require_mass(self.graduation, "a scale graduation", field="graduation"),
            "a scale graduation",
            field="graduation",
        )
        if self.graduation >= self.capacity:
            raise ValidationError(
                "a scale graduation has to be smaller than its capacity", field="graduation"
            )
        if not self.weighs:
            raise ValidationError("a scale has to weigh something", field="weighs")
        if self.calibration_days <= 0:
            raise ValidationError(
                "a calibration interval has to be positive", field="calibration_days"
            )

    @property
    def calibration_due(self) -> date:
        """The last day a batch may be weighed on this scale."""
        return self.last_calibrated + timedelta(days=self.calibration_days)

    def state(self, on: date, *, warning_days: int = CALIBRATION_WARNING_DAYS) -> ScaleState:
        """Where the calibration sits on ``on``."""
        remaining = (self.calibration_due - on).days
        if remaining < 0:
            return ScaleState.OVERDUE
        if remaining <= warning_days:
            return ScaleState.DUE_SOON
        return ScaleState.CURRENT

    def is_current(self, on: date) -> bool:
        """True when the calibration covers ``on``."""
        return not self.state(on).blocks_batching

    def days_until_due(self, on: date) -> int:
        """Days left on the calibration, negative once it has lapsed."""
        return (self.calibration_due - on).days

    def can_weigh(self, material_class: MaterialClass) -> bool:
        """True when this scale is assigned to weigh that class of material."""
        return material_class in self.weighs

    def smallest_defensible_charge(self, *, graduations: int = 20) -> Quantity:
        """The lightest charge worth weighing on this scale.

        A charge that only spans a few graduations cannot be weighed to any
        useful accuracy. Twenty graduations is the rule of thumb the scale
        technicians use and it is what the plant should be sized against.
        """
        if graduations <= 0:
            raise ValidationError("graduations has to be positive", field="graduations")
        return self.graduation * graduations

    def describe(self, on: date) -> str:
        """One line for a listing."""
        classes = ", ".join(str(k) for k in self.weighs)
        return (
            f"{self.code}  {self.name}  {self.capacity.format(0)} capacity  "
            f"[{classes}]  {self.state(on)} until {self.calibration_due.isoformat()}"
        )
