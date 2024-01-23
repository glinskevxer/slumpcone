"""Tolerance bands, which in this trade are rarely symmetric.

A slump specification of 4 inches plus or minus 1 is symmetric. A slump
specification with a maximum of 5 inches and no minimum is one-sided. C94's
weighing tolerance on cement is the greater of one percent of the required
weight and three tenths of one percent of the scale capacity, which is neither.

All three are the same question -- is this reading inside the band -- so they
are all the same type, and the band is built by whoever knows the rule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError


class Side(Enum):
    """Which way a reading missed its band."""

    LOW = "low"
    IN = "in"
    HIGH = "high"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Band:
    """A target with a low and a high allowance, either of which may be open.

    ``minus`` and ``plus`` are non-negative allowances away from ``target``.
    ``None`` on either side means that side is not bounded at all.
    """

    target: float
    minus: float | None
    plus: float | None

    def __post_init__(self) -> None:
        if not math.isfinite(self.target):
            raise ValidationError("a band target has to be finite", field="target")
        for name, allowance in (("minus", self.minus), ("plus", self.plus)):
            if allowance is None:
                continue
            if not math.isfinite(allowance):
                raise ValidationError(f"the {name} allowance has to be finite", field=name)
            if allowance < 0.0:
                raise ValidationError(f"the {name} allowance cannot be negative", field=name)
        if self.minus is None and self.plus is None:
            raise ValidationError("a band open on both sides is not a band", field="band")

    @classmethod
    def symmetric(cls, target: float, allowance: float) -> Band:
        """``target`` plus or minus ``allowance``."""
        return cls(target, allowance, allowance)

    @classmethod
    def at_most(cls, limit: float) -> Band:
        """No lower bound, nothing above ``limit``."""
        return cls(limit, None, 0.0)

    @classmethod
    def at_least(cls, limit: float) -> Band:
        """No upper bound, nothing below ``limit``."""
        return cls(limit, 0.0, None)

    @classmethod
    def between(cls, low: float, high: float) -> Band:
        """Everything from ``low`` to ``high``, target at the midpoint."""
        if high < low:
            raise ValidationError(
                "the high end of a band cannot be below the low", field="band"
            )
        middle = (low + high) / 2.0
        return cls(middle, middle - low, high - middle)

    @property
    def low(self) -> float | None:
        """The lowest acceptable reading, or ``None`` when unbounded below."""
        if self.minus is None:
            return None
        return self.target - self.minus

    @property
    def high(self) -> float | None:
        """The highest acceptable reading, or ``None`` when unbounded above."""
        if self.plus is None:
            return None
        return self.target + self.plus

    def side(self, reading: float, *, epsilon: float = 1e-9) -> Side:
        """Which side of the band ``reading`` fell on.

        The epsilon matters. Readings are recorded to a quarter inch and a tenth
        of a percent, and a band edge computed from a percentage lands a float
        ulp below the reading often enough that an exact comparison rejects
        loads that passed.
        """
        low, high = self.low, self.high
        if low is not None and reading < low - epsilon:
            return Side.LOW
        if high is not None and reading > high + epsilon:
            return Side.HIGH
        return Side.IN

    def contains(self, reading: float, *, epsilon: float = 1e-9) -> bool:
        """True when ``reading`` is inside the band."""
        return self.side(reading, epsilon=epsilon) is Side.IN

    def deviation(self, reading: float) -> float:
        """How far outside the band ``reading`` is, signed. Zero when inside."""
        low, high = self.low, self.high
        if low is not None and reading < low:
            return reading - low
        if high is not None and reading > high:
            return reading - high
        return 0.0

    def clamp(self, reading: float) -> float:
        """``reading`` pulled to the nearest edge of the band."""
        low, high = self.low, self.high
        if low is not None and reading < low:
            return low
        if high is not None and reading > high:
            return high
        return reading

    def widen(self, extra: float) -> Band:
        """The same band with ``extra`` added to whichever sides are bounded."""
        if extra < 0.0:
            raise ValidationError("cannot widen a band by a negative amount", field="extra")
        return Band(
            self.target,
            None if self.minus is None else self.minus + extra,
            None if self.plus is None else self.plus + extra,
        )

    def format(self, digits: int = 2, unit: str = "") -> str:
        """Print the band the way a specification writes it."""
        suffix = f" {unit}" if unit else ""

        def show(value: float) -> str:
            return f"{value:.{digits}f}"

        if self.minus is None:
            return f"at most {show(self.target + (self.plus or 0.0))}{suffix}"
        if self.plus is None:
            return f"at least {show(self.target - self.minus)}{suffix}"
        if math.isclose(self.minus, self.plus):
            return f"{show(self.target)} +/- {show(self.plus)}{suffix}"
        return f"{show(self.target)} +{show(self.plus)} -{show(self.minus)}{suffix}"

    def __str__(self) -> str:
        return self.format()
