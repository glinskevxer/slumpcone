"""Cylinders, and the three things about one that decide what it can be used for.

Size decides how many of them make a test. Two six by twelve cylinders average
to a strength test; four by eights are more variable, so it takes three of them.
A lab that switches to the smaller mould to save concrete and keeps casting two
per set has quietly stopped producing valid acceptance tests.

Cure decides whether the result is about the concrete or about the structure.
Standard cured cylinders are the ones acceptance is judged on. Field cured ones
sit next to the pour under the same blankets and answer a different question:
whether the forms can come off yet.

Purpose is what the lab was asked for, and it is recorded rather than inferred,
because a set cast for form removal that happens to be standard cured is still
not part of the acceptance record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_ticket_number
from slumpcone.units.quantity import Quantity


class SpecimenSize(Enum):
    """The mould a specimen was cast in."""

    CYL_6X12 = "6x12"
    CYL_4X8 = "4x8"
    CYL_150X300 = "150x300"
    CYL_100X200 = "100x200"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> SpecimenSize:
        """Read a mould size off a lab sheet."""
        key = text.strip().lower().replace(" ", "").replace("*", "x").replace("by", "x")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown specimen size {text!r}", field="specimen_size")

    @property
    def nominal_diameter(self) -> Quantity:
        """The diameter the mould is nominally made to."""
        table = {
            SpecimenSize.CYL_6X12: Quantity(6.0, "in"),
            SpecimenSize.CYL_4X8: Quantity(4.0, "in"),
            SpecimenSize.CYL_150X300: Quantity(150.0, "mm"),
            SpecimenSize.CYL_100X200: Quantity(100.0, "mm"),
        }
        return table[self]

    @property
    def nominal_length(self) -> Quantity:
        """The length the mould is nominally made to."""
        return self.nominal_diameter * 2.0

    @property
    def is_small(self) -> bool:
        """True for the four inch and hundred millimetre moulds."""
        return self in {SpecimenSize.CYL_4X8, SpecimenSize.CYL_100X200}

    @property
    def specimens_per_test(self) -> int:
        """How many of this size average to one strength test.

        Three for the small moulds, two for the large ones. The smaller
        specimen has a higher coefficient of variation, so more of them are
        needed for the average to carry the same weight.
        """
        return 3 if self.is_small else 2

    @property
    def largest_aggregate(self) -> Quantity:
        """The biggest aggregate this mould may be used with.

        A specimen has to be at least three times the nominal maximum aggregate
        size across, or the aggregate arranges itself against the mould wall
        rather than at random and the break is not about the concrete.
        """
        return self.nominal_diameter * (1.0 / 3.0)


class CureCondition(Enum):
    """How the specimen was kept between casting and testing."""

    STANDARD = "standard"
    FIELD = "field"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> CureCondition:
        """Read a cure condition off a lab sheet."""
        key = text.strip().lower()
        aliases = {"lab": "standard", "moist": "standard", "job": "field", "site": "field"}
        key = aliases.get(key, key)
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown cure condition {text!r}", field="cure")

    @property
    def counts_for_acceptance(self) -> bool:
        """True when a break on this specimen can accept or reject the concrete."""
        return self is CureCondition.STANDARD


class SpecimenPurpose(Enum):
    """What the set was cast for."""

    ACCEPTANCE = "acceptance"
    FORM_REMOVAL = "form_removal"
    INFORMATION = "information"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> SpecimenPurpose:
        """Read a purpose off a lab sheet."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown specimen purpose {text!r}", field="purpose")


@dataclass(frozen=True, slots=True)
class Specimen:
    """One cylinder, from the load it came off to the day it is due."""

    code: str
    set_code: str
    ticket_number: str
    cast_at: datetime
    size: SpecimenSize = SpecimenSize.CYL_4X8
    cure: CureCondition = CureCondition.STANDARD
    purpose: SpecimenPurpose = SpecimenPurpose.ACCEPTANCE
    age_days: int = 28
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="specimen_code"))
        object.__setattr__(self, "set_code", normalize_code(self.set_code, field="set_code"))
        object.__setattr__(self, "ticket_number", normalize_ticket_number(self.ticket_number))
        if self.age_days <= 0:
            raise ValidationError("a test age has to be positive", field="age_days")

    @property
    def due_at(self) -> datetime:
        """When this specimen should be broken."""
        return self.cast_at + timedelta(days=self.age_days)

    @property
    def counts_for_acceptance(self) -> bool:
        """True when this specimen is part of the acceptance record."""
        return self.cure.counts_for_acceptance and self.purpose is SpecimenPurpose.ACCEPTANCE

    def suits_aggregate(self, nominal_max_size: Quantity) -> bool:
        """True when the mould is big enough for that aggregate."""
        if nominal_max_size.dimension.value != "length":
            raise ValidationError(
                "a nominal maximum size is a length", field="nominal_max_size"
            )
        return nominal_max_size <= self.size.largest_aggregate

    def age_at(self, when: datetime) -> float:
        """How old the specimen is, in days, at some moment."""
        return (when - self.cast_at).total_seconds() / 86400.0

    def describe(self) -> str:
        """One line for a lab log."""
        return (
            f"{self.code}  set {self.set_code}  ticket {self.ticket_number}  "
            f"{self.size} {self.cure}  {self.age_days} d  due {self.due_at.date().isoformat()}"
        )
