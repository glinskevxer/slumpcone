"""The plant record.

A plant is the thing a ticket is written by, and almost everything about how a
batch is judged reads off it: which unit system the numbers are in, which scale
weighed each material, what mixing method was used and therefore how the load
is allowed to be handled afterwards.

Mixing method is the one that surprises people. A central mixed load has
already been mixed before it goes in the truck, so the revolution count that
governs a truck mixed load does not apply to it in the same way, and the
discharge clock starts at a different point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from slumpcone.errors import NotFoundError, RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.materials.kinds import MaterialClass, WaterSource
from slumpcone.plant.scale import Scale
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


class MixingMethod(Enum):
    """How the concrete is mixed before it leaves the plant."""

    CENTRAL_MIXED = "central_mixed"
    SHRINK_MIXED = "shrink_mixed"
    TRUCK_MIXED = "truck_mixed"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> MixingMethod:
        """Read a mixing method off a plant configuration."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown mixing method {text!r}", field="mixing_method")

    @property
    def mixes_in_the_drum(self) -> bool:
        """True when mixing happens in the truck and revolutions are counted."""
        return self is not MixingMethod.CENTRAL_MIXED

    @property
    def required_mixing_revolutions(self) -> int:
        """Revolutions at mixing speed before the load is considered mixed."""
        if self is MixingMethod.TRUCK_MIXED:
            return 70
        if self is MixingMethod.SHRINK_MIXED:
            return 30
        return 0


@dataclass(frozen=True, slots=True)
class Plant:
    """One batch plant, configured."""

    code: str
    name: str
    unit_system: UnitSystem = UnitSystem.CUSTOMARY
    mixing_method: MixingMethod = MixingMethod.TRUCK_MIXED
    water_source: WaterSource = WaterSource.POTABLE
    scales: tuple[Scale, ...] = ()
    max_load: Quantity | None = None
    certification_expires: date | None = None
    location: str | None = None
    notes: str = field(default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="plant_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="plant_name"))
        if self.location is not None:
            object.__setattr__(
                self, "location", normalize_name(self.location, field="location")
            )
        seen: set[str] = set()
        for scale in self.scales:
            if scale.code in seen:
                raise ValidationError(f"scale {scale.code} appears twice", field="scales")
            seen.add(scale.code)
        if self.max_load is not None:
            if self.max_load.dimension.value != "volume":
                raise ValidationError("a load size is a volume", field="max_load")
            if self.max_load.value <= 0.0:
                raise ValidationError("a load size has to be positive", field="max_load")

    @property
    def scale_codes(self) -> tuple[str, ...]:
        """Every scale code on the plant, sorted."""
        return tuple(sorted(s.code for s in self.scales))

    def scale(self, code: str) -> Scale:
        """The scale filed under ``code``."""
        key = normalize_code(code, field="scale_code")
        for candidate in self.scales:
            if candidate.code == key:
                return candidate
        raise NotFoundError("scale", key)

    def scale_for(self, material_class: MaterialClass) -> Scale:
        """The scale that weighs a class of material.

        When more than one scale is assigned the smallest capacity wins,
        because that is the one the plant would use and the one that gives the
        tightest tolerance.
        """
        candidates = [s for s in self.scales if s.can_weigh(material_class)]
        if not candidates:
            raise NotFoundError("scale weighing", str(material_class))
        return min(candidates, key=lambda s: s.capacity.base_value)

    def has_scale_for(self, material_class: MaterialClass) -> bool:
        """True when some scale on the plant weighs that class."""
        return any(s.can_weigh(material_class) for s in self.scales)

    def overdue_scales(self, on: date) -> tuple[Scale, ...]:
        """Every scale whose calibration has lapsed on ``on``."""
        return tuple(s for s in self.scales if not s.is_current(on))

    def blocking_reasons(self, on: date) -> tuple[str, ...]:
        """Everything stopping this plant from batching on ``on``."""
        reasons: list[str] = []
        if self.certification_expires is not None and on > self.certification_expires:
            reasons.append(
                f"plant certification expired {self.certification_expires.isoformat()}"
            )
        for scale in self.overdue_scales(on):
            reasons.append(
                f"scale {scale.code} calibration lapsed {scale.calibration_due.isoformat()}"
            )
        return tuple(reasons)

    def is_operable(self, on: date) -> bool:
        """True when nothing stops this plant batching on ``on``."""
        return not self.blocking_reasons(on)

    def require_operable(self, on: date) -> None:
        """Refuse the batch and say why, when the plant cannot run."""
        reasons = self.blocking_reasons(on)
        if reasons:
            raise RuleViolationError("PLANT_NOT_OPERABLE", "; ".join(reasons))

    def describe(self) -> str:
        """One line for a listing."""
        where = f" at {self.location}" if self.location else ""
        return (
            f"{self.code}  {self.name}{where}  {self.unit_system}  "
            f"{self.mixing_method}  {len(self.scales)} scales"
        )
