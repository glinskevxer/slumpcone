"""Cusum, for the drift a Shewhart chart will not see.

An individuals chart catches a load that comes out badly. It is close to blind
to a mixture that has been drifting a hundred pounds low for two months, because
no single test ever leaves the limits. That drift is the expensive failure: it
is what a cement change or a wet sand pile does, and by the time an individuals
chart notices, the concrete is in the ground.

Cusum answers the question the individuals chart cannot: has the mean moved. It
runs a pair of running sums of the distance from target, one for the high side
and one for the low, each reset to zero whenever it would go the wrong way. The
slack term k is the drift the plant does not care about, and the decision limit
h is how much accumulated evidence it takes before the chart calls it.

The two parameters are quoted in standard deviations, not in psi, so a plant
with tight control gets a tighter chart without anybody retuning it. The usual
pair is half a standard deviation of slack against a limit of five, which
catches a one sigma shift in about ten tests.

What cusum will not do is tell you the shift is real. It tells you the evidence
has accumulated past a threshold somebody chose. So this module reports where
the run started as well as where it fired, because the start is what you go and
look at in the batch records.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from slumpcone.errors import RuleViolationError
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity

# The pair almost every text starts from: half a sigma of slack, five sigma of
# accumulated evidence before the chart says something.
DEFAULT_SLACK = 0.5
DEFAULT_LIMIT = 5.0

# Below this many tests, a fitted standard deviation is not worth using.
MINIMUM_TESTS = 8


class CusumError(RuleViolationError):
    """A cusum chart that cannot be drawn honestly."""


@dataclass(frozen=True, slots=True)
class CusumPoint:
    """One test, with both running sums after it."""

    label: str
    value: Quantity
    high: float
    low: float

    @property
    def worst(self) -> float:
        """Whichever side has accumulated more."""
        return max(self.high, self.low)

    def fired(self, limit: float) -> bool:
        """Whether either side has passed the decision limit."""
        return self.worst >= limit - 1e-9


@dataclass(frozen=True, slots=True)
class CusumRun:
    """A stretch where one side accumulated past the limit."""

    side: str
    started_at: int
    fired_at: int
    peak: float

    @property
    def length(self) -> int:
        """How many tests it took to accumulate."""
        return self.fired_at - self.started_at + 1

    def describe(self) -> str:
        """One line."""
        return (
            f"{self.side} shift: started at test {self.started_at + 1}, "
            f"called at test {self.fired_at + 1} after {self.length} test(s)"
        )


@dataclass(frozen=True, slots=True)
class CusumChart:
    """A whole chart, with the runs it found."""

    target: Quantity
    deviation: Quantity
    slack: float
    limit: float
    points: tuple[CusumPoint, ...]
    runs: tuple[CusumRun, ...]

    @property
    def slack_psi(self) -> float:
        """The slack in the units the plant reads."""
        return self.slack * self.deviation.to("psi").value

    @property
    def limit_psi(self) -> float:
        """The decision limit in the units the plant reads."""
        return self.limit * self.deviation.to("psi").value

    @property
    def is_stable(self) -> bool:
        """Whether the mean held throughout."""
        return not self.runs

    @property
    def low_runs(self) -> tuple[CusumRun, ...]:
        """The runs that went the way that matters, which is down."""
        return tuple(run for run in self.runs if run.side == "low")

    def first_low(self) -> CusumRun | None:
        """The first downward shift, which is the one to go and look at."""
        return self.low_runs[0] if self.low_runs else None

    def render(self, width: int = 40) -> str:
        """A text chart, one row per test, both sides against the limit."""
        rows = [f"target {self.target.format(0)}, limit {self.limit_psi:.0f} psi"]
        for index, point in enumerate(self.points):
            filled = min(width, int(round(width * point.worst / self.limit)))
            side = "-" if point.low >= point.high else "+"
            mark = "*" if point.fired(self.limit) else " "
            rows.append(f"{index + 1:>3} {point.label:<10} {side}{'#' * filled:<{width}}{mark}")
        return "\n".join(rows)

    def describe(self) -> str:
        """One line."""
        if self.is_stable:
            return f"{len(self.points)} test(s), no shift in the mean"
        return (
            f"{len(self.points)} test(s), {len(self.runs)} shift(s), "
            f"{len(self.low_runs)} of them downward"
        )


def build_cusum(
    tests: Sequence[StrengthTest],
    target: Quantity,
    *,
    deviation: Quantity | None = None,
    slack: float = DEFAULT_SLACK,
    limit: float = DEFAULT_LIMIT,
) -> CusumChart:
    """Run a cusum over a run of strength tests.

    ``deviation`` is the standard deviation the chart is scaled by. Handing one
    in uses the plant's established figure, which is the right thing when there
    is one. Leaving it out fits one from the tests themselves, which needs
    enough of them to mean anything and refuses when there are not.
    """
    if slack < 0.0:
        raise CusumError("CUSUM_NEGATIVE_SLACK", "slack cannot be negative")
    if limit <= 0.0:
        raise CusumError("CUSUM_NO_LIMIT", "a decision limit has to be positive")
    usable = sorted(
        (test for test in tests if test.counts_for_acceptance),
        key=lambda test: (test.tested_on, test.set_code),
    )
    if not usable:
        raise CusumError("CUSUM_NO_TESTS", "a cusum needs at least one acceptance test")

    values = [test.average.to("psi").value for test in usable]
    if deviation is None:
        if len(values) < MINIMUM_TESTS:
            raise CusumError(
                "CUSUM_TOO_FEW_TO_FIT",
                f"fitting a deviation wants {MINIMUM_TESTS} tests, found {len(values)}",
            )
        deviation = Quantity(statistics.stdev(values), "psi")
    if deviation.to("psi").value <= 0.0:
        raise CusumError(
            "CUSUM_NO_SPREAD", "a cusum needs a positive standard deviation to scale by"
        )

    sigma = deviation.to("psi").value
    aim = target.to("psi").value
    slack_psi = slack * sigma
    limit_psi = limit * sigma

    points: list[CusumPoint] = []
    runs: list[CusumRun] = []
    high = low = 0.0
    high_start = low_start = 0
    high_open = low_open = False

    for index, (test, value) in enumerate(zip(usable, values, strict=True)):
        if high <= 0.0:
            high_start = index
        if low <= 0.0:
            low_start = index
        high = max(0.0, high + (value - aim) - slack_psi)
        low = max(0.0, low + (aim - value) - slack_psi)
        points.append(
            CusumPoint(test.set_code, Quantity(value, "psi"), high / sigma, low / sigma)
        )
        if high >= limit_psi and not high_open:
            runs.append(CusumRun("high", high_start, index, high / sigma))
            high_open = True
        if high < limit_psi:
            high_open = False
        if low >= limit_psi and not low_open:
            runs.append(CusumRun("low", low_start, index, low / sigma))
            low_open = True
        if low < limit_psi:
            low_open = False

    return CusumChart(target, deviation, slack, limit, tuple(points), tuple(runs))
