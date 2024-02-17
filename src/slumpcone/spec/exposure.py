"""Exposure classes, and the requirements they stack up.

A structural drawing assigns one class from each of four categories: freezing
and thawing, sulfate, water contact, and corrosion protection. Each class
carries its own limits, and the mixture has to satisfy all of them at once. The
binding limit is whichever is tightest, and it is rarely the same category
twice running.

The interesting part is that these interact. An F3 slab in a C2 environment
takes the F3 air requirement and the C2 water-cementitious ratio, and the air
requirement itself depends on the aggregate the mixture happens to use.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.materials.gradation import Sieve, sieve
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


class ExposureCategory(Enum):
    """The four categories a drawing assigns a class from."""

    FREEZE_THAW = "F"
    SULFATE = "S"
    WATER = "W"
    CORROSION = "C"

    def __str__(self) -> str:
        return self.value


class ExposureClass(Enum):
    """One class within a category, written the way a drawing writes it."""

    F0 = "F0"
    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    W0 = "W0"
    W1 = "W1"
    W2 = "W2"
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> ExposureClass:
        """Read a class off a drawing note."""
        key = text.strip().upper().replace(" ", "")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown exposure class {text!r}", field="exposure_class")

    @property
    def category(self) -> ExposureCategory:
        """Which category this class belongs to."""
        return ExposureCategory(self.value[0])

    @property
    def severity(self) -> int:
        """The digit, zero being no requirement."""
        return int(self.value[1])

    @property
    def max_water_cementitious(self) -> float | None:
        """The ratio limit this class imposes, or ``None`` for no limit."""
        table: dict[ExposureClass, float] = {
            ExposureClass.F1: 0.55,
            ExposureClass.F2: 0.45,
            ExposureClass.F3: 0.40,
            ExposureClass.S1: 0.50,
            ExposureClass.S2: 0.45,
            ExposureClass.S3: 0.45,
            ExposureClass.W2: 0.50,
            ExposureClass.C2: 0.40,
        }
        return table.get(self)

    @property
    def min_strength(self) -> Quantity:
        """The minimum specified compressive strength this class imposes."""
        table: dict[ExposureClass, float] = {
            ExposureClass.F1: 3500.0,
            ExposureClass.F2: 4500.0,
            ExposureClass.F3: 5000.0,
            ExposureClass.S1: 4000.0,
            ExposureClass.S2: 4500.0,
            ExposureClass.S3: 4500.0,
            ExposureClass.W2: 4000.0,
            ExposureClass.C2: 5000.0,
        }
        return Quantity(table.get(self, 2500.0), "psi")

    @property
    def max_chloride(self) -> Percent | None:
        """Water soluble chloride ion limit by mass of cementitious."""
        table: dict[ExposureClass, float] = {
            ExposureClass.C0: 1.00,
            ExposureClass.C1: 0.30,
            ExposureClass.C2: 0.15,
        }
        value = table.get(self)
        return None if value is None else Percent(value)

    @property
    def needs_air_entrainment(self) -> bool:
        """True when the class puts a floor under the air content."""
        return self in {ExposureClass.F1, ExposureClass.F2, ExposureClass.F3}

    @property
    def caps_supplementary_cementitious(self) -> bool:
        """True when the class caps how much of the binder may be an SCM.

        F3 does, because too much replacement leaves a surface that scales
        under deicing salts. It is the only class that does.
        """
        return self is ExposureClass.F3


# ACI's air content table, by nominal maximum aggregate size. The first column
# is the F1 requirement, the second covers F2 and F3.
_AIR_TABLE: tuple[tuple[str, float, float], ...] = (
    ("3/8 in", 6.0, 7.5),
    ("1/2 in", 5.5, 7.0),
    ("3/4 in", 5.0, 6.0),
    ("1 in", 4.5, 6.0),
    ("1-1/2 in", 4.5, 5.5),
    ("2 in", 4.0, 5.0),
    ("3 in", 3.5, 4.5),
)


def air_requirement(
    exposure: ExposureClass, nominal_max_size: Sieve | str, strength: Quantity | None = None
) -> Percent | None:
    """The target air content for a freeze-thaw class and an aggregate size.

    ``None`` means the class puts no floor under the air content at all, which
    is different from a floor of zero: an F0 mixture may still be air entrained
    for finishability and nothing here objects.

    The one reduction the table allows is for high strength concrete. Above
    5000 psi the requirement drops a full percent, because the paste is dense
    enough that the extra air costs more strength than the durability is worth.
    """
    if not exposure.needs_air_entrainment:
        return None
    size = sieve(nominal_max_size) if isinstance(nominal_max_size, str) else nominal_max_size
    for label, moderate, severe in _AIR_TABLE:
        if sieve(label) == size:
            base = moderate if exposure is ExposureClass.F1 else severe
            if strength is not None and strength > Quantity(5000.0, "psi"):
                base -= 1.0
            return Percent(base)
    raise ValidationError(
        f"the air table has no row for a {size} aggregate", field="nominal_max_size"
    )


@dataclass(frozen=True, slots=True)
class ExposureSet:
    """One class from each category, as a drawing assigns them."""

    freeze_thaw: ExposureClass = ExposureClass.F0
    sulfate: ExposureClass = ExposureClass.S0
    water: ExposureClass = ExposureClass.W0
    corrosion: ExposureClass = ExposureClass.C0

    def __post_init__(self) -> None:
        pairs = (
            (self.freeze_thaw, ExposureCategory.FREEZE_THAW),
            (self.sulfate, ExposureCategory.SULFATE),
            (self.water, ExposureCategory.WATER),
            (self.corrosion, ExposureCategory.CORROSION),
        )
        for assigned, expected in pairs:
            if assigned.category is not expected:
                raise ValidationError(
                    f"{assigned} is not a {expected} class", field=str(expected).lower()
                )

    @classmethod
    def parse(cls, text: str) -> ExposureSet:
        """Read ``"F2 S1 W0 C2"`` in any order, filling absent categories with zero."""
        assigned: dict[ExposureCategory, ExposureClass] = {}
        for token in text.replace(",", " ").split():
            member = ExposureClass.parse(token)
            if member.category in assigned:
                raise ValidationError(
                    f"two {member.category} classes in {text!r}", field="exposure"
                )
            assigned[member.category] = member
        return cls(
            assigned.get(ExposureCategory.FREEZE_THAW, ExposureClass.F0),
            assigned.get(ExposureCategory.SULFATE, ExposureClass.S0),
            assigned.get(ExposureCategory.WATER, ExposureClass.W0),
            assigned.get(ExposureCategory.CORROSION, ExposureClass.C0),
        )

    @property
    def classes(self) -> tuple[ExposureClass, ...]:
        """The four assigned classes in category order."""
        return (self.freeze_thaw, self.sulfate, self.water, self.corrosion)

    @property
    def max_water_cementitious(self) -> float | None:
        """The tightest ratio limit any assigned class imposes."""
        limits = [c.max_water_cementitious for c in self.classes if c.max_water_cementitious]
        return min(limits) if limits else None

    @property
    def min_strength(self) -> Quantity:
        """The highest minimum strength any assigned class imposes."""
        return max((c.min_strength for c in self.classes), key=lambda q: q.base_value)

    @property
    def max_chloride(self) -> Percent | None:
        """The tightest chloride limit any assigned class imposes."""
        limits = [c.max_chloride for c in self.classes if c.max_chloride is not None]
        return min(limits, key=lambda p: p.value) if limits else None

    def air_target(
        self, nominal_max_size: Sieve | str, strength: Quantity | None = None
    ) -> Percent | None:
        """The air content this set demands for a given aggregate size."""
        return air_requirement(self.freeze_thaw, nominal_max_size, strength)

    def governing_class(self, attribute: str) -> ExposureClass | None:
        """Which class sets the binding limit for one attribute.

        Reports name the class, not just the number, because an engineer asked
        why a ratio is 0.40 wants to hear "C2", not "because it is".
        """
        if attribute == "max_water_cementitious":
            candidates = [c for c in self.classes if c.max_water_cementitious is not None]
            if not candidates:
                return None
            return min(candidates, key=lambda c: c.max_water_cementitious or 0.0)
        if attribute == "min_strength":
            return max(self.classes, key=lambda c: c.min_strength.base_value)
        if attribute == "max_chloride":
            candidates = [c for c in self.classes if c.max_chloride is not None]
            if not candidates:
                return None
            return min(candidates, key=lambda c: (c.max_chloride or Percent(0.0)).value)
        raise ValidationError(f"no governing class for {attribute!r}", field="attribute")

    def __str__(self) -> str:
        return " ".join(str(c) for c in self.classes)
