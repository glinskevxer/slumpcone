"""The delivery ticket.

C94 makes the ticket a legal document and lists what has to be on it: the
plant, a serial number, the date, the truck, the purchaser, the job, the
designation of the concrete, the volume, the time of first mixing, and space
for water the receiver adds at the site.

The check here is that those fields are *present*, not that they are true.
Nothing in software can tell whether the truck number written down is the truck
that left, but a ticket with no truck number on it at all is a ticket that
cannot be reconciled against anything, and those are the ones that turn up in a
dispute two years later.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from slumpcone.batching.engine import PlannedBatch
from slumpcone.batching.weighing import WeighingResult
from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name, normalize_ticket_number
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.quantity import Quantity

REQUIRED_TICKET_FIELDS = (
    "plant_code",
    "number",
    "batched_at",
    "truck_code",
    "purchaser",
    "project",
    "mix_code",
    "volume",
)


@dataclass(frozen=True, slots=True)
class TicketLine:
    """One weighed material as the batch recorder logged it."""

    material_code: str
    material_class: MaterialClass
    required: Quantity
    actual: Quantity
    allowance: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        for name, amount in (
            ("required", self.required),
            ("actual", self.actual),
            ("allowance", self.allowance),
        ):
            if amount.dimension.value != "mass":
                raise ValidationError(f"a ticket {name} is a mass", field=name)
        if self.actual.value < 0.0:
            raise ValidationError("a recorded weight cannot be negative", field="actual")

    @property
    def result(self) -> WeighingResult:
        """This line judged against its tolerance."""
        return WeighingResult(
            self.material_code, self.material_class, self.required, self.actual, self.allowance
        )


@dataclass(frozen=True, slots=True)
class TicketAdmixture:
    """One admixture dispensed, as the dispenser logged it."""

    material_code: str
    called_for: Quantity
    dispensed: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        for name, amount in (("called_for", self.called_for), ("dispensed", self.dispensed)):
            if amount.dimension.value != "volume":
                raise ValidationError(f"an admixture {name} is a volume", field=name)

    @property
    def error(self) -> Quantity:
        """Dispensed less called for."""
        return self.dispensed - self.called_for.to(self.dispensed.unit)

    @property
    def conforms(self) -> bool:
        """True inside the three percent an admixture dispenser is allowed."""
        if self.called_for.is_zero():
            return self.dispensed.is_zero()
        return abs(self.error.base_value) <= abs(self.called_for.base_value) * 0.03 + 1e-12


@dataclass(frozen=True, slots=True)
class BatchTicket:
    """One delivery, as it left the plant."""

    number: str
    plant_code: str
    mix_code: str
    mix_revision: int
    batched_at: datetime
    volume: Quantity
    lines: tuple[TicketLine, ...]
    admixtures: tuple[TicketAdmixture, ...] = ()
    truck_code: str | None = None
    purchaser: str | None = None
    project: str | None = None
    cumulative_volume: Quantity | None = None
    revolution_counter: int | None = None
    water_held_back: Quantity | None = None
    notes: str = field(default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalize_ticket_number(self.number))
        object.__setattr__(
            self, "plant_code", normalize_code(self.plant_code, field="plant_code")
        )
        object.__setattr__(self, "mix_code", normalize_code(self.mix_code, field="mix_code"))
        if self.truck_code is not None:
            object.__setattr__(
                self, "truck_code", normalize_code(self.truck_code, field="truck_code")
            )
        if self.purchaser is not None:
            object.__setattr__(
                self, "purchaser", normalize_name(self.purchaser, field="purchaser")
            )
        if self.project is not None:
            object.__setattr__(self, "project", normalize_name(self.project, field="project"))
        if self.volume.dimension.value != "volume":
            raise ValidationError("a load size is a volume", field="volume")
        if self.volume.value <= 0.0:
            raise ValidationError("a load size has to be positive", field="volume")
        if self.mix_revision <= 0:
            raise ValidationError("a mix revision starts at one", field="mix_revision")
        if self.revolution_counter is not None and self.revolution_counter < 0:
            raise ValidationError(
                "a revolution counter cannot read negative", field="revolution_counter"
            )

    @classmethod
    def from_plan(
        cls,
        planned: PlannedBatch,
        number: str,
        batched_at: datetime,
        actuals: Mapping[str, Quantity] | None = None,
        dispensed: Mapping[str, Quantity] | None = None,
        **details: object,
    ) -> BatchTicket:
        """Write a ticket for a planned batch, recording what actually happened.

        A material with no recorded weight is taken to have been batched
        exactly, which is what a plant with no recording batcher would have to
        assume anyway.
        """
        recorded = actuals or {}
        given = dispensed or {}
        lines = tuple(
            TicketLine(
                entry.material_code,
                entry.material_class,
                entry.required,
                recorded.get(entry.material_code, entry.required),
                entry.allowance,
            )
            for entry in planned.lines
        )
        admixtures = tuple(
            TicketAdmixture(
                entry.material_code,
                entry.charge,
                given.get(entry.material_code, entry.charge),
            )
            for entry in planned.admixture_lines
        )
        return cls(
            number=number,
            plant_code=planned.plant_code,
            mix_code=planned.mix_code,
            mix_revision=planned.mix_revision,
            batched_at=batched_at,
            volume=planned.volume,
            lines=lines,
            admixtures=admixtures,
            **details,  # type: ignore[arg-type]
        )

    def line(self, material_code: str) -> TicketLine:
        """One line by material code."""
        key = normalize_code(material_code, field="material_code")
        for candidate in self.lines:
            if candidate.material_code == key:
                return candidate
        raise ValidationError(f"{key} is not on this ticket", field="material_code")

    @property
    def results(self) -> tuple[WeighingResult, ...]:
        """Every weighed line judged against its tolerance."""
        return tuple(entry.result for entry in self.lines)

    @property
    def out_of_tolerance(self) -> tuple[WeighingResult, ...]:
        """The lines that missed."""
        return tuple(result for result in self.results if not result.conforms)

    @property
    def admixtures_out_of_tolerance(self) -> tuple[TicketAdmixture, ...]:
        """The admixture doses that missed."""
        return tuple(entry for entry in self.admixtures if not entry.conforms)

    def missing_required_fields(self) -> tuple[str, ...]:
        """Which of C94's mandatory ticket fields are blank."""
        missing: list[str] = []
        for name in REQUIRED_TICKET_FIELDS:
            if getattr(self, name, None) is None:
                missing.append(name)
        return tuple(missing)

    @property
    def is_complete(self) -> bool:
        """True when every mandatory field is filled in."""
        return not self.missing_required_fields()

    @property
    def batched_weight(self) -> Quantity:
        """Everything the scales actually recorded."""
        total = Quantity.zero("lb")
        for entry in self.lines:
            total = total + entry.actual.to("lb")
        return total

    def describe(self) -> str:
        """The ticket header as it prints."""
        return (
            f"ticket {self.number}  {self.plant_code}  {self.mix_code} r{self.mix_revision}  "
            f"{self.volume.format(2)}  {self.batched_at.isoformat(sep=' ', timespec='minutes')}"
        )
