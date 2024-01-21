"""Temperature, which is not a :class:`~slumpcone.units.quantity.Quantity`.

Fahrenheit and Celsius are affine, not scalar, so the conversion carries an
offset and multiplying a temperature by two is meaningless. Keeping it in its
own type means the mistake cannot be written down: there is no ``__mul__`` here
and no way to hand a temperature to something expecting a mass.

A *difference* between two temperatures is scalar, so subtraction returns a
:class:`TemperatureDelta`, and that one does support scaling.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from slumpcone.errors import UnitError, ValidationError

_TEXT = re.compile(r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+)\s*(?:deg\s*)?(?P<unit>[CFcf])\s*$")

_ABSOLUTE_ZERO_C = -273.15


def _canonical(unit: str) -> str:
    key = unit.strip().lstrip("°").lstrip("deg").strip().upper()
    if key in {"C", "CELSIUS", "CENTIGRADE"}:
        return "C"
    if key in {"F", "FAHRENHEIT"}:
        return "F"
    raise UnitError(f"unknown temperature unit {unit!r}", field="unit")


@dataclass(frozen=True, slots=True, eq=False, order=False)
class TemperatureDelta:
    """A difference between two temperatures, in degrees C or degrees F."""

    value: float
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit", _canonical(self.unit))
        if not math.isfinite(self.value):
            raise ValidationError("a temperature difference has to be finite", field="value")
        object.__setattr__(self, "value", float(self.value))

    def to(self, unit: str) -> TemperatureDelta:
        """This difference expressed in the other scale.

        A degree difference scales by 9/5 with no offset, which is exactly the
        part people get wrong when they convert a tolerance band.
        """
        target = _canonical(unit)
        if target == self.unit:
            return self
        if target == "F":
            return TemperatureDelta(self.value * 9.0 / 5.0, "F")
        return TemperatureDelta(self.value * 5.0 / 9.0, "C")

    def __add__(self, other: TemperatureDelta) -> TemperatureDelta:
        return TemperatureDelta(self.value + other.to(self.unit).value, self.unit)

    def __sub__(self, other: TemperatureDelta) -> TemperatureDelta:
        return TemperatureDelta(self.value - other.to(self.unit).value, self.unit)

    def __mul__(self, factor: float) -> TemperatureDelta:
        return TemperatureDelta(self.value * float(factor), self.unit)

    __rmul__ = __mul__

    def __neg__(self) -> TemperatureDelta:
        return TemperatureDelta(-self.value, self.unit)

    def __abs__(self) -> TemperatureDelta:
        return TemperatureDelta(abs(self.value), self.unit)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TemperatureDelta):
            return NotImplemented
        return math.isclose(self.value, other.to(self.unit).value, rel_tol=1e-12, abs_tol=1e-12)

    def __hash__(self) -> int:
        return hash(round(self.to("C").value, 9))

    def __lt__(self, other: TemperatureDelta) -> bool:
        return self.value < other.to(self.unit).value and self != other

    def __le__(self, other: TemperatureDelta) -> bool:
        return self.value <= other.to(self.unit).value or self == other

    def __gt__(self, other: TemperatureDelta) -> bool:
        return not self <= other

    def __ge__(self, other: TemperatureDelta) -> bool:
        return not self < other

    def __str__(self) -> str:
        return f"{self.value:.1f} deg{self.unit}"


@dataclass(frozen=True, slots=True, eq=False, order=False)
class Temperature:
    """A concrete, air or material temperature on one of the two scales."""

    value: float
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit", _canonical(self.unit))
        if not math.isfinite(self.value):
            raise ValidationError("a temperature has to be finite", field="value")
        object.__setattr__(self, "value", float(self.value))
        if self.celsius < _ABSOLUTE_ZERO_C - 1e-9:
            raise ValidationError("temperature is below absolute zero", field="value")

    @property
    def celsius(self) -> float:
        """The reading in degrees Celsius, whatever scale it was taken on."""
        if self.unit == "C":
            return self.value
        return (self.value - 32.0) * 5.0 / 9.0

    @property
    def fahrenheit(self) -> float:
        """The reading in degrees Fahrenheit."""
        if self.unit == "F":
            return self.value
        return self.value * 9.0 / 5.0 + 32.0

    @classmethod
    def parse(cls, text: str) -> Temperature:
        """Read ``"72 F"``, ``"72degF"`` or ``"22 C"``."""
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a temperature", field="temperature")
        return cls(float(match.group("value")), match.group("unit"))

    def to(self, unit: str) -> Temperature:
        """The same reading on the other scale."""
        target = _canonical(unit)
        if target == self.unit:
            return self
        if target == "F":
            return Temperature(self.fahrenheit, "F")
        return Temperature(self.celsius, "C")

    def __add__(self, delta: TemperatureDelta) -> Temperature:
        return Temperature(self.value + delta.to(self.unit).value, self.unit)

    def __sub__(self, other: Temperature | TemperatureDelta) -> Temperature | TemperatureDelta:
        if isinstance(other, TemperatureDelta):
            return Temperature(self.value - other.to(self.unit).value, self.unit)
        return TemperatureDelta(self.value - other.to(self.unit).value, self.unit)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Temperature):
            return NotImplemented
        return math.isclose(self.celsius, other.celsius, rel_tol=1e-12, abs_tol=1e-9)

    def __hash__(self) -> int:
        return hash(round(self.celsius, 9))

    def __lt__(self, other: Temperature) -> bool:
        return self.celsius < other.celsius and self != other

    def __le__(self, other: Temperature) -> bool:
        return self.celsius <= other.celsius or self == other

    def __gt__(self, other: Temperature) -> bool:
        return not self <= other

    def __ge__(self, other: Temperature) -> bool:
        return not self < other

    def __str__(self) -> str:
        return f"{self.value:.0f} deg{self.unit}"

    def __repr__(self) -> str:
        return f"Temperature({self.value!r}, {self.unit!r})"
