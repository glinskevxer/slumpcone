"""The tests a technician runs on the load before it goes in the forms.

Five of them, and they are not interchangeable. Slump and air are the two that
can reject a load. Temperature is a limit in hot and cold weather and a piece
of context the rest of the year. Unit weight is what the yield check runs on.

The point of discharge matters and is recorded, because a sample taken off the
front of the load and a sample taken after two yards have gone in the forms are
not the same concrete, and C172 says which one counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_ticket_number
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from slumpcone.units.temperature import Temperature


class FreshTestKind(Enum):
    """Which test was run, and what standard it was run to."""

    SLUMP = "slump"
    AIR_PRESSURE = "air_pressure"
    AIR_VOLUMETRIC = "air_volumetric"
    TEMPERATURE = "temperature"
    UNIT_WEIGHT = "unit_weight"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> FreshTestKind:
        """Read a test kind off a field sheet."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {"air": "air_pressure", "density": "unit_weight", "temp": "temperature"}
        key = aliases.get(key, key)
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown fresh test {text!r}", field="test_kind")

    @property
    def standard(self) -> str:
        """The ASTM method this test is run to."""
        table = {
            FreshTestKind.SLUMP: "ASTM C143",
            FreshTestKind.AIR_PRESSURE: "ASTM C231",
            FreshTestKind.AIR_VOLUMETRIC: "ASTM C173",
            FreshTestKind.TEMPERATURE: "ASTM C1064",
            FreshTestKind.UNIT_WEIGHT: "ASTM C138",
        }
        return table[self]

    @property
    def is_air(self) -> bool:
        """True for either of the two air methods."""
        return self in {FreshTestKind.AIR_PRESSURE, FreshTestKind.AIR_VOLUMETRIC}

    @property
    def can_reject_a_load(self) -> bool:
        """True when a failing result on its own is grounds to send it back."""
        return self is FreshTestKind.SLUMP or self.is_air

    @property
    def suits_lightweight(self) -> bool:
        """True when the method works on a lightweight or porous aggregate.

        The pressure meter reads the air in the aggregate's own pores as if it
        were air in the paste, so a lightweight mixture has to be tested
        volumetrically. Plants that miss this reject perfectly good concrete.
        """
        return self is not FreshTestKind.AIR_PRESSURE


@dataclass(frozen=True, slots=True)
class FreshTest:
    """One test result, tied to the ticket the sample came off."""

    ticket_number: str
    kind: FreshTestKind
    taken_at: datetime
    slump: Quantity | None = None
    air: Percent | None = None
    temperature: Temperature | None = None
    unit_weight: MassPerVolume | None = None
    discharged_before_sample: Quantity | None = None
    technician: str | None = None
    is_retest: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticket_number", normalize_ticket_number(self.ticket_number))
        if self.technician is not None:
            object.__setattr__(
                self, "technician", normalize_code(self.technician, field="technician")
            )
        self._check_value_present()
        self._check_ranges()

    def _check_value_present(self) -> None:
        expected = {
            FreshTestKind.SLUMP: self.slump,
            FreshTestKind.AIR_PRESSURE: self.air,
            FreshTestKind.AIR_VOLUMETRIC: self.air,
            FreshTestKind.TEMPERATURE: self.temperature,
            FreshTestKind.UNIT_WEIGHT: self.unit_weight,
        }
        if expected[self.kind] is None:
            raise ValidationError(f"a {self.kind} test needs a reading", field=str(self.kind))

    def _check_ranges(self) -> None:
        if self.slump is not None:
            if self.slump.dimension.value != "length":
                raise ValidationError("a slump is a length", field="slump")
            if self.slump.value < 0.0:
                raise ValidationError("a slump cannot be negative", field="slump")
            if self.slump.to("in").value > 12.0:
                raise ValidationError(
                    "a slump above twelve inches is a collapsed cone, not a reading",
                    field="slump",
                )
        if self.air is not None and not 0.0 <= self.air.value <= 25.0:
            raise ValidationError(f"an air content of {self.air} is not a reading", field="air")
        if self.unit_weight is not None and self.unit_weight.value <= 0.0:
            raise ValidationError("a unit weight has to be positive", field="unit_weight")
        if self.discharged_before_sample is not None:
            if self.discharged_before_sample.dimension.value != "volume":
                raise ValidationError(
                    "the discharge before a sample is a volume",
                    field="discharged_before_sample",
                )
            if self.discharged_before_sample.value < 0.0:
                raise ValidationError(
                    "the discharge before a sample cannot be negative",
                    field="discharged_before_sample",
                )

    @property
    def value_text(self) -> str:
        """The reading, formatted the way its own method reports it."""
        if self.kind is FreshTestKind.SLUMP and self.slump is not None:
            return self.slump.format(2)
        if self.kind.is_air and self.air is not None:
            return self.air.format(1)
        if self.kind is FreshTestKind.TEMPERATURE and self.temperature is not None:
            return str(self.temperature)
        if self.kind is FreshTestKind.UNIT_WEIGHT and self.unit_weight is not None:
            return self.unit_weight.format(1)
        return "-"

    def describe(self) -> str:
        """One line for a field log."""
        tail = " retest" if self.is_retest else ""
        return (
            f"{self.ticket_number}  {self.kind}  {self.value_text}  "
            f"{self.taken_at.isoformat(sep=' ', timespec='minutes')}{tail}"
        )
