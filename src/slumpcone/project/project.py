"""The job, and the classes of concrete its drawings call for.

A project does not order a mix design. It orders a class: "4000 psi, F2, six
inch slump", and the producer proposes a mixture that satisfies it. The class
is what the specification says and it outlives any particular mixture, so it is
what everything downstream is judged against.

One project can carry several classes and usually does. A building has a slab
class, a wall class and a footing class, all with different exposures, and a
truck delivering the wrong one is a real and common failure that nothing in the
plant catches on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.spec.exposure import ExposureSet
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


@dataclass(frozen=True, slots=True)
class SpecifiedClass:
    """One class of concrete a project's drawings call for."""

    code: str
    specified_strength: Quantity
    test_age_days: int = 28
    exposure: ExposureSet = field(default_factory=ExposureSet)
    slump_band: Band | None = None
    air_band: Band | None = None
    max_water_cementitious: float | None = None
    min_cementitious: Quantity | None = None
    nominal_max_size: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="class_code"))
        if self.specified_strength.dimension.value != "pressure":
            raise ValidationError(
                "a specified strength is a pressure", field="specified_strength"
            )
        if self.specified_strength.value <= 0.0:
            raise ValidationError(
                "a specified strength has to be positive", field="specified_strength"
            )
        if self.test_age_days <= 0:
            raise ValidationError("a test age has to be positive", field="test_age_days")
        if self.max_water_cementitious is not None and self.max_water_cementitious <= 0.0:
            raise ValidationError(
                "a ratio limit has to be positive", field="max_water_cementitious"
            )
        if (
            self.min_cementitious is not None
            and self.min_cementitious.dimension.value != "mass"
        ):
            raise ValidationError("a cementitious floor is a mass", field="min_cementitious")
        if (
            self.nominal_max_size is not None
            and self.nominal_max_size.dimension.value != "length"
        ):
            raise ValidationError(
                "a nominal maximum size is a length", field="nominal_max_size"
            )

    @property
    def effective_ratio_limit(self) -> float | None:
        """The tightest ratio limit, from the drawings or from the exposure."""
        from_exposure = self.exposure.max_water_cementitious
        limits = [
            value for value in (self.max_water_cementitious, from_exposure) if value is not None
        ]
        return min(limits) if limits else None

    @property
    def effective_strength_floor(self) -> Quantity:
        """The higher of the specified strength and the exposure floor."""
        floor = self.exposure.min_strength
        return max(self.specified_strength, floor, key=lambda q: q.base_value)

    def describe(self) -> str:
        """One line for a project listing."""
        ratio = self.effective_ratio_limit
        tail = f"  w/cm max {ratio:.2f}" if ratio is not None else ""
        return (
            f"{self.code}  {self.specified_strength.format(0)} at "
            f"{self.test_age_days} d  {self.exposure}{tail}"
        )


@dataclass(frozen=True, slots=True)
class Project:
    """One job, its classes and the window it runs over."""

    code: str
    name: str
    classes: tuple[SpecifiedClass, ...] = ()
    owner: str | None = None
    specifier: str | None = None
    unit_system: UnitSystem = UnitSystem.CUSTOMARY
    started_on: date | None = None
    finished_on: date | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="project_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="project_name"))
        for label in ("owner", "specifier"):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, normalize_name(value, field=label))
        seen: set[str] = set()
        for entry in self.classes:
            if entry.code in seen:
                raise ValidationError(f"class {entry.code} appears twice", field="classes")
            seen.add(entry.code)
        if (
            self.started_on is not None
            and self.finished_on is not None
            and self.finished_on < self.started_on
        ):
            raise ValidationError(
                "a project cannot finish before it starts", field="finished_on"
            )

    @property
    def class_codes(self) -> tuple[str, ...]:
        """Every class code on the job, sorted."""
        return tuple(sorted(entry.code for entry in self.classes))

    def specified_class(self, code: str) -> SpecifiedClass:
        """One class by code."""
        key = normalize_code(code, field="class_code")
        for entry in self.classes:
            if entry.code == key:
                return entry
        raise NotFoundError("specified class", key)

    def is_open(self, on: date) -> bool:
        """True when the job is running on ``on``."""
        if self.started_on is not None and on < self.started_on:
            return False
        return not (self.finished_on is not None and on > self.finished_on)

    def describe(self) -> str:
        """One line for a listing."""
        who = f"  {self.owner}" if self.owner else ""
        return f"{self.code}  {self.name}{who}  {len(self.classes)} classes"
