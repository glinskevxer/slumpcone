from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.strength.breaks import BreakResult
from slumpcone.strength.control import (
    MIN_TESTS,
    ControlStandard,
    overall_standard,
    range_constant,
    read_control,
    within_test_standard,
)
from slumpcone.strength.specimen import SpecimenSize
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity
from tests.strength.test_acceptance import TESTED, a_test

AREA = 28.274333882308138


def spread_test(set_code: str, low: float, high: float, day: int = 0) -> StrengthTest:
    breaks = tuple(
        BreakResult(
            f"{set_code}-{letter}",
            TESTED,
            28.0,
            Quantity(6.0, "in"),
            Quantity(6.0, "in"),
            Quantity(12.0, "in"),
            Quantity(value * AREA, "lbf"),
        )
        for letter, value in (("A", low), ("B", high))
    )
    return StrengthTest(set_code, "4000P-57", breaks, size=SpecimenSize.CYL_6X12)


def record(count: int, base: float = 4500.0, step: float = 100.0) -> list[StrengthTest]:
    return [
        a_test(f"S-{index:02d}", base + (index % 3) * step, index) for index in range(count)
    ]


class CaseConstants:
    def test_the_range_constants(self) -> None:
        assert range_constant(2) == pytest.approx(1.128)
        assert range_constant(3) == pytest.approx(1.693)

    def test_an_unknown_companion_count(self) -> None:
        with pytest.raises(ValidationError, match="no range constant"):
            range_constant(7)

    def test_three_companions_divide_by_more(self) -> None:
        assert range_constant(3) > range_constant(2)


class CaseGrades:
    @pytest.mark.parametrize(
        ("psi", "grade"),
        [
            (300.0, ControlStandard.EXCELLENT),
            (450.0, ControlStandard.VERY_GOOD),
            (550.0, ControlStandard.GOOD),
            (650.0, ControlStandard.FAIR),
            (800.0, ControlStandard.POOR),
        ],
    )
    def test_the_overall_bands(self, psi: float, grade: ControlStandard) -> None:
        assert overall_standard(Quantity(psi, "psi")) is grade

    def test_a_non_pressure_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            overall_standard(Quantity(400, "lb"))

    @pytest.mark.parametrize(
        ("value", "grade"),
        [
            (2.0, ControlStandard.EXCELLENT),
            (3.5, ControlStandard.VERY_GOOD),
            (4.5, ControlStandard.GOOD),
            (5.5, ControlStandard.FAIR),
            (8.0, ControlStandard.POOR),
        ],
    )
    def test_the_within_test_bands(self, value: float, grade: ControlStandard) -> None:
        assert within_test_standard(Percent(value)) is grade

    def test_which_grades_need_attention(self) -> None:
        assert ControlStandard.POOR.needs_attention
        assert ControlStandard.FAIR.needs_attention
        assert not ControlStandard.GOOD.needs_attention

    def test_it_prints_its_own_value(self) -> None:
        assert str(ControlStandard.VERY_GOOD) == "very good"


class CaseReading:
    def test_a_record_needs_two_tests(self) -> None:
        with pytest.raises(ValidationError, match="at least two tests"):
            read_control(record(1))

    def test_the_mean_and_the_overall_deviation(self) -> None:
        reading = read_control(record(12))
        assert reading.mean.value == pytest.approx(4600.0, abs=30.0)
        assert reading.overall_deviation.value > 0.0

    def test_a_tight_record_grades_well(self) -> None:
        reading = read_control(record(12, step=10.0))
        assert reading.overall_grade is ControlStandard.EXCELLENT

    def test_a_loose_record_grades_badly(self) -> None:
        reading = read_control(record(12, step=1200.0))
        assert reading.overall_grade.needs_attention

    def test_the_within_test_figure_comes_off_the_ranges(self) -> None:
        tests = [
            spread_test("S-1", 4400.0, 4600.0),
            spread_test("S-2", 4500.0, 4700.0),
            spread_test("S-3", 4300.0, 4500.0),
        ]
        reading = read_control(tests)
        assert reading.companions == 2
        assert reading.within_test_deviation.value == pytest.approx(200.0 / 1.128, abs=1.0)

    def test_a_tight_laboratory(self) -> None:
        tests = [spread_test(f"S-{index}", 4500.0, 4510.0) for index in range(4)]
        assert read_control(tests).within_test_grade is ControlStandard.EXCELLENT

    def test_a_loose_laboratory(self) -> None:
        tests = [spread_test(f"S-{index}", 4000.0, 5000.0) for index in range(4)]
        assert read_control(tests).within_test_grade.needs_attention

    def test_the_two_variations_are_independent(self) -> None:
        tight_plant_loose_lab = [
            spread_test(f"S-{index}", 4000.0, 5000.0) for index in range(6)
        ]
        reading = read_control(tight_plant_loose_lab)
        assert not reading.overall_grade.needs_attention
        assert reading.within_test_grade.needs_attention
        assert reading.where_the_problem_is == "the laboratory"

    def test_where_the_problem_is(self) -> None:
        assert read_control(record(12, step=10.0)).where_the_problem_is == "neither"

    def test_enough_tests(self) -> None:
        assert not read_control(record(4)).is_enough_tests
        assert read_control(record(MIN_TESTS)).is_enough_tests

    def test_describe(self) -> None:
        text = read_control(record(12)).describe()
        assert "overall" in text
        assert "within test" in text

    def test_describe_says_when_there_are_too_few(self) -> None:
        assert "only 4 tests" in read_control(record(4)).describe()

    def test_the_variations_are_shares_of_the_mean(self) -> None:
        reading = read_control(record(12))
        assert reading.overall_variation.value == pytest.approx(
            100.0 * reading.overall_deviation.value / reading.mean.value
        )
        assert reading.within_test_variation.value >= 0.0
