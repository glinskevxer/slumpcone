"""Moisture probes, and whether the number they are reporting can be trusted.

A batch panel reads free moisture off a probe buried in the sand bin, and every
batch that day is corrected by that number. It is the single most leveraged
reading in the plant: a probe half a percent out moves the water in every load,
which moves the ratio, which moves the strength, and nothing downstream will
ever point at the probe.

Probes drift. They drift with the material, with the temperature, and with
whatever built up on the face of the sensor. So the reading is only worth
anything alongside the last time somebody checked it against an oven dry sample
by C566, and this module is about that check rather than about the reading.

Three things are kept apart here on purpose.

The **offset** is the difference between what the probe said and what the oven
said, on one occasion. It is one measurement and it has noise in it.

The **drift** is how the offset has moved across checks. A probe that reads a
steady quarter percent high is fine and can be corrected in software. One whose
offset moved a full percent in a fortnight is failing, even if today's offset
happens to be small.

The **standing** is whether the plant may use the probe at all today, which
turns on when it was last checked rather than on how good the last check was. A
probe with a beautiful offset from four months ago is out of calibration.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.errors import RuleViolationError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent

# How long a check stands for. Nothing in ASTM sets this; plants pick a month
# and the ones that pick a quarter find out why they should not have.
CHECK_VALID_DAYS = 30

# An offset larger than this is not drift, it is a broken probe.
OFFSET_LIMIT = Percent(1.0)

# And a probe whose offsets have spread this far across checks is on its way out.
DRIFT_LIMIT = Percent(0.5)


class ProbeError(RuleViolationError):
    """A probe reading or check that cannot be used."""


class ProbeStanding(Enum):
    """Whether the plant may batch off this probe today."""

    GOOD = "good"
    DUE = "due for a check"
    OVERDUE = "overdue, do not batch off it"
    FAILED = "failed its last check"

    def __str__(self) -> str:
        return self.value

    @property
    def may_batch(self) -> bool:
        """Whether a plant may still correct a batch off this probe.

        Due counts. A probe whose check is booked for next week has not become
        unreliable overnight, and refusing it would mean a plant stops batching
        because a technician is on holiday. What refuses is overdue, which is a
        check that did not happen, and failed, which is a check that did.
        """
        return self in {ProbeStanding.GOOD, ProbeStanding.DUE}

    @property
    def needs_attention(self) -> bool:
        """Everything but good needs somebody to do something."""
        return self is not ProbeStanding.GOOD


@dataclass(frozen=True, slots=True)
class ProbeCheck:
    """One comparison of a probe against an oven dried sample."""

    probe_code: str
    checked_on: date
    probe_reading: Percent
    oven_reading: Percent
    technician: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "probe_code", normalize_code(self.probe_code, field="probe_code")
        )
        for name, value in (("probe", self.probe_reading), ("oven", self.oven_reading)):
            if value.value < 0.0:
                raise ProbeError(
                    "PROBE_NEGATIVE_MOISTURE",
                    f"the {name} reading cannot be negative moisture",
                )
            if value.value > 30.0:
                raise ProbeError(
                    "PROBE_MOISTURE_OFF_SCALE",
                    f"the {name} reading of {value.format(1)} is not aggregate moisture",
                )

    @property
    def offset(self) -> Percent:
        """How far the probe was out. Positive means the probe read high."""
        return Percent(self.probe_reading.value - self.oven_reading.value)

    @property
    def reads_high(self) -> bool:
        """Whether the probe overstates the water, which underbatches it."""
        return self.offset.value > 0.0

    @property
    def is_within_limit(self) -> bool:
        """Whether one check on its own passes."""
        return abs(self.offset.value) <= OFFSET_LIMIT.value + 1e-9

    def days_since(self, on: date) -> int:
        """How long ago this check was."""
        return (on - self.checked_on).days

    def describe(self) -> str:
        """One line."""
        direction = "high" if self.reads_high else "low"
        verdict = "within limit" if self.is_within_limit else "out of limit"
        return (
            f"{self.probe_code} on {self.checked_on.isoformat()}: reads "
            f"{abs(self.offset.value):.2f} points {direction}, {verdict}"
        )


@dataclass(frozen=True, slots=True)
class ProbeHistory:
    """Every check on one probe, and what they say together."""

    probe_code: str
    checks: tuple[ProbeCheck, ...]

    def __post_init__(self) -> None:
        wrong = [one for one in self.checks if one.probe_code != self.probe_code]
        if wrong:
            raise ProbeError(
                "PROBE_HISTORY_MIXED",
                f"{self.probe_code} history carries a check for {wrong[0].probe_code}",
            )

    @property
    def latest(self) -> ProbeCheck | None:
        """The most recent check."""
        if not self.checks:
            return None
        return max(self.checks, key=lambda one: one.checked_on)

    @property
    def mean_offset(self) -> Percent:
        """The average offset, which is what a software correction would use."""
        if not self.checks:
            return Percent(0.0)
        return Percent(statistics.fmean(one.offset.value for one in self.checks))

    @property
    def drift(self) -> Percent:
        """How far the offset has moved across checks, high to low.

        Deliberately the spread rather than a fitted slope. Plants check probes
        a handful of times a year at irregular intervals, and a slope fitted to
        five points at uneven spacing says more about the spacing than about the
        probe.
        """
        if len(self.checks) < 2:
            return Percent(0.0)
        offsets = [one.offset.value for one in self.checks]
        return Percent(max(offsets) - min(offsets))

    @property
    def is_drifting(self) -> bool:
        """Whether the offset has moved further than a probe's should."""
        return self.drift.value > DRIFT_LIMIT.value + 1e-9

    def standing(self, on: date, *, valid_days: int = CHECK_VALID_DAYS) -> ProbeStanding:
        """Whether the plant may batch off this probe today.

        A probe that has never been checked is overdue rather than failed. The
        difference matters: one needs a technician with an oven, the other needs
        a new probe.
        """
        last = self.latest
        if last is None:
            return ProbeStanding.OVERDUE
        if not last.is_within_limit:
            return ProbeStanding.FAILED
        age = last.days_since(on)
        if age > valid_days:
            return ProbeStanding.OVERDUE
        if age > valid_days - 7:
            return ProbeStanding.DUE
        return ProbeStanding.GOOD

    def corrected(self, reading: Percent, on: date) -> Percent:
        """A probe reading with the standing offset taken off it.

        Refuses on a probe the plant may not batch off. Correcting a reading
        from an overdue probe produces a number that looks corrected and is not
        trustworthy, which is worse than no number.
        """
        standing = self.standing(on)
        if not standing.may_batch:
            raise ProbeError(
                "PROBE_NOT_IN_STANDING",
                f"{self.probe_code} is {standing}, so its reading cannot be corrected",
            )
        return Percent(max(0.0, reading.value - self.mean_offset.value))

    def describe(self, on: date) -> str:
        """One line."""
        return (
            f"{self.probe_code}: {len(self.checks)} check(s), mean offset "
            f"{self.mean_offset.value:+.2f}, drift {self.drift.value:.2f}, "
            f"{self.standing(on)}"
        )


def history_for(probe_code: str, checks: Sequence[ProbeCheck]) -> ProbeHistory:
    """Gather one probe's checks out of a pile of them."""
    key = normalize_code(probe_code, field="probe_code")
    return ProbeHistory(key, tuple(one for one in checks if one.probe_code == key))


def probes_needing_attention(
    histories: Sequence[ProbeHistory], on: date
) -> tuple[ProbeHistory, ...]:
    """Every probe that is not in good standing, worst first."""
    order = {
        ProbeStanding.FAILED: 0,
        ProbeStanding.OVERDUE: 1,
        ProbeStanding.DUE: 2,
        ProbeStanding.GOOD: 3,
    }
    return tuple(
        sorted(
            (one for one in histories if one.standing(on).needs_attention),
            key=lambda one: (order[one.standing(on)], one.probe_code),
        )
    )
