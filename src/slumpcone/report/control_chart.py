"""Control charts, in text, because that is where they get read.

Three charts off one record. The individual chart plots every test with limits
three deviations either side of the mean, and it answers "is anything odd".
The moving average of three plots the number the acceptance rule runs on, and
it answers "is the mixture where it should be". The moving range plots the gap
between consecutive tests, and it answers "is the process steady", which is a
different question from either.

They are drawn as fixed width bars rather than as a picture. A quality manager
reads these in an email, on a phone, or printed on a plant's own printer, and a
chart that needs a browser is a chart nobody looks at.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.strength.tests import StrengthTest
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity

# How wide the drawn bar is, in characters.
CHART_WIDTH = 40

# How many deviations either side of the mean the control limits sit.
SIGMA_LIMITS = 3.0

MOVING_WINDOW = 3


@dataclass(frozen=True, slots=True)
class ChartPoint:
    """One point on a chart."""

    label: str
    value: float
    inside: bool = True


@dataclass(frozen=True, slots=True)
class ControlChart:
    """One chart: its points, its centre line and its limits."""

    title: str
    points: tuple[ChartPoint, ...]
    centre: float
    lower: float | None
    upper: float | None
    unit: str = "psi"

    @property
    def outside(self) -> tuple[ChartPoint, ...]:
        """Every point beyond a limit."""
        return tuple(point for point in self.points if not point.inside)

    @property
    def is_in_control(self) -> bool:
        """True when nothing has gone outside the limits."""
        return not self.outside

    def _scale(self) -> tuple[float, float]:
        values = [point.value for point in self.points]
        candidates = [*values, self.centre]
        if self.lower is not None:
            candidates.append(self.lower)
        if self.upper is not None:
            candidates.append(self.upper)
        low, high = min(candidates), max(candidates)
        if math.isclose(low, high):
            return (low - 1.0, high + 1.0)
        margin = (high - low) * 0.05
        return (low - margin, high + margin)

    def bar(self, value: float) -> str:
        """One point drawn as a bar, scaled to the chart."""
        low, high = self._scale()
        share = (value - low) / (high - low)
        filled = max(0, min(CHART_WIDTH, round(share * CHART_WIDTH)))
        return "#" * filled + "." * (CHART_WIDTH - filled)

    def render(self) -> str:
        """The chart as a table."""
        columns = (
            Column("point"),
            Column("value", Align.RIGHT),
            Column(f"0 to {CHART_WIDTH}"),
            Column(""),
        )
        rows = [
            [
                point.label,
                f"{point.value:.0f}",
                self.bar(point.value),
                "" if point.inside else "out",
            ]
            for point in self.points
        ]
        header = render_pairs(
            [
                ("centre", f"{self.centre:.0f} {self.unit}"),
                ("lower limit", "-" if self.lower is None else f"{self.lower:.0f}"),
                ("upper limit", "-" if self.upper is None else f"{self.upper:.0f}"),
                ("in control", "yes" if self.is_in_control else "no"),
            ]
        )
        return "\n".join(
            [heading(self.title, underline="-"), header, "", render_table(columns, rows)]
        )


def _usable(tests: Sequence[StrengthTest]) -> list[StrengthTest]:
    usable = [test for test in tests if test.counts_for_acceptance]
    if len(usable) < 2:
        raise ValidationError("a chart needs at least two tests", field="tests")
    return sorted(usable, key=lambda test: (test.tested_on, test.set_code))


def individual_chart(tests: Sequence[StrengthTest]) -> ControlChart:
    """Every test, with limits three deviations either side of the mean."""
    usable = _usable(tests)
    values = [test.average.to("psi").value for test in usable]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    deviation = math.sqrt(variance)
    lower = mean - SIGMA_LIMITS * deviation
    upper = mean + SIGMA_LIMITS * deviation
    points = tuple(
        ChartPoint(test.set_code, value, lower <= value <= upper)
        for test, value in zip(usable, values, strict=True)
    )
    return ControlChart("Individual tests", points, mean, lower, upper)


def moving_average_chart(tests: Sequence[StrengthTest], specified: Quantity) -> ControlChart:
    """The average of three consecutive tests, against the specified strength."""
    usable = _usable(tests)
    values = [test.average.to("psi").value for test in usable]
    if len(values) < MOVING_WINDOW:
        raise ValidationError(
            f"a moving average needs at least {MOVING_WINDOW} tests", field="tests"
        )
    floor = specified.to("psi").value
    points: list[ChartPoint] = []
    for index in range(len(values) - MOVING_WINDOW + 1):
        window = values[index : index + MOVING_WINDOW]
        average = sum(window) / MOVING_WINDOW
        label = usable[index + MOVING_WINDOW - 1].set_code
        points.append(ChartPoint(label, average, average >= floor))
    centre = sum(point.value for point in points) / len(points)
    return ControlChart("Moving average of three", tuple(points), centre, floor, None)


def moving_range_chart(tests: Sequence[StrengthTest]) -> ControlChart:
    """The gap between consecutive tests, with the usual upper limit.

    The limit is the average range times a constant that comes from the same
    table as the range constants: for a range over two results it is 3.267.
    """
    usable = _usable(tests)
    values = [test.average.to("psi").value for test in usable]
    ranges = [abs(later - earlier) for earlier, later in zip(values, values[1:], strict=False)]
    average = sum(ranges) / len(ranges)
    upper = 3.267 * average
    points = tuple(
        ChartPoint(usable[index + 1].set_code, value, value <= upper)
        for index, value in enumerate(ranges)
    )
    return ControlChart("Moving range", points, average, None, upper)


def render_control_report(
    mix_code: str, tests: Sequence[StrengthTest], specified: Quantity
) -> str:
    """All three charts, one after another."""
    parts = [heading(f"Control charts for {mix_code}")]
    parts.append(individual_chart(tests).render())
    usable = [test for test in tests if test.counts_for_acceptance]
    if len(usable) >= MOVING_WINDOW:
        parts.append("")
        parts.append(moving_average_chart(tests, specified).render())
    parts.append("")
    parts.append(moving_range_chart(tests).render())
    return "\n".join(parts)
