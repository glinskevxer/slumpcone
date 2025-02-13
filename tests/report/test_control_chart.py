from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.report.control_chart import (
    CHART_WIDTH,
    ChartPoint,
    ControlChart,
    individual_chart,
    moving_average_chart,
    moving_range_chart,
    render_control_report,
)
from slumpcone.units.quantity import Quantity
from tests.strength.test_acceptance import a_test

SPECIFIED = Quantity(4000, "psi")


def record(count: int = 8, base: float = 4600.0, step: float = 100.0) -> list[object]:
    return [
        a_test(f"S-{index:02d}", base + (index % 3 - 1) * step, index) for index in range(count)
    ]


class CaseChart:
    def chart(self) -> ControlChart:
        return ControlChart(
            "Test",
            (ChartPoint("a", 100.0), ChartPoint("b", 200.0, False)),
            150.0,
            120.0,
            180.0,
        )

    def test_points_outside_the_limits(self) -> None:
        assert [point.label for point in self.chart().outside] == ["b"]
        assert not self.chart().is_in_control

    def test_a_chart_with_nothing_outside(self) -> None:
        chart = ControlChart("Test", (ChartPoint("a", 100.0),), 100.0, 90.0, 110.0)
        assert chart.is_in_control

    def test_the_bar_is_the_chart_width(self) -> None:
        assert len(self.chart().bar(150.0)) == CHART_WIDTH

    def test_a_low_value_draws_short(self) -> None:
        assert self.chart().bar(100.0).count("#") < self.chart().bar(200.0).count("#")

    def test_a_flat_chart_still_draws(self) -> None:
        chart = ControlChart("Test", (ChartPoint("a", 100.0),), 100.0, None, None)
        assert len(chart.bar(100.0)) == CHART_WIDTH

    def test_render(self) -> None:
        text = self.chart().render()
        assert "Test" in text
        assert "centre" in text
        assert "in control" in text
        assert "out" in text

    def test_render_without_limits(self) -> None:
        chart = ControlChart("Test", (ChartPoint("a", 100.0),), 100.0, None, None)
        assert "lower limit" in chart.render()


class CaseIndividual:
    def test_it_needs_two_tests(self) -> None:
        with pytest.raises(ValidationError, match="at least two tests"):
            individual_chart(record(1))  # type: ignore[arg-type]

    def test_a_point_per_test(self) -> None:
        chart = individual_chart(record(8))  # type: ignore[arg-type]
        assert len(chart.points) == 8

    def test_a_steady_record_is_in_control(self) -> None:
        chart = individual_chart(record(8, step=20.0))  # type: ignore[arg-type]
        assert chart.is_in_control

    def test_an_outlier_falls_outside(self) -> None:
        tests = [*record(20, step=20.0), a_test("S-99", 3000.0, 21)]
        chart = individual_chart(tests)  # type: ignore[arg-type]
        assert not chart.is_in_control
        assert chart.outside[0].label == "S-99"

    def test_the_centre_is_the_mean(self) -> None:
        chart = individual_chart(record(9))  # type: ignore[arg-type]
        assert chart.centre == pytest.approx(4600.0, abs=30.0)


class CaseMovingAverage:
    def test_it_needs_three_tests(self) -> None:
        with pytest.raises(ValidationError, match="at least 3 tests"):
            moving_average_chart(record(2), SPECIFIED)  # type: ignore[arg-type]

    def test_the_window_slides(self) -> None:
        chart = moving_average_chart(record(8), SPECIFIED)  # type: ignore[arg-type]
        assert len(chart.points) == 6

    def test_a_healthy_record_stays_above_the_floor(self) -> None:
        chart = moving_average_chart(record(8), SPECIFIED)  # type: ignore[arg-type]
        assert chart.is_in_control

    def test_a_low_record_falls_below(self) -> None:
        chart = moving_average_chart(record(8, base=3500.0), SPECIFIED)  # type: ignore[arg-type]
        assert not chart.is_in_control

    def test_the_lower_limit_is_the_specified_strength(self) -> None:
        chart = moving_average_chart(record(8), SPECIFIED)  # type: ignore[arg-type]
        assert chart.lower == pytest.approx(4000.0)


class CaseMovingRange:
    def test_a_point_per_gap(self) -> None:
        chart = moving_range_chart(record(8))  # type: ignore[arg-type]
        assert len(chart.points) == 7

    def test_a_steady_record_is_in_control(self) -> None:
        chart = moving_range_chart(record(8, step=20.0))  # type: ignore[arg-type]
        assert chart.is_in_control

    def test_a_jump_falls_outside(self) -> None:
        tests = [*record(8, step=10.0), a_test("S-99", 8000.0, 9)]
        chart = moving_range_chart(tests)  # type: ignore[arg-type]
        assert not chart.is_in_control

    def test_the_centre_is_the_average_range(self) -> None:
        chart = moving_range_chart(record(8))  # type: ignore[arg-type]
        assert chart.centre > 0.0


class CaseReport:
    def test_all_three_charts(self) -> None:
        text = render_control_report("4000P-57", record(8), SPECIFIED)  # type: ignore[arg-type]
        assert "Control charts for 4000P-57" in text
        assert "Individual tests" in text
        assert "Moving average of three" in text
        assert "Moving range" in text

    def test_a_short_record_leaves_out_the_moving_average(self) -> None:
        text = render_control_report("4000P-57", record(2), SPECIFIED)  # type: ignore[arg-type]
        assert "Moving average" not in text
        assert "Moving range" in text
