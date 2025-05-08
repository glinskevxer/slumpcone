from __future__ import annotations

import pytest

from slumpcone.report.cusum import (
    DEFAULT_LIMIT,
    DEFAULT_SLACK,
    CusumChart,
    CusumError,
    CusumPoint,
    CusumRun,
    build_cusum,
)
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity
from tests.strength.test_acceptance import a_test

TARGET = Quantity(4600, "psi")
SIGMA = Quantity(400, "psi")


def steady(count: int = 12) -> list[StrengthTest]:
    """Tests that sit on target, alternating either side of it."""
    return [
        a_test(f"S-{index:02d}", 4600.0 + (100.0 if index % 2 else -100.0), index)
        for index in range(count)
    ]


def drifting(count: int = 12, drop: float = 600.0, after: int = 4) -> list[StrengthTest]:
    """Tests that sit on target, then step down and stay there."""
    return [
        a_test(
            f"S-{index:02d}",
            4600.0 - (drop if index >= after else 0.0),
            index,
        )
        for index in range(count)
    ]


class CaseSteady:
    def test_a_steady_run_finds_no_shift(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        assert chart.is_stable
        assert chart.runs == ()

    def test_it_keeps_a_point_per_test(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        assert len(chart.points) == 12

    def test_the_sums_stay_near_zero(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        assert max(point.worst for point in chart.points) < DEFAULT_LIMIT

    def test_the_slack_and_limit_read_in_psi(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        assert chart.slack_psi == pytest.approx(200.0)
        assert chart.limit_psi == pytest.approx(2000.0)

    def test_describe(self) -> None:
        assert "no shift" in build_cusum(steady(), TARGET, deviation=SIGMA).describe()


class CaseDrift:
    def test_a_step_down_is_found(self) -> None:
        chart = build_cusum(drifting(), TARGET, deviation=SIGMA)
        assert not chart.is_stable
        assert chart.low_runs

    def test_the_run_is_on_the_low_side(self) -> None:
        chart = build_cusum(drifting(), TARGET, deviation=SIGMA)
        assert chart.runs[0].side == "low"

    def test_it_points_at_where_the_drift_started(self) -> None:
        chart = build_cusum(drifting(after=4), TARGET, deviation=SIGMA)
        first = chart.first_low()
        assert first is not None
        # Tests are numbered from one in the report, so index four is test five.
        assert first.started_at >= 4

    def test_it_takes_several_tests_to_accumulate(self) -> None:
        chart = build_cusum(drifting(), TARGET, deviation=SIGMA)
        first = chart.first_low()
        assert first is not None
        assert first.length > 1

    def test_a_bigger_drop_is_found_sooner(self) -> None:
        gentle = build_cusum(drifting(drop=500.0), TARGET, deviation=SIGMA).first_low()
        sharp = build_cusum(drifting(drop=1200.0), TARGET, deviation=SIGMA).first_low()
        assert gentle is not None
        assert sharp is not None
        assert sharp.fired_at <= gentle.fired_at

    def test_a_step_up_is_found_on_the_high_side(self) -> None:
        rising = [
            a_test(f"S-{index:02d}", 4600.0 + (800.0 if index >= 4 else 0.0), index)
            for index in range(12)
        ]
        chart = build_cusum(rising, TARGET, deviation=SIGMA)
        assert chart.runs
        assert chart.runs[0].side == "high"
        assert chart.low_runs == ()

    def test_a_high_shift_is_not_reported_as_one_to_go_and_look_at(self) -> None:
        rising = [
            a_test(f"S-{index:02d}", 4600.0 + (800.0 if index >= 4 else 0.0), index)
            for index in range(12)
        ]
        assert build_cusum(rising, TARGET, deviation=SIGMA).first_low() is None

    def test_describe_counts_the_shifts(self) -> None:
        text = build_cusum(drifting(), TARGET, deviation=SIGMA).describe()
        assert "shift(s)" in text
        assert "downward" in text

    def test_a_run_describes_with_one_based_numbering(self) -> None:
        run = CusumRun("low", 3, 8, 5.4)
        assert "test 4" in run.describe()
        assert "test 9" in run.describe()
        assert run.length == 6


class CaseTuning:
    def test_more_slack_finds_fewer_shifts(self) -> None:
        tight = build_cusum(drifting(drop=250.0), TARGET, deviation=SIGMA, slack=0.25)
        loose = build_cusum(drifting(drop=250.0), TARGET, deviation=SIGMA, slack=1.5)
        assert len(tight.runs) >= len(loose.runs)

    def test_a_higher_limit_finds_fewer_shifts(self) -> None:
        low = build_cusum(drifting(), TARGET, deviation=SIGMA, limit=3.0)
        high = build_cusum(drifting(), TARGET, deviation=SIGMA, limit=20.0)
        assert len(low.runs) >= len(high.runs)

    def test_a_tighter_deviation_makes_the_chart_more_sensitive(self) -> None:
        wide = build_cusum(drifting(drop=250.0), TARGET, deviation=Quantity(800, "psi"))
        narrow = build_cusum(drifting(drop=250.0), TARGET, deviation=Quantity(150, "psi"))
        assert len(narrow.runs) >= len(wide.runs)

    def test_the_defaults_are_the_textbook_pair(self) -> None:
        assert pytest.approx(0.5) == DEFAULT_SLACK
        assert pytest.approx(5.0) == DEFAULT_LIMIT

    def test_negative_slack(self) -> None:
        with pytest.raises(CusumError) as caught:
            build_cusum(steady(), TARGET, deviation=SIGMA, slack=-1.0)
        assert caught.value.code == "CUSUM_NEGATIVE_SLACK"

    def test_a_zero_limit(self) -> None:
        with pytest.raises(CusumError) as caught:
            build_cusum(steady(), TARGET, deviation=SIGMA, limit=0.0)
        assert caught.value.code == "CUSUM_NO_LIMIT"


class CaseFittingTheDeviation:
    def test_it_fits_one_when_none_is_given(self) -> None:
        chart = build_cusum(steady(), TARGET)
        assert chart.deviation.value > 0.0

    def test_too_few_tests_to_fit(self) -> None:
        with pytest.raises(CusumError) as caught:
            build_cusum(steady(4), TARGET)
        assert caught.value.code == "CUSUM_TOO_FEW_TO_FIT"

    def test_a_handed_in_deviation_works_on_a_short_run(self) -> None:
        chart = build_cusum(steady(4), TARGET, deviation=SIGMA)
        assert len(chart.points) == 4

    def test_a_run_with_no_spread_cannot_be_fitted(self) -> None:
        flat = [a_test(f"S-{index:02d}", 4600.0, index) for index in range(10)]
        with pytest.raises(CusumError) as caught:
            build_cusum(flat, TARGET)
        assert caught.value.code == "CUSUM_NO_SPREAD"

    def test_a_zero_deviation_handed_in(self) -> None:
        with pytest.raises(CusumError) as caught:
            build_cusum(steady(), TARGET, deviation=Quantity(0.0, "psi"))
        assert caught.value.code == "CUSUM_NO_SPREAD"

    def test_no_tests_at_all(self) -> None:
        with pytest.raises(CusumError) as caught:
            build_cusum([], TARGET, deviation=SIGMA)
        assert caught.value.code == "CUSUM_NO_TESTS"


class CaseRendering:
    def test_a_row_per_test_plus_a_header(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        assert len(chart.render().splitlines()) == 13

    def test_the_header_names_the_target_and_limit(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        header = chart.render().splitlines()[0]
        assert "target" in header
        assert "2000 psi" in header

    def test_a_fired_row_is_marked(self) -> None:
        chart = build_cusum(drifting(), TARGET, deviation=SIGMA)
        assert "*" in chart.render()

    def test_a_steady_chart_has_no_marks(self) -> None:
        chart = build_cusum(steady(), TARGET, deviation=SIGMA)
        assert "*" not in chart.render()

    def test_the_low_side_is_signed(self) -> None:
        chart = build_cusum(drifting(), TARGET, deviation=SIGMA)
        assert " -" in chart.render()

    def test_the_width_can_be_narrowed(self) -> None:
        chart = build_cusum(drifting(), TARGET, deviation=SIGMA)
        assert len(chart.render(width=10)) < len(chart.render(width=60))


def test_a_point_fires_at_the_limit() -> None:
    point = CusumPoint("S-1", Quantity(4000, "psi"), 5.0, 0.0)
    assert point.fired(5.0)
    assert point.worst == pytest.approx(5.0)


def test_a_point_below_the_limit_does_not_fire() -> None:
    assert not CusumPoint("S-1", Quantity(4000, "psi"), 4.9, 0.0).fired(5.0)


def test_an_empty_chart_is_stable() -> None:
    chart = CusumChart(TARGET, SIGMA, 0.5, 5.0, (), ())
    assert chart.is_stable
    assert chart.first_low() is None
