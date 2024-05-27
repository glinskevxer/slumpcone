from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.acceptance import (
    BRANCH_STRENGTH,
    StrengthStatus,
    evaluate_strength,
    individual_floor,
)
from slumpcone.strength.breaks import BreakResult
from slumpcone.strength.specimen import CureCondition, SpecimenSize
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity

TESTED = datetime(2024, 7, 10, 10, 15)
SPECIFIED = Quantity(4000, "psi")


def a_test(set_code: str, strength: float, day: int = 0, **overrides: object) -> StrengthTest:
    # Two six by twelve companions, both landing on the strength asked for.
    load = strength * 28.274333882308138
    breaks = tuple(
        BreakResult(
            f"{set_code}-{letter}",
            TESTED + timedelta(days=day),
            28.0,
            Quantity(6.0, "in"),
            Quantity(6.0, "in"),
            Quantity(12.0, "in"),
            Quantity(load, "lbf"),
        )
        for letter in ("A", "B")
    )
    fields: dict[str, object] = {
        "set_code": set_code,
        "mix_code": "4000P-57",
        "breaks": breaks,
        "size": SpecimenSize.CYL_6X12,
    }
    fields.update(overrides)
    return StrengthTest(**fields)  # type: ignore[arg-type]


class CaseIndividualFloor:
    def test_below_the_branch_it_is_a_flat_five_hundred(self) -> None:
        assert individual_floor(Quantity(4000, "psi")) == Quantity(3500, "psi")
        assert individual_floor(Quantity(3000, "psi")) == Quantity(2500, "psi")

    def test_at_the_branch_it_is_still_the_flat_margin(self) -> None:
        assert individual_floor(BRANCH_STRENGTH) == Quantity(4500, "psi")

    def test_above_the_branch_it_is_a_tenth(self) -> None:
        assert individual_floor(Quantity(6000, "psi")) == Quantity(5400, "psi")

    def test_the_proportional_margin_is_wider_in_absolute_terms(self) -> None:
        assert individual_floor(Quantity(8000, "psi")) == Quantity(7200, "psi")

    def test_a_non_pressure_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            individual_floor(Quantity(4000, "lb"))

    def test_a_non_positive_strength_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            individual_floor(Quantity(0, "psi"))


class CaseStatus:
    def test_which_status_needs_action(self) -> None:
        assert StrengthStatus.INVESTIGATE.needs_action
        assert not StrengthStatus.SATISFACTORY.needs_action

    def test_prints_its_own_value(self) -> None:
        assert str(StrengthStatus.NOT_ENOUGH_TESTS) == "not_enough_tests"


class CaseEvaluate:
    def test_nothing_on_file(self) -> None:
        report = evaluate_strength("4000P-57", [], SPECIFIED)
        assert report.status is StrengthStatus.NOT_ENOUGH_TESTS
        assert report.windows == ()

    def test_two_tests_is_not_a_window_yet(self) -> None:
        report = evaluate_strength(
            "4000P-57", [a_test("S-1", 4500.0), a_test("S-2", 4600.0, 1)], SPECIFIED
        )
        assert report.status is StrengthStatus.NOT_ENOUGH_TESTS
        assert report.windows == ()

    def test_three_good_tests_are_satisfactory(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 4500.0), a_test("S-2", 4600.0, 1), a_test("S-3", 4700.0, 2)],
            SPECIFIED,
        )
        assert report.status is StrengthStatus.SATISFACTORY
        assert len(report.windows) == 1
        assert report.windows[0].meets
        assert report.reasons == ()

    def test_the_windows_slide(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [
                a_test("S-1", 4500.0),
                a_test("S-2", 4600.0, 1),
                a_test("S-3", 4700.0, 2),
                a_test("S-4", 4800.0, 3),
            ],
            SPECIFIED,
        )
        assert len(report.windows) == 2
        assert report.windows[0].set_codes == ("S-1", "S-2", "S-3")
        assert report.windows[1].set_codes == ("S-2", "S-3", "S-4")

    def test_a_low_average_of_three(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 3900.0), a_test("S-2", 3800.0, 1), a_test("S-3", 3950.0, 2)],
            SPECIFIED,
        )
        assert report.status is StrengthStatus.INVESTIGATE
        assert len(report.failing_windows) == 1
        assert "below the specified" in report.reasons[0]

    def test_one_very_low_test_among_high_ones(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 5200.0), a_test("S-2", 3400.0, 1), a_test("S-3", 5300.0, 2)],
            SPECIFIED,
        )
        assert report.windows[0].meets
        assert [low.set_code for low in report.low_tests] == ["S-2"]
        assert report.status is StrengthStatus.INVESTIGATE

    def test_a_record_hovering_under_fails_the_average_not_the_individual(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 3900.0), a_test("S-2", 3850.0, 1), a_test("S-3", 3800.0, 2)],
            SPECIFIED,
        )
        assert report.low_tests == ()
        assert report.failing_windows != ()

    def test_the_individual_rule_applies_before_three_tests(self) -> None:
        report = evaluate_strength("4000P-57", [a_test("S-1", 3000.0)], SPECIFIED)
        assert report.status is StrengthStatus.INVESTIGATE
        assert report.low_tests[0].shortfall == Quantity(500, "psi")


class CaseFiltering:
    def test_field_cured_sets_are_dropped(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [
                a_test("S-1", 4500.0),
                a_test("S-2", 2000.0, 1, cure=CureCondition.FIELD),
                a_test("S-3", 4600.0, 2),
                a_test("S-4", 4700.0, 3),
            ],
            SPECIFIED,
        )
        assert [t.set_code for t in report.tests] == ["S-1", "S-3", "S-4"]
        assert report.status is StrengthStatus.SATISFACTORY

    def test_incomplete_sets_are_dropped(self) -> None:
        thin = a_test("S-2", 2000.0, 1)
        thin = StrengthTest(
            thin.set_code, thin.mix_code, thin.breaks[:1], size=SpecimenSize.CYL_6X12
        )
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 4500.0), thin, a_test("S-3", 4600.0, 2), a_test("S-4", 4700.0, 3)],
            SPECIFIED,
        )
        assert [t.set_code for t in report.tests] == ["S-1", "S-3", "S-4"]

    def test_tests_are_ordered_by_the_day_they_were_broken(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-3", 4700.0, 2), a_test("S-1", 4500.0), a_test("S-2", 4600.0, 1)],
            SPECIFIED,
        )
        assert [t.set_code for t in report.tests] == ["S-1", "S-2", "S-3"]


class CaseReporting:
    def test_window_describe(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 4500.0), a_test("S-2", 4600.0, 1), a_test("S-3", 4700.0, 2)],
            SPECIFIED,
        )
        assert "ok" in report.windows[0].describe()
        assert report.windows[0].margin.value == pytest.approx(600.0, abs=5.0)

    def test_report_describe(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 3000.0), a_test("S-2", 3100.0, 1), a_test("S-3", 3200.0, 2)],
            SPECIFIED,
        )
        text = report.describe()
        assert "4000P-57 against 4000 psi: investigate on 3 tests" in text
        assert "below the" in text
