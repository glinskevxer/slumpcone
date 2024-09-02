"""The strength report a producer hands to an engineer.

Three tables and a header block. The tests as they were broken, the moving
averages the acceptance rule runs on, and any individual test that fell through
the floor. Nothing is summarised away: an engineer reading this wants to see
the numbers the verdict was computed from, because the verdict on its own is
not something anybody can check.

The header block carries the standard deviation and the required average
strength the record supports, because the two questions that follow a strength
report are always "is it acceptable" and "what should the mixture be
proportioned to now".
"""

from __future__ import annotations

from collections.abc import Sequence

from slumpcone.strength.acceptance import AcceptanceReport, evaluate_strength
from slumpcone.strength.required import (
    MIN_RECORD_TESTS,
    required_average_strength,
    sample_standard_deviation,
)
from slumpcone.strength.tests import StrengthTest
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity


def render_tests(tests: Sequence[StrengthTest]) -> str:
    """Every test in the record, oldest first."""
    columns = (
        Column("set"),
        Column("broken"),
        Column("age", Align.RIGHT),
        Column("result", Align.RIGHT),
        Column("low", Align.RIGHT),
        Column("high", Align.RIGHT),
        Column("spread", Align.RIGHT),
        Column("n", Align.RIGHT),
    )
    rows = [
        [
            test.set_code,
            test.tested_on.isoformat(),
            f"{test.age_days:g}",
            test.average.format(0),
            test.lowest.format(0),
            test.highest.format(0),
            test.within_test_range_percent.format(1),
            len(test.breaks),
        ]
        for test in tests
    ]
    return render_table(columns, rows)


def render_moving_averages(report: AcceptanceReport) -> str:
    """The windows of three the acceptance rule runs on."""
    columns = (
        Column("window"),
        Column("average", Align.RIGHT),
        Column("margin", Align.RIGHT),
        Column("verdict"),
    )
    rows = [
        [
            ", ".join(window.set_codes),
            window.average.format(0),
            window.margin.format(0),
            "ok" if window.meets else "below",
        ]
        for window in report.windows
    ]
    return render_table(columns, rows)


def render_low_tests(report: AcceptanceReport) -> str:
    """Individual tests that fell below the floor."""
    columns = (
        Column("set"),
        Column("result", Align.RIGHT),
        Column("floor", Align.RIGHT),
        Column("short by", Align.RIGHT),
    )
    rows = [
        [low.set_code, low.result.format(0), low.floor.format(0), low.shortfall.format(0)]
        for low in report.low_tests
    ]
    return render_table(columns, rows)


def render_header(report: AcceptanceReport) -> str:
    """The block above the tables."""
    strengths = [test.average for test in report.tests]
    pairs: list[tuple[str, object]] = [
        ("mix", report.mix_code),
        ("specified", report.specified.format(0)),
        ("tests", len(report.tests)),
        ("status", str(report.status)),
    ]
    if len(strengths) >= 2:
        deviation = sample_standard_deviation(strengths)
        pairs.append(("standard deviation", deviation.format(0)))
    if len(strengths) >= MIN_RECORD_TESTS:
        required = required_average_strength(report.specified, strengths)
        pairs.append(("required average", required.required.format(0)))
        pairs.append(("basis", required.basis))
    return render_pairs(pairs)


def render_report(report: AcceptanceReport) -> str:
    """The whole report as plain text."""
    parts = [heading(f"Strength record for {report.mix_code}"), render_header(report)]
    if report.tests:
        parts.extend(["", heading("Tests", underline="-"), render_tests(report.tests)])
    if report.windows:
        parts.extend(
            [
                "",
                heading("Moving averages of three", underline="-"),
                render_moving_averages(report),
            ]
        )
    if report.low_tests:
        parts.extend(
            [
                "",
                heading("Individual tests below the floor", underline="-"),
                render_low_tests(report),
            ]
        )
    if report.reasons:
        parts.extend(["", "Findings:"])
        parts.extend(f"  {reason}" for reason in report.reasons)
    return "\n".join(parts)


def strength_report(mix_code: str, tests: Sequence[StrengthTest], specified: Quantity) -> str:
    """Evaluate a mixture's record and render the whole report."""
    return render_report(evaluate_strength(mix_code, tests, specified))
