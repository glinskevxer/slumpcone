from __future__ import annotations

import pytest

from slumpcone.report.strength_report import (
    render_header,
    render_low_tests,
    render_moving_averages,
    render_report,
    render_tests,
    strength_report,
)
from slumpcone.strength.acceptance import evaluate_strength
from slumpcone.units.quantity import Quantity
from tests.strength.test_acceptance import a_test

SPECIFIED = Quantity(4000, "psi")


def good_record() -> list[object]:
    return [a_test("S-1", 4500.0), a_test("S-2", 4600.0, 1), a_test("S-3", 4700.0, 2)]


def failing_record() -> list[object]:
    return [a_test("S-1", 5200.0), a_test("S-2", 3200.0, 1), a_test("S-3", 5300.0, 2)]


def report(tests: list[object]) -> object:
    return evaluate_strength("4000P-57", tests, SPECIFIED)  # type: ignore[arg-type]


class CaseTestsTable:
    def test_the_heading(self) -> None:
        text = render_tests(report(good_record()).tests)  # type: ignore[attr-defined]
        assert text.splitlines()[0].startswith("set")
        assert "spread" in text.splitlines()[0]

    def test_a_row_per_test(self) -> None:
        text = render_tests(report(good_record()).tests)  # type: ignore[attr-defined]
        assert len(text.splitlines()) == 5

    def test_the_results_are_printed(self) -> None:
        text = render_tests(report(good_record()).tests)  # type: ignore[attr-defined]
        assert "4500 psi" in text
        assert "S-1" in text

    def test_an_empty_record_still_prints_a_heading(self) -> None:
        assert render_tests([]).splitlines()[0].startswith("set")


class CaseMovingAverages:
    def test_a_window_per_three_tests(self) -> None:
        text = render_moving_averages(report(good_record()))  # type: ignore[arg-type]
        assert "S-1, S-2, S-3" in text
        assert "ok" in text

    def test_a_failing_window_says_below(self) -> None:
        low = [a_test("S-1", 3400.0), a_test("S-2", 3500.0, 1), a_test("S-3", 3600.0, 2)]
        text = render_moving_averages(report(low))  # type: ignore[arg-type]
        assert "below" in text


class CaseLowTests:
    def test_a_low_test_is_listed(self) -> None:
        text = render_low_tests(report(failing_record()))  # type: ignore[arg-type]
        assert "S-2" in text
        assert "3500 psi" in text

    def test_a_clean_record_lists_nothing(self) -> None:
        text = render_low_tests(report(good_record()))  # type: ignore[arg-type]
        assert len(text.splitlines()) == 2


class CaseHeader:
    def test_the_basics(self) -> None:
        text = render_header(report(good_record()))  # type: ignore[arg-type]
        assert "mix" in text
        assert "4000P-57" in text
        assert "specified" in text
        assert "satisfactory" in text

    def test_a_standard_deviation_appears_from_two_tests(self) -> None:
        text = render_header(report(good_record()))  # type: ignore[arg-type]
        assert "standard deviation" in text

    def test_a_single_test_has_no_deviation(self) -> None:
        text = render_header(report([a_test("S-1", 4500.0)]))  # type: ignore[arg-type]
        assert "standard deviation" not in text

    def test_a_long_record_carries_a_required_average(self) -> None:
        long_record = [
            a_test(f"S-{index:02d}", 4500.0 + (index % 3) * 200.0, index) for index in range(20)
        ]
        text = render_header(report(long_record))  # type: ignore[arg-type]
        assert "required average" in text
        assert "test record" in text

    def test_a_short_record_does_not(self) -> None:
        text = render_header(report(good_record()))  # type: ignore[arg-type]
        assert "required average" not in text


class CaseWholeReport:
    def test_a_clean_report(self) -> None:
        text = render_report(report(good_record()))  # type: ignore[arg-type]
        assert "Strength record for 4000P-57" in text
        assert "Tests" in text
        assert "Moving averages of three" in text
        assert "Findings:" not in text

    def test_a_report_with_findings(self) -> None:
        text = render_report(report(failing_record()))  # type: ignore[arg-type]
        assert "Individual tests below the floor" in text
        assert "Findings:" in text

    def test_an_empty_record(self) -> None:
        text = render_report(report([]))  # type: ignore[arg-type]
        assert "not_enough_tests" in text
        assert "Tests" not in text

    def test_the_convenience_wrapper(self) -> None:
        text = strength_report("4000P-57", good_record(), SPECIFIED)  # type: ignore[arg-type]
        assert "Strength record for 4000P-57" in text


@pytest.mark.parametrize("strength", [4500.0, 5000.0])
def test_a_higher_record_still_renders(strength: float) -> None:
    tests = [
        a_test("S-1", strength),
        a_test("S-2", strength + 100.0, 1),
        a_test("S-3", strength + 200.0, 2),
    ]
    assert "satisfactory" in strength_report("M", tests, SPECIFIED)
