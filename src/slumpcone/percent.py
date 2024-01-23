"""Percentages, kept apart from the fractions they stand for.

Air content is written 6.0 and means 0.06. Free moisture is written 3.2 and
means 0.032. A specification writes a replacement limit as 25 and a batch
computer wants 0.25. Every one of those has been entered a hundred times too
large at some point, so the percentage is a type and the fraction is a property
you have to ask for.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from slumpcone.errors import ValidationError

_TEXT = re.compile(r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+)\s*%?\s*$")


@dataclass(frozen=True, slots=True, eq=False, order=False)
class Percent:
    """A percentage. ``Percent(6.0)`` is six percent, not six hundred."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValidationError("a percentage has to be finite", field="percent")
        object.__setattr__(self, "value", float(self.value))

    @classmethod
    def from_fraction(cls, fraction: float) -> Percent:
        """``Percent.from_fraction(0.06)`` is six percent."""
        return cls(float(fraction) * 100.0)

    @classmethod
    def parse(cls, text: str) -> Percent:
        """Read ``"6"``, ``"6%"`` or ``" 6.0 % "``."""
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a percentage", field="percent")
        return cls(float(match.group("value")))

    @property
    def fraction(self) -> float:
        """The same number as a fraction of one."""
        return self.value / 100.0

    def of(self, amount: float) -> float:
        """This percentage of ``amount``."""
        return amount * self.fraction

    def __add__(self, other: Percent) -> Percent:
        return Percent(self.value + other.value)

    def __sub__(self, other: Percent) -> Percent:
        return Percent(self.value - other.value)

    def __mul__(self, factor: float) -> Percent:
        return Percent(self.value * float(factor))

    __rmul__ = __mul__

    def __truediv__(self, divisor: float) -> Percent:
        if float(divisor) == 0.0:
            raise ValidationError("division by zero", field="percent")
        return Percent(self.value / float(divisor))

    def __neg__(self) -> Percent:
        return Percent(-self.value)

    def __abs__(self) -> Percent:
        return Percent(abs(self.value))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Percent):
            return NotImplemented
        return math.isclose(self.value, other.value, rel_tol=1e-12, abs_tol=1e-12)

    def __hash__(self) -> int:
        return hash(round(self.value, 9))

    def __lt__(self, other: Percent) -> bool:
        return self.value < other.value and self != other

    def __le__(self, other: Percent) -> bool:
        return self.value <= other.value or self == other

    def __gt__(self, other: Percent) -> bool:
        return not self <= other

    def __ge__(self, other: Percent) -> bool:
        return not self < other

    def format(self, digits: int = 1) -> str:
        """Print to ``digits`` decimal places with the sign."""
        return f"{self.value:.{digits}f}%"

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Percent({self.value!r})"

    def __bool__(self) -> bool:
        return not math.isclose(self.value, 0.0, abs_tol=1e-12)
