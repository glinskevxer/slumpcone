"""Water added at the job, and what it costs.

A load that arrives stiff can have water added once, on the job, before any
concrete is discharged. The addition is allowed only up to the design water
content, it has to be mixed in at mixing speed for at least thirty revolutions,
and the amount goes on the ticket.

Past the design water it is still physically possible and it still happens.
What changes is who owns the outcome: water added at the purchaser's direction
beyond what the mixture was designed for voids the producer's warranty on
strength, and the ticket has to say so. That is not a judgement about whether
the concrete will be fine. It is about who pays if it is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_ticket_number
from slumpcone.mixdesign.volumes import WATER_DENSITY
from slumpcone.units.quantity import Quantity

# Revolutions at mixing speed a jobsite addition has to be followed by.
MIXING_REVOLUTIONS_AFTER_WATER = 30


class RequestedBy(Enum):
    """Who asked for the water."""

    PRODUCER = "producer"
    PURCHASER = "purchaser"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> RequestedBy:
        """Read who asked off a ticket."""
        key = text.strip().lower()
        aliases = {"plant": "producer", "driver": "producer", "contractor": "purchaser"}
        key = aliases.get(key, key)
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown requester {text!r}", field="requested_by")


@dataclass(frozen=True, slots=True)
class WaterAddition:
    """One addition of water at the job."""

    ticket_number: str
    added_at: datetime
    amount: Quantity
    requested_by: RequestedBy = RequestedBy.PURCHASER
    revolutions_after: int = MIXING_REVOLUTIONS_AFTER_WATER
    discharged_before: Quantity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticket_number", normalize_ticket_number(self.ticket_number))
        if self.amount.dimension.value != "volume":
            raise ValidationError("added water is a volume", field="amount")
        if self.amount.value < 0.0:
            raise ValidationError("added water cannot be negative", field="amount")
        if self.revolutions_after < 0:
            raise ValidationError(
                "a revolution count cannot be negative", field="revolutions_after"
            )
        if self.discharged_before is not None:
            if self.discharged_before.dimension.value != "volume":
                raise ValidationError(
                    "the discharge before an addition is a volume", field="discharged_before"
                )
            if self.discharged_before.value < 0.0:
                raise ValidationError(
                    "the discharge before an addition cannot be negative",
                    field="discharged_before",
                )

    @property
    def mass(self) -> Quantity:
        """The water as a weight, which is what the ratio is computed on."""
        return WATER_DENSITY.times(self.amount)

    @property
    def was_mixed_in(self) -> bool:
        """True when the drum turned enough afterwards for it to be concrete."""
        return self.revolutions_after >= MIXING_REVOLUTIONS_AFTER_WATER

    @property
    def after_discharge_started(self) -> bool:
        """True when concrete had already gone in the forms before this."""
        return self.discharged_before is not None and not self.discharged_before.is_zero()


@dataclass(frozen=True, slots=True)
class WaterAdditionVerdict:
    """One addition judged against the mixture it went into."""

    addition: WaterAddition
    batch_water: Quantity
    cementitious: Quantity
    design_ratio: float
    max_ratio: float | None

    @property
    def resulting_water(self) -> Quantity:
        """Total water in the load after the addition."""
        return self.batch_water + self.addition.mass.to(self.batch_water.unit)

    @property
    def resulting_ratio(self) -> float:
        """Water-cementitious ratio after the addition."""
        if self.cementitious.is_zero():
            raise ValidationError(
                "a load with no cementitious material has no ratio", field="cementitious"
            )
        return self.resulting_water.base_value / self.cementitious.base_value

    @property
    def exceeds_design(self) -> bool:
        """True when the addition takes the load past its design water."""
        return self.resulting_ratio > self.design_ratio + 1e-9

    @property
    def exceeds_specification(self) -> bool:
        """True when the addition takes the load past a specified ratio limit."""
        return self.max_ratio is not None and self.resulting_ratio > self.max_ratio + 1e-9

    @property
    def warranty_void(self) -> bool:
        """True when the producer is no longer answerable for the strength.

        Only the purchaser can void it. Water the producer adds to bring a load
        back to its own design is the producer's problem either way.
        """
        return self.exceeds_design and self.addition.requested_by is RequestedBy.PURCHASER

    @property
    def reasons(self) -> tuple[str, ...]:
        """Everything wrong with this addition."""
        found: list[str] = []
        if self.exceeds_specification and self.max_ratio is not None:
            found.append(
                f"takes the ratio to {self.resulting_ratio:.3f}, past the specified "
                f"{self.max_ratio:.2f}"
            )
        elif self.exceeds_design:
            found.append(
                f"takes the ratio to {self.resulting_ratio:.3f}, past the design "
                f"{self.design_ratio:.3f}"
            )
        if not self.addition.was_mixed_in:
            found.append(
                f"followed by {self.addition.revolutions_after} revolutions, "
                f"{MIXING_REVOLUTIONS_AFTER_WATER} are needed"
            )
        if self.addition.after_discharge_started:
            found.append("added after discharge had already started")
        return tuple(found)

    @property
    def conforms(self) -> bool:
        """True when the addition breaks nothing."""
        return not self.reasons

    def describe(self) -> str:
        """One line for a ticket audit."""
        head = (
            f"{self.addition.amount.format(1)} added by "
            f"{self.addition.requested_by}, ratio {self.resulting_ratio:.3f}"
        )
        if self.conforms:
            return head
        tail = "; ".join(self.reasons)
        void = ", warranty void" if self.warranty_void else ""
        return f"{head}: {tail}{void}"


def judge_addition(
    addition: WaterAddition,
    batch_water: Quantity,
    cementitious: Quantity,
    design_ratio: float,
    max_ratio: float | None = None,
) -> WaterAdditionVerdict:
    """Judge one jobsite water addition."""
    for name, amount in (("batch_water", batch_water), ("cementitious", cementitious)):
        if amount.dimension.value != "mass":
            raise ValidationError(f"{name} is a mass", field=name)
        if amount.value < 0.0:
            raise ValidationError(f"{name} cannot be negative", field=name)
    if design_ratio <= 0.0:
        raise ValidationError("a design ratio has to be positive", field="design_ratio")
    return WaterAdditionVerdict(addition, batch_water, cementitious, design_ratio, max_ratio)
