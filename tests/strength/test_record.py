from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.breaks import BreakResult
from slumpcone.strength.record import (
    MAX_STRENGTH_DIFFERENCE,
    MIN_SPAN_DAYS,
    TestRecord,
    combined_count,
    statistical_average_deviation,
)
from slumpcone.strength.specimen import CureCondition, SpecimenSize
from slumpcone.strength.tests import StrengthTest
from slumpcone.units.quantity import Quantity

FIRST = datetime(2024, 1, 10, 10, 0)


def a_test(set_code: str, strength: float, day: int, **overrides: object) -> StrengthTest:
    load = strength * 28.274333882308138
    breaks = tuple(
        BreakResult(
            f"{set_code}-{letter}",
            FIRST + timedelta(days=day),
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


def record(
    count: int = 30, spread: float = 400.0, spacing: int = 4, **overrides: object
) -> TestRecord:
    tests = tuple(
        a_test(f"S-{index:03d}", 5000.0 + (spread if index % 2 else -spread), index * spacing)
        for index in range(count)
    )
    fields: dict[str, object] = {
        "mix_code": "4000P-57",
        "specified": Quantity(4000, "psi"),
        "tests": tests,
        "materials_are_similar": True,
    }
    fields.update(overrides)
    return TestRecord(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_the_mix_code_is_normalised(self) -> None:
        assert record(mix_code="4000p 57").mix_code == "4000P-57"

    def test_the_specified_strength_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            record(specified=Quantity(4000, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            record(specified=Quantity(0, "psi"))

    def test_a_repeated_set_is_refused(self) -> None:
        one = a_test("S-1", 5000.0, 0)
        with pytest.raises(ValidationError, match="appears twice"):
            TestRecord("4000P-57", Quantity(4000, "psi"), (one, one))


class CaseStatistics:
    def test_count_and_span(self) -> None:
        built = record(count=30, spacing=4)
        assert built.count == 30
        assert built.span_days == 116

    def test_the_strengths_come_back_oldest_first(self) -> None:
        built = record(count=4)
        assert built.strengths[0].value < built.strengths[1].value

    def test_the_deviation(self) -> None:
        assert record().deviation.value == pytest.approx(406.8, abs=1.0)

    def test_the_mean(self) -> None:
        assert record().mean.value == pytest.approx(5000.0, abs=1.0)

    def test_an_empty_record_has_no_mean(self) -> None:
        empty = TestRecord("4000P-57", Quantity(4000, "psi"), ())
        with pytest.raises(ValidationError, match="no mean"):
            _ = empty.mean

    def test_a_record_of_one_covers_no_span(self) -> None:
        assert record(count=1).span_days == 0

    def test_field_cured_sets_are_left_out(self) -> None:
        tests = (
            *record(count=4).tests,
            a_test("S-999", 1000.0, 20, cure=CureCondition.FIELD),
        )
        built = TestRecord("4000P-57", Quantity(4000, "psi"), tests)
        assert built.count == 4

    def test_full_record_flag(self) -> None:
        assert record(count=30).is_full
        assert not record(count=29).is_full


class CaseQualification:
    def test_a_good_record_qualifies(self) -> None:
        assert record().qualifies_for(Quantity(4000, "psi"))
        assert record().disqualifications(Quantity(4000, "psi")) == ()

    def test_too_few_tests(self) -> None:
        reasons = record(count=10).disqualifications(Quantity(4000, "psi"))
        assert any("usable tests" in reason for reason in reasons)

    def test_too_short_a_span(self) -> None:
        reasons = record(count=20, spacing=1).disqualifications(Quantity(4000, "psi"))
        assert any("covers 19 days" in reason for reason in reasons)

    def test_a_specified_strength_too_far_away(self) -> None:
        reasons = record().disqualifications(Quantity(6000, "psi"))
        assert any("2000 psi from" in reason for reason in reasons)

    def test_exactly_a_thousand_apart_is_allowed(self) -> None:
        assert record().qualifies_for(Quantity(5000, "psi"))

    def test_materials_have_to_be_declared_similar(self) -> None:
        reasons = record(materials_are_similar=False).disqualifications(Quantity(4000, "psi"))
        assert any("declared similar" in reason for reason in reasons)

    def test_similarity_does_not_default_to_true(self) -> None:
        bare = TestRecord("4000P-57", Quantity(4000, "psi"), record().tests)
        assert not bare.materials_are_similar

    def test_several_reasons_come_back_together(self) -> None:
        reasons = record(count=5, spacing=1, materials_are_similar=False).disqualifications(
            Quantity(6000, "psi")
        )
        assert len(reasons) == 4

    def test_the_thresholds(self) -> None:
        assert MIN_SPAN_DAYS == 45
        assert MAX_STRENGTH_DIFFERENCE.value == pytest.approx(1000.0)


class CaseCombining:
    def test_two_identical_records_combine_to_the_same_deviation(self) -> None:
        one = record(count=20)
        two = record(count=20)
        combined = statistical_average_deviation(one, two)
        assert combined.value == pytest.approx(one.deviation.value, abs=1.0)

    def test_the_wider_record_pulls_the_combination_up(self) -> None:
        tight = record(count=20, spread=200.0)
        wide = record(count=20, spread=800.0)
        combined = statistical_average_deviation(tight, wide)
        assert tight.deviation < combined < wide.deviation

    def test_the_longer_record_carries_more_weight(self) -> None:
        tight_long = record(count=30, spread=200.0)
        wide_short = record(count=16, spread=800.0)
        combined = statistical_average_deviation(tight_long, wide_short)
        midpoint = (tight_long.deviation.value + wide_short.deviation.value) / 2.0
        assert combined.value < midpoint

    def test_a_record_of_one_cannot_combine(self) -> None:
        with pytest.raises(ValidationError, match="at least two tests"):
            statistical_average_deviation(record(count=1), record(count=20))

    def test_combined_count(self) -> None:
        assert combined_count(record(count=16), record(count=18)) == 34

    def test_describe(self) -> None:
        text = record().describe()
        assert "4000P-57" in text
        assert "30 tests over 116 days" in text
        assert "mean 5000 psi" in text
