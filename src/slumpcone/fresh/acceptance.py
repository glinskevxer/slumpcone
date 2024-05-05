"""Judging a load on its fresh tests, including the one retest it is allowed.

C94 gives a load exactly one second chance. A slump or air result outside the
band may be checked immediately with a fresh sample from the same load, and if
that one passes the load is accepted. If it fails, the load is rejected and no
third sample counts.

The rule is per property, not per load. A load that failed slump, was retested
and passed, and then failed air has used its slump retest and still has its air
retest available. Collapsing that into one flag is how a plant ends up
rejecting concrete it was entitled to place.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.mixdesign.design import MixDesign
from slumpcone.tolerance import Band, Side


class PropertyOutcome(Enum):
    """Where one property ended up after every sample on it."""

    NOT_TESTED = "not_tested"
    PASSED = "passed"
    PASSED_ON_RETEST = "passed_on_retest"
    RETEST_DUE = "retest_due"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value

    @property
    def is_settled(self) -> bool:
        """True when no further sample will change this."""
        return self in {
            PropertyOutcome.PASSED,
            PropertyOutcome.PASSED_ON_RETEST,
            PropertyOutcome.FAILED,
        }

    @property
    def is_acceptable(self) -> bool:
        """True when the property does not stand in the way of placing the load."""
        return self in {
            PropertyOutcome.NOT_TESTED,
            PropertyOutcome.PASSED,
            PropertyOutcome.PASSED_ON_RETEST,
        }


class LoadOutcome(Enum):
    """What happens to the load."""

    NOT_TESTED = "not_tested"
    ACCEPTED = "accepted"
    RETEST_DUE = "retest_due"
    REJECTED = "rejected"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PropertyVerdict:
    """One property, its samples in order, and where it ended up."""

    kind: str
    band: Band
    readings: tuple[float, ...]
    sides: tuple[Side, ...]
    outcome: PropertyOutcome

    @property
    def first(self) -> float | None:
        """The first reading taken, or ``None`` when nothing was."""
        return self.readings[0] if self.readings else None

    @property
    def governing(self) -> float | None:
        """The reading the outcome rests on."""
        return self.readings[-1] if self.readings else None

    def describe(self) -> str:
        """One line for a field log."""
        if not self.readings:
            return f"{self.kind}: not tested"
        taken = ", ".join(f"{value:g}" for value in self.readings)
        return f"{self.kind}: {taken} against {self.band.format(1)} -> {self.outcome}"


@dataclass(frozen=True, slots=True)
class LoadVerdict:
    """Every tested property on one load, and what it adds up to."""

    ticket_number: str
    properties: tuple[PropertyVerdict, ...]
    outcome: LoadOutcome

    def property_for(self, kind: str) -> PropertyVerdict | None:
        """One property's verdict by name."""
        for candidate in self.properties:
            if candidate.kind == kind:
                return candidate
        return None

    @property
    def failures(self) -> tuple[PropertyVerdict, ...]:
        """Every property that rejected the load."""
        return tuple(p for p in self.properties if p.outcome is PropertyOutcome.FAILED)

    def describe(self) -> str:
        """The load and each property, as plain text."""
        lines = [f"ticket {self.ticket_number}: {self.outcome}"]
        lines.extend(f"  {p.describe()}" for p in self.properties)
        return "\n".join(lines)


def _judge_series(kind: str, band: Band, readings: tuple[float, ...]) -> PropertyVerdict:
    sides = tuple(band.side(value) for value in readings)
    if not readings:
        return PropertyVerdict(kind, band, readings, sides, PropertyOutcome.NOT_TESTED)
    if sides[0] is Side.IN:
        return PropertyVerdict(kind, band, readings[:1], sides[:1], PropertyOutcome.PASSED)
    if len(readings) == 1:
        return PropertyVerdict(kind, band, readings, sides, PropertyOutcome.RETEST_DUE)
    if sides[1] is Side.IN:
        return PropertyVerdict(
            kind, band, readings[:2], sides[:2], PropertyOutcome.PASSED_ON_RETEST
        )
    return PropertyVerdict(kind, band, readings[:2], sides[:2], PropertyOutcome.FAILED)


def _readings(tests: Iterable[FreshTest], kinds: set[FreshTestKind]) -> tuple[float, ...]:
    chosen = sorted(
        (t for t in tests if t.kind in kinds), key=lambda t: (t.taken_at, t.is_retest)
    )
    values: list[float] = []
    for test in chosen:
        if test.kind is FreshTestKind.SLUMP and test.slump is not None:
            values.append(test.slump.to("in").value)
        elif test.kind.is_air and test.air is not None:
            values.append(test.air.value)
    return tuple(values)


def judge_load(
    ticket_number: str, tests: Iterable[FreshTest], design: MixDesign
) -> LoadVerdict:
    """Judge one load's fresh tests against the design's own bands."""
    collected = list(tests)
    for test in collected:
        if test.ticket_number != ticket_number:
            raise ValidationError(
                f"test on ticket {test.ticket_number} handed in for {ticket_number}",
                field="ticket_number",
            )
    properties: list[PropertyVerdict] = []
    slump_readings = _readings(collected, {FreshTestKind.SLUMP})
    properties.append(_judge_series("slump", design.slump_tolerance(), slump_readings))
    air_band = design.air_tolerance()
    if air_band is not None:
        air_readings = _readings(
            collected, {FreshTestKind.AIR_PRESSURE, FreshTestKind.AIR_VOLUMETRIC}
        )
        properties.append(_judge_series("air", air_band, air_readings))
    outcomes = [p.outcome for p in properties]
    if any(outcome is PropertyOutcome.FAILED for outcome in outcomes):
        overall = LoadOutcome.REJECTED
    elif any(outcome is PropertyOutcome.RETEST_DUE for outcome in outcomes):
        overall = LoadOutcome.RETEST_DUE
    elif all(outcome is PropertyOutcome.NOT_TESTED for outcome in outcomes):
        overall = LoadOutcome.NOT_TESTED
    else:
        overall = LoadOutcome.ACCEPTED
    return LoadVerdict(ticket_number, tuple(properties), overall)
