"""Sieve analysis, and the two things it decides.

A gradation is a list of percentages passing a stack of sieves. Two numbers
come out of it that the rest of the register depends on. The fineness modulus
sets the fine aggregate proportion a mix design starts from, and the nominal
maximum size caps the aggregate a placement can take.

Both are computed here rather than typed in, because a fineness modulus typed
in beside the sieve data it disagrees with is the kind of thing that survives
for years.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True, order=False)
class Sieve:
    """One sieve in the standard stack, identified by its opening."""

    label: str
    opening_mm: float

    def __lt__(self, other: Sieve) -> bool:
        return self.opening_mm < other.opening_mm

    def __le__(self, other: Sieve) -> bool:
        return self.opening_mm <= other.opening_mm

    def __gt__(self, other: Sieve) -> bool:
        return self.opening_mm > other.opening_mm

    def __ge__(self, other: Sieve) -> bool:
        return self.opening_mm >= other.opening_mm

    @property
    def opening(self) -> Quantity:
        """The opening as a length."""
        return Quantity(self.opening_mm, "mm")

    def __str__(self) -> str:
        return self.label


# Coarse to fine, which is the order a sieve stack is built and the order every
# report prints. Nothing here should ever be sorted the other way.
SIEVES: tuple[Sieve, ...] = (
    Sieve("4 in", 100.0),
    Sieve("3-1/2 in", 90.0),
    Sieve("3 in", 75.0),
    Sieve("2-1/2 in", 63.0),
    Sieve("2 in", 50.0),
    Sieve("1-1/2 in", 37.5),
    Sieve("1 in", 25.0),
    Sieve("3/4 in", 19.0),
    Sieve("1/2 in", 12.5),
    Sieve("3/8 in", 9.5),
    Sieve("No. 4", 4.75),
    Sieve("No. 8", 2.36),
    Sieve("No. 16", 1.18),
    Sieve("No. 30", 0.600),
    Sieve("No. 50", 0.300),
    Sieve("No. 100", 0.150),
    Sieve("No. 200", 0.075),
)

_BY_LABEL: dict[str, Sieve] = {s.label: s for s in SIEVES}

# The fineness modulus is the sum of cumulative percentages retained on this
# subset only. Adding a sieve to the stack does not change it, which is the
# whole point of fixing the list.
_FM_SIEVES: tuple[str, ...] = (
    "3 in",
    "1-1/2 in",
    "3/4 in",
    "3/8 in",
    "No. 4",
    "No. 8",
    "No. 16",
    "No. 30",
    "No. 50",
    "No. 100",
)


def sieve(label: str) -> Sieve:
    """The sieve with this label. Accepts a few spellings of the same thing."""
    key = " ".join(label.strip().split())
    if key in _BY_LABEL:
        return _BY_LABEL[key]
    folded = key.upper().replace("#", "NO. ").replace("NO.", "NO. ")
    folded = " ".join(folded.split())
    for candidate in SIEVES:
        if candidate.label.upper() == folded:
            return candidate
    raise ValidationError(f"unknown sieve {label!r}", field="sieve")


@dataclass(frozen=True, slots=True)
class Gradation:
    """Percent passing each sieve that was run, coarse to fine."""

    passing: tuple[tuple[Sieve, Percent], ...]

    def __post_init__(self) -> None:
        if not self.passing:
            raise ValidationError("a gradation needs at least one sieve", field="passing")
        seen: set[str] = set()
        previous: Percent | None = None
        for sieve_, percent in self.passing:
            if sieve_.label in seen:
                raise ValidationError(f"sieve {sieve_} appears twice", field="passing")
            seen.add(sieve_.label)
            if not 0.0 <= percent.value <= 100.0:
                raise ValidationError(
                    f"percent passing {sieve_} is {percent}, outside 0 to 100", field="passing"
                )
            if previous is not None and percent > previous:
                raise ValidationError(
                    f"percent passing rises at {sieve_}, which a sieve stack cannot do",
                    field="passing",
                )
            previous = percent
        ordered = sorted(self.passing, key=lambda pair: pair[0].opening_mm, reverse=True)
        if [p[0].label for p in ordered] != [p[0].label for p in self.passing]:
            raise ValidationError("a gradation runs coarse to fine", field="passing")

    @classmethod
    def of(cls, readings: dict[str, float]) -> Gradation:
        """Build from ``{"1 in": 100.0, "3/4 in": 92.0, ...}``."""
        pairs = [(sieve(label), Percent(value)) for label, value in readings.items()]
        pairs.sort(key=lambda pair: pair[0].opening_mm, reverse=True)
        return cls(tuple(pairs))

    def passing_on(self, label: str) -> Percent | None:
        """Percent passing one sieve, or ``None`` when it was not run."""
        target = sieve(label)
        for sieve_, percent in self.passing:
            if sieve_ == target:
                return percent
        return None

    def retained_on(self, label: str) -> Percent | None:
        """Cumulative percent retained on one sieve."""
        passing = self.passing_on(label)
        if passing is None:
            return None
        return Percent(100.0) - passing

    @property
    def fineness_modulus(self) -> float:
        """The fineness modulus, to two decimals as the standard reports it.

        Every sieve in the fixed list has to have been run. A stack missing the
        No. 100 gives a number two tenths low, and two tenths of fineness
        modulus moves a sand proportion by about fifteen pounds.
        """
        total = 0.0
        for label in _FM_SIEVES:
            passing = self.passing_on(label)
            if passing is None:
                if sieve(label).opening_mm > self.coarsest.opening_mm:
                    continue
                raise ValidationError(
                    f"the stack is missing {label}, so it has no fineness modulus",
                    field="passing",
                )
            total += 100.0 - passing.value
        return round(total / 100.0, 2)

    @property
    def coarsest(self) -> Sieve:
        """The largest sieve that was run."""
        return self.passing[0][0]

    @property
    def finest(self) -> Sieve:
        """The smallest sieve that was run."""
        return self.passing[-1][0]

    @property
    def nominal_max_size(self) -> Sieve:
        """The smallest sieve that retains no more than ten percent.

        This is the aggregate size a specification writes, and it is not the
        largest sieve in the stack. A number 57 stone runs on a 1-1/2 inch
        sieve at 100 percent and is a one inch aggregate.
        """
        chosen = self.coarsest
        for sieve_, percent in self.passing:
            if percent.value >= 90.0:
                chosen = sieve_
            else:
                break
        return chosen

    def describe(self) -> str:
        """A one line summary for a listing."""
        head = ", ".join(f"{s}={p.format(0)}" for s, p in self.passing[:4])
        return f"{self.nominal_max_size} nominal, {head}"
