"""C33 grading requirements, by size number.

A coarse aggregate is bought as a size number and the size number is a set of
bands the sieve analysis has to land inside. A fine aggregate has one set of
bands and two extra rules that nothing else has: the fineness modulus has to sit
between 2.3 and 3.1, and it may not wander more than 0.20 from the value the
mix design was proportioned on.

That second rule is the one worth having code for. A sand that drifts coarse
still passes every band and still moves the mixture, and nobody notices until
the finishers complain.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.materials.gradation import Gradation
from slumpcone.percent import Percent
from slumpcone.tolerance import Band

FINE_AGGREGATE = "FA"

# Percent passing, low and high, for each sieve the size number names.
_LIMITS: dict[str, dict[str, tuple[float, float]]] = {
    "4": {
        "2 in": (100.0, 100.0),
        "1-1/2 in": (90.0, 100.0),
        "3/4 in": (20.0, 55.0),
        "1/2 in": (0.0, 15.0),
        "3/8 in": (0.0, 5.0),
    },
    "467": {
        "2 in": (100.0, 100.0),
        "1-1/2 in": (95.0, 100.0),
        "3/4 in": (35.0, 70.0),
        "No. 4": (0.0, 5.0),
    },
    "57": {
        "1-1/2 in": (100.0, 100.0),
        "1 in": (95.0, 100.0),
        "1/2 in": (25.0, 60.0),
        "No. 4": (0.0, 10.0),
        "No. 8": (0.0, 5.0),
    },
    "67": {
        "1 in": (100.0, 100.0),
        "3/4 in": (90.0, 100.0),
        "3/8 in": (20.0, 55.0),
        "No. 4": (0.0, 10.0),
        "No. 8": (0.0, 5.0),
    },
    "7": {
        "1 in": (100.0, 100.0),
        "3/4 in": (90.0, 100.0),
        "3/8 in": (40.0, 70.0),
        "No. 4": (0.0, 15.0),
        "No. 8": (0.0, 5.0),
    },
    "8": {
        "1/2 in": (100.0, 100.0),
        "3/8 in": (85.0, 100.0),
        "No. 4": (10.0, 30.0),
        "No. 8": (0.0, 10.0),
        "No. 16": (0.0, 5.0),
    },
    "89": {
        "1/2 in": (100.0, 100.0),
        "3/8 in": (90.0, 100.0),
        "No. 4": (20.0, 55.0),
        "No. 8": (5.0, 30.0),
        "No. 16": (0.0, 10.0),
        "No. 50": (0.0, 5.0),
    },
    FINE_AGGREGATE: {
        "3/8 in": (100.0, 100.0),
        "No. 4": (95.0, 100.0),
        "No. 8": (80.0, 100.0),
        "No. 16": (50.0, 85.0),
        "No. 30": (25.0, 60.0),
        "No. 50": (5.0, 30.0),
        "No. 100": (0.0, 10.0),
    },
}

FINENESS_MODULUS_BAND = Band.between(2.3, 3.1)

# How far a sand's fineness modulus may drift from the value the mix design was
# proportioned on before the proportions have to be revisited.
FINENESS_MODULUS_DRIFT = 0.20


def size_numbers() -> tuple[str, ...]:
    """Every size number this table knows, coarse first then the sand."""
    coarse = sorted((k for k in _LIMITS if k != FINE_AGGREGATE), key=lambda k: (len(k), k))
    return (*coarse, FINE_AGGREGATE)


def limits_for(size_number: str) -> dict[str, Band]:
    """The bands a size number requires, keyed by sieve label."""
    key = size_number.strip().upper().lstrip("#")
    table = _LIMITS.get(key)
    if table is None:
        raise ValidationError(
            f"unknown aggregate size number {size_number!r}", field="size_number"
        )
    return {label: Band.between(low, high) for label, (low, high) in table.items()}


@dataclass(frozen=True, slots=True)
class GradingFinding:
    """One sieve that did not land inside its band."""

    sieve_label: str
    measured: Percent | None
    band: Band

    @property
    def is_missing(self) -> bool:
        """True when the sieve was not run at all."""
        return self.measured is None

    def describe(self) -> str:
        """One line naming the sieve and what went wrong."""
        if self.measured is None:
            return f"{self.sieve_label}: not run, band is {self.band.format(0)} percent"
        return (
            f"{self.sieve_label}: {self.measured.format(1)} passing, "
            f"band is {self.band.format(0)} percent"
        )


def check_grading(grading: Gradation, size_number: str) -> tuple[GradingFinding, ...]:
    """Every sieve where ``grading`` misses the bands for ``size_number``."""
    findings: list[GradingFinding] = []
    for label, band in limits_for(size_number).items():
        measured = grading.passing_on(label)
        if measured is None or not band.contains(measured.value):
            findings.append(GradingFinding(label, measured, band))
    return tuple(findings)


def conforms(grading: Gradation, size_number: str) -> bool:
    """True when a gradation lands inside every band for its size number."""
    return not check_grading(grading, size_number)


def check_fineness_modulus(
    grading: Gradation, *, design_value: float | None = None
) -> tuple[str, ...]:
    """The complaints a sand's fineness modulus earns, if any.

    Two independent rules, and a sand can break either without breaking the
    other. Sitting outside 2.3 to 3.1 makes it unsuitable. Drifting more than
    0.20 from what the mix was proportioned on makes it different, which is a
    separate problem with a separate remedy.
    """
    modulus = grading.fineness_modulus
    complaints: list[str] = []
    if not FINENESS_MODULUS_BAND.contains(modulus):
        complaints.append(
            f"fineness modulus {modulus:.2f} is outside {FINENESS_MODULUS_BAND.format(1)}"
        )
    if design_value is not None:
        drift = abs(modulus - design_value)
        if drift > FINENESS_MODULUS_DRIFT + 1e-9:
            complaints.append(
                f"fineness modulus {modulus:.2f} is {drift:.2f} from the design "
                f"value {design_value:.2f}, the limit is {FINENESS_MODULUS_DRIFT:.2f}"
            )
    return tuple(complaints)
