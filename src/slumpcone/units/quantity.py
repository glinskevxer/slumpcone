"""A magnitude with a unit attached.

Every number that leaves this package with a unit on it is a :class:`Quantity`.
Bare floats are used only inside a single calculation, never across a module
boundary, because the two unit systems in this trade look identical on the wire:
``350`` is a plausible cement content in both lb/yd3 and kg/m3 and they are not
the same concrete.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from slumpcone.errors import UnitError, ValidationError
from slumpcone.units.dimension import Dimension, resolve

_TEXT = re.compile(
    r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(?P<unit>.+?)\s*$"
)

# Two magnitudes are the same when they agree to twelve significant figures.
# Anything looser hides a real conversion mistake; anything tighter turns
# ordinary float noise into a failing comparison.
_REL_TOL = 1e-12


@dataclass(frozen=True, slots=True, eq=False, order=False)
class Quantity:
    """A finite magnitude in one of the units the table knows."""

    value: float
    unit: str = field()

    def __post_init__(self) -> None:
        unit = resolve(self.unit)
        object.__setattr__(self, "unit", unit.symbol)
        try:
            magnitude = float(self.value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValidationError(f"{self.value!r} is not a number", field="value") from exc
        if not math.isfinite(magnitude):
            raise ValidationError("a quantity has to be finite", field="value")
        object.__setattr__(self, "value", magnitude)

    @property
    def dimension(self) -> Dimension:
        """What this quantity measures."""
        return resolve(self.unit).dimension

    @property
    def base_value(self) -> float:
        """The magnitude expressed in this dimension's SI base unit."""
        return self.value * resolve(self.unit).to_base

    @classmethod
    def parse(cls, text: str) -> Quantity:
        """Read ``"3000 psi"`` or ``"27ft3"`` into a quantity."""
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a quantity", field="quantity")
        return cls(float(match.group("value")), match.group("unit"))

    @classmethod
    def zero(cls, unit: str) -> Quantity:
        """Nothing at all, carrying a unit so it can still be added."""
        return cls(0.0, unit)

    def to(self, unit: str) -> Quantity:
        """This magnitude in ``unit``.

        Raises :class:`UnitError` when the target measures something else.
        """
        target = resolve(unit)
        if target.dimension is not self.dimension:
            raise UnitError(
                f"cannot express {self.dimension} in {target.symbol}, which measures "
                f"{target.dimension}",
                field="unit",
            )
        return Quantity(self.base_value / target.to_base, target.symbol)

    def _same_dimension(self, other: Quantity, verb: str) -> None:
        if other.dimension is not self.dimension:
            raise UnitError(
                f"cannot {verb} {other.dimension} and {self.dimension}",
                field="unit",
            )

    def __add__(self, other: Quantity) -> Quantity:
        self._same_dimension(other, "add")
        return Quantity(self.value + other.to(self.unit).value, self.unit)

    def __sub__(self, other: Quantity) -> Quantity:
        self._same_dimension(other, "subtract")
        return Quantity(self.value - other.to(self.unit).value, self.unit)

    def __mul__(self, factor: float) -> Quantity:
        return Quantity(self.value * float(factor), self.unit)

    __rmul__ = __mul__

    def __truediv__(self, other: Quantity | float) -> Quantity | float:
        if isinstance(other, Quantity):
            self._same_dimension(other, "divide")
            divisor = other.base_value
            if divisor == 0.0:
                raise ValidationError("division by a zero quantity", field="value")
            return self.base_value / divisor
        divisor = float(other)
        if divisor == 0.0:
            raise ValidationError("division by zero", field="value")
        return Quantity(self.value / divisor, self.unit)

    def __neg__(self) -> Quantity:
        return Quantity(-self.value, self.unit)

    def __abs__(self) -> Quantity:
        return Quantity(abs(self.value), self.unit)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.dimension is not self.dimension:
            return False
        return math.isclose(self.base_value, other.base_value, rel_tol=_REL_TOL, abs_tol=1e-15)

    def __hash__(self) -> int:
        return hash((self.dimension, round(self.base_value, 12)))

    def _compare(self, other: Quantity, verb: str) -> tuple[float, float]:
        if not isinstance(other, Quantity):  # pragma: no cover - defensive
            raise TypeError(f"cannot {verb} a quantity against {type(other).__name__}")
        self._same_dimension(other, verb)
        return self.base_value, other.base_value

    def __lt__(self, other: Quantity) -> bool:
        mine, theirs = self._compare(other, "order")
        return mine < theirs and not self == other

    def __le__(self, other: Quantity) -> bool:
        mine, theirs = self._compare(other, "order")
        return mine <= theirs or self == other

    def __gt__(self, other: Quantity) -> bool:
        return not self <= other

    def __ge__(self, other: Quantity) -> bool:
        return not self < other

    def is_zero(self) -> bool:
        """True when the magnitude is zero to the comparison tolerance."""
        return math.isclose(self.base_value, 0.0, abs_tol=1e-15)

    def format(self, digits: int = 2) -> str:
        """Print the magnitude to ``digits`` decimal places with its unit."""
        if digits < 0:
            raise ValidationError("digits cannot be negative", field="digits")
        return f"{self.value:.{digits}f} {self.unit}"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Quantity({self.value!r}, {self.unit!r})"

    def __format__(self, spec: str) -> str:
        if not spec:
            return str(self)
        return f"{format(self.value, spec)} {self.unit}"

    def __bool__(self) -> bool:
        return not self.is_zero()

    def __float__(self) -> float:  # pragma: no cover - convenience only
        return self.value

    def as_dict(self) -> dict[str, Any]:
        """The wire form: magnitude and canonical symbol."""
        return {"value": self.value, "unit": self.unit}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Quantity:
        """Rebuild from :meth:`as_dict`."""
        try:
            return cls(float(raw["value"]), str(raw["unit"]))
        except KeyError as exc:
            missing = exc.args[0]
            raise ValidationError(f"quantity is missing {missing!r}", field="quantity") from exc
