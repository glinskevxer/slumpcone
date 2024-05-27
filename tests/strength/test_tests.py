from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.breaks import BreakResult, FractureType
from slumpcone.strength.specimen import CureCondition, SpecimenPurpose, SpecimenSize
from slumpcone.strength.tests import StrengthTest, group_into_tests
from slumpcone.units.quantity import Quantity

TESTED = datetime(2024, 7, 10, 10, 15)


def one_break(
    code: str = "C-4471-A", load: float = 63000.0, age: float = 28.0, **overrides: object
) -> BreakResult:
    fields: dict[str, object] = {
        "specimen_code": code,
        "tested_at": TESTED,
        "age_days": age,
        "diameter_one": Quantity(4.00, "in"),
        "diameter_two": Quantity(4.00, "in"),
        "length": Quantity(8.00, "in"),
        "max_load": Quantity(load, "lbf"),
    }
    fields.update(overrides)
    return BreakResult(**fields)  # type: ignore[arg-type]


def strength_set(*breaks: BreakResult, **overrides: object) -> StrengthTest:
    fields: dict[str, object] = {
        "set_code": "S-4471",
        "mix_code": "4000P-57",
        "breaks": breaks or (one_break(), one_break("C-4471-B"), one_break("C-4471-C")),
    }
    fields.update(overrides)
    return StrengthTest(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_codes_are_normalised(self) -> None:
        built = strength_set(set_code=" s 4471 ", mix_code="4000p 57")
        assert built.set_code == "S-4471"
        assert built.mix_code == "4000P-57"

    def test_a_test_with_no_breaks_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one break"):
            StrengthTest("S-4471", "4000P-57", ())

    def test_a_repeated_specimen_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="appears twice"):
            strength_set(one_break(), one_break())


class CaseAverages:
    def test_the_average_of_three(self) -> None:
        built = strength_set(
            one_break("A", 62000.0), one_break("B", 63000.0), one_break("C", 64000.0)
        )
        assert built.average.value == pytest.approx(5014.0, abs=5.0)

    def test_the_lowest_and_highest(self) -> None:
        built = strength_set(
            one_break("A", 62000.0), one_break("B", 63000.0), one_break("C", 64000.0)
        )
        assert built.lowest < built.highest

    def test_the_age_is_averaged(self) -> None:
        built = strength_set(one_break("A", age=28.0), one_break("B", age=28.2))
        assert built.age_days == pytest.approx(28.1)
        assert built.age_spread == pytest.approx(0.2, abs=1e-9)

    def test_the_test_date_is_the_last_break(self) -> None:
        later = one_break("B")
        built = strength_set(
            one_break("A"),
            BreakResult(
                later.specimen_code,
                TESTED + timedelta(days=1),
                29.0,
                later.diameter_one,
                later.diameter_two,
                later.length,
                later.max_load,
            ),
        )
        assert built.tested_on == (TESTED + timedelta(days=1)).date()

    def test_the_strengths_come_back_in_break_order(self) -> None:
        built = strength_set(one_break("A", 62000.0), one_break("B", 64000.0))
        assert built.strengths[0] < built.strengths[1]


class CaseSpread:
    def test_a_tight_set(self) -> None:
        built = strength_set(
            one_break("A", 63000.0), one_break("B", 63500.0), size=SpecimenSize.CYL_6X12
        )
        assert built.within_test_range_percent.value < 1.0
        assert built.concerns() == ()

    def test_a_wide_set_is_a_concern(self) -> None:
        built = strength_set(one_break("A", 55000.0), one_break("B", 65000.0))
        assert built.within_test_range_percent.value > 8.0
        assert any("precision limit" in concern for concern in built.concerns())

    def test_three_companions_get_a_looser_limit(self) -> None:
        two = strength_set(
            one_break("A", 60000.0), one_break("B", 65200.0), size=SpecimenSize.CYL_6X12
        )
        three = strength_set(
            one_break("A", 60000.0),
            one_break("B", 62600.0),
            one_break("C", 65200.0),
            size=SpecimenSize.CYL_4X8,
        )
        assert two.range_limit.value < three.range_limit.value
        assert any("precision limit" in c for c in two.concerns())
        assert not any("precision limit" in c for c in three.concerns())

    def test_a_single_break_has_no_spread(self) -> None:
        built = strength_set(one_break("A"))
        assert built.within_test_range_percent.value == pytest.approx(0.0)


class CaseCompleteness:
    def test_two_six_by_twelves_make_a_test(self) -> None:
        built = strength_set(one_break("A"), one_break("B"), size=SpecimenSize.CYL_6X12)
        assert built.is_complete
        assert built.counts_for_acceptance

    def test_two_four_by_eights_do_not(self) -> None:
        built = strength_set(one_break("A"), one_break("B"), size=SpecimenSize.CYL_4X8)
        assert not built.is_complete
        assert any("companions broken" in c for c in built.concerns())

    def test_a_field_cured_set_is_not_acceptance(self) -> None:
        built = strength_set(cure=CureCondition.FIELD)
        assert built.is_complete
        assert not built.counts_for_acceptance

    def test_a_form_removal_set_is_not_acceptance(self) -> None:
        assert not strength_set(purpose=SpecimenPurpose.FORM_REMOVAL).counts_for_acceptance


class CaseConcerns:
    def test_companions_broken_days_apart(self) -> None:
        built = strength_set(one_break("A", age=28.0), one_break("B", age=30.0))
        assert any("days apart" in c for c in built.concerns())

    def test_an_out_of_round_companion(self) -> None:
        odd = one_break("B", diameter_one=Quantity(4.2, "in"))
        built = strength_set(one_break("A"), odd, one_break("C"))
        assert any("out of round" in c for c in built.concerns())

    def test_a_fracture_that_points_at_the_setup(self) -> None:
        odd = one_break("B", fracture=FractureType.SIDE_FRACTURE)
        built = strength_set(one_break("A"), odd, one_break("C"))
        assert any("points at the setup" in c for c in built.concerns())

    def test_describe(self) -> None:
        line = strength_set().describe()
        assert "S-4471" in line
        assert "4000P-57" in line
        assert "28 d" in line
        assert "n=3" in line


class CaseGrouping:
    def test_breaks_are_gathered_by_set(self) -> None:
        breaks = [one_break("A"), one_break("B"), one_break("C")]
        sets = {"A": "S-1", "B": "S-1", "C": "S-2"}
        mixes = {"S-1": "4000P-57", "S-2": "3000W-67"}
        tests = group_into_tests(breaks, sets, mixes)
        assert [t.set_code for t in tests] == ["S-1", "S-2"]
        assert len(tests[0].breaks) == 2

    def test_a_break_with_no_set_is_dropped(self) -> None:
        tests = group_into_tests([one_break("A")], {}, {})
        assert tests == ()

    def test_a_set_with_no_mix_is_dropped(self) -> None:
        tests = group_into_tests([one_break("A")], {"A": "S-1"}, {})
        assert tests == ()

    def test_defaults_are_passed_through(self) -> None:
        tests = group_into_tests(
            [one_break("A")], {"A": "S-1"}, {"S-1": "M"}, cure=CureCondition.FIELD
        )
        assert tests[0].cure is CureCondition.FIELD

    def test_members_come_back_in_specimen_order(self) -> None:
        breaks = [one_break("C"), one_break("A"), one_break("B")]
        sets = dict.fromkeys(["A", "B", "C"], "S-1")
        tests = group_into_tests(breaks, sets, {"S-1": "M"})
        assert [b.specimen_code for b in tests[0].breaks] == ["A", "B", "C"]
