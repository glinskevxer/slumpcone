"""Mass per unit volume, the shape almost every mix design number has.

Cement content, aggregate weight, water content and unit weight are all a mass
over a volume. Written as a bare float it is either lb/yd3 or kg/m3 and the
factor between them is 0.5933, which is close enough to 0.6 that a wrong guess
survives a sanity check and reaches the truck.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from slumpcone.errors import UnitError, ValidationError
from slumpcone.units.dimension import Dimension, resolve
from slumpcone.units.quantity import Quantity

_TEXT = re.compile(
    r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(?P<mass>[A-Za-z]+)\s*"
    r"(?:/|\s+per\s+)\s*(?P<volume>[A-Za-z0-9^³]+)\s*$"
)


@dataclass(frozen=True, slots=True, eq=False, order=False)
class MassPerVolume:
    """A mass of material carried by each unit volume of concrete."""

    value: float
    mass_unit: str
    volume_unit: str

    def __post_init__(self) -> None:
        mass = resolve(self.mass_unit)
        volume = resolve(self.volume_unit)
        if mass.dimension is not Dimension.MASS:
            raise UnitError(f"{self.mass_unit!r} is not a mass", field="mass_unit")
        if volume.dimension is not Dimension.VOLUME:
            raise UnitError(f"{self.volume_unit!r} is not a volume", field="volume_unit")
        if not math.isfinite(self.value):
            raise ValidationError("a rate has to be finite", field="value")
        object.__setattr__(self, "mass_unit", mass.symbol)
        object.__setattr__(self, "volume_unit", volume.symbol)
        object.__setattr__(self, "value", float(self.value))

    @classmethod
    def parse(cls, text: str) -> MassPerVolume:
        """Read ``"564 lb/yd3"`` or ``"335 kg per m3"``."""
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a rate", field="rate")
        return cls(
            float(match.group("value")),
            match.group("mass"),
            match.group("volume"),
        )

    @classmethod
    def of(cls, mass: Quantity, volume: Quantity) -> MassPerVolume:
        """The rate that puts ``mass`` in every ``volume``."""
        if volume.is_zero():
            raise ValidationError("cannot take a rate over zero volume", field="volume")
        return cls(mass.value / volume.value, mass.unit, volume.unit)

    @property
    def base_value(self) -> float:
        """Kilograms per cubic metre, whatever units it was written in."""
        return self.value * resolve(self.mass_unit).to_base / resolve(self.volume_unit).to_base

    @property
    def units(self) -> str:
        """The unit pair as it prints, for example ``lb/yd3``."""
        return f"{self.mass_unit}/{self.volume_unit}"

    def to(self, mass_unit: str, volume_unit: str) -> MassPerVolume:
        """The same rate in another unit pair."""
        mass = resolve(mass_unit)
        volume = resolve(volume_unit)
        if mass.dimension is not Dimension.MASS:
            raise UnitError(f"{mass_unit!r} is not a mass", field="mass_unit")
        if volume.dimension is not Dimension.VOLUME:
            raise UnitError(f"{volume_unit!r} is not a volume", field="volume_unit")
        return MassPerVolume(
            self.base_value * volume.to_base / mass.to_base,
            mass.symbol,
            volume.symbol,
        )

    def times(self, volume: Quantity) -> Quantity:
        """The mass this rate puts into ``volume``."""
        if volume.dimension is not Dimension.VOLUME:
            raise UnitError(f"{volume.unit!r} is not a volume", field="volume")
        return Quantity(self.value * volume.to(self.volume_unit).value, self.mass_unit)

    def __add__(self, other: MassPerVolume) -> MassPerVolume:
        return MassPerVolume(
            self.value + other.to(self.mass_unit, self.volume_unit).value,
            self.mass_unit,
            self.volume_unit,
        )

    def __sub__(self, other: MassPerVolume) -> MassPerVolume:
        return MassPerVolume(
            self.value - other.to(self.mass_unit, self.volume_unit).value,
            self.mass_unit,
            self.volume_unit,
        )

    def __mul__(self, factor: float) -> MassPerVolume:
        return MassPerVolume(self.value * float(factor), self.mass_unit, self.volume_unit)

    __rmul__ = __mul__

    def __truediv__(self, other: MassPerVolume | float) -> MassPerVolume | float:
        if isinstance(other, MassPerVolume):
            if other.base_value == 0.0:
                raise ValidationError("division by a zero rate", field="value")
            return self.base_value / other.base_value
        divisor = float(other)
        if divisor == 0.0:
            raise ValidationError("division by zero", field="value")
        return MassPerVolume(self.value / divisor, self.mass_unit, self.volume_unit)

    def ratio_to(self, other: MassPerVolume) -> float:
        """This rate divided by another, as a plain number.

        ``__truediv__`` has to answer both "scale this rate" and "compare two
        rates", so its return type is a union and every caller has to narrow it.
        Callers that only ever want the ratio use this instead.
        """
        if other.base_value == 0.0:
            raise ValidationError("division by a zero rate", field="value")
        return self.base_value / other.base_value

    def __neg__(self) -> MassPerVolume:
        return MassPerVolume(-self.value, self.mass_unit, self.volume_unit)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MassPerVolume):
            return NotImplemented
        return math.isclose(self.base_value, other.base_value, rel_tol=1e-12, abs_tol=1e-15)

    def __hash__(self) -> int:
        return hash(round(self.base_value, 9))

    def __lt__(self, other: MassPerVolume) -> bool:
        return self.base_value < other.base_value and self != other

    def __le__(self, other: MassPerVolume) -> bool:
        return self.base_value <= other.base_value or self == other

    def __gt__(self, other: MassPerVolume) -> bool:
        return not self <= other

    def __ge__(self, other: MassPerVolume) -> bool:
        return not self < other

    def is_zero(self) -> bool:
        """True when the rate is zero to the comparison tolerance."""
        return math.isclose(self.base_value, 0.0, abs_tol=1e-15)

    def format(self, digits: int = 1) -> str:
        """Print the rate to ``digits`` decimal places with its unit pair."""
        return f"{self.value:.{digits}f} {self.units}"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"MassPerVolume({self.value!r}, {self.mass_unit!r}, {self.volume_unit!r})"
