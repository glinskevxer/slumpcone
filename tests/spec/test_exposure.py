from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.spec.exposure import (
    ExposureCategory,
    ExposureClass,
    ExposureSet,
    air_requirement,
)
from slumpcone.units.quantity import Quantity


class CaseExposureClass:
    def test_parse(self) -> None:
        assert ExposureClass.parse("f2") is ExposureClass.F2
        assert ExposureClass.parse(" C 2 ") is ExposureClass.C2

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="exposure class"):
            ExposureClass.parse("F4")

    def test_category_and_severity(self) -> None:
        assert ExposureClass.F3.category is ExposureCategory.FREEZE_THAW
        assert ExposureClass.S2.category is ExposureCategory.SULFATE
        assert ExposureClass.F3.severity == 3
        assert ExposureClass.W0.severity == 0

    def test_ratio_limits(self) -> None:
        assert ExposureClass.F0.max_water_cementitious is None
        assert ExposureClass.F1.max_water_cementitious == pytest.approx(0.55)
        assert ExposureClass.C2.max_water_cementitious == pytest.approx(0.40)

    def test_strength_floors(self) -> None:
        assert ExposureClass.F0.min_strength == Quantity(2500, "psi")
        assert ExposureClass.C2.min_strength == Quantity(5000, "psi")
        assert ExposureClass.S1.min_strength == Quantity(4000, "psi")

    def test_chloride_limits(self) -> None:
        assert ExposureClass.C0.max_chloride == Percent(1.00)
        assert ExposureClass.C2.max_chloride == Percent(0.15)
        assert ExposureClass.F2.max_chloride is None

    def test_air_entrainment_flag(self) -> None:
        assert ExposureClass.F1.needs_air_entrainment
        assert ExposureClass.F3.needs_air_entrainment
        assert not ExposureClass.F0.needs_air_entrainment
        assert not ExposureClass.S3.needs_air_entrainment

    def test_only_f3_caps_replacement(self) -> None:
        assert ExposureClass.F3.caps_supplementary_cementitious
        assert not ExposureClass.F2.caps_supplementary_cementitious

    def test_prints_the_drawing_spelling(self) -> None:
        assert str(ExposureClass.F3) == "F3"
        assert str(ExposureCategory.SULFATE) == "S"


class CaseAirRequirement:
    def test_no_requirement_without_a_freeze_thaw_class(self) -> None:
        assert air_requirement(ExposureClass.F0, "1 in") is None

    @pytest.mark.parametrize(
        ("size", "moderate", "severe"),
        [
            ("3/8 in", 6.0, 7.5),
            ("3/4 in", 5.0, 6.0),
            ("1 in", 4.5, 6.0),
            ("1-1/2 in", 4.5, 5.5),
        ],
    )
    def test_the_table(self, size: str, moderate: float, severe: float) -> None:
        assert air_requirement(ExposureClass.F1, size) == Percent(moderate)
        assert air_requirement(ExposureClass.F2, size) == Percent(severe)
        assert air_requirement(ExposureClass.F3, size) == Percent(severe)

    def test_high_strength_takes_a_point_off(self) -> None:
        assert air_requirement(ExposureClass.F2, "1 in", Quantity(6000, "psi")) == Percent(5.0)

    def test_exactly_five_thousand_takes_nothing_off(self) -> None:
        assert air_requirement(ExposureClass.F2, "1 in", Quantity(5000, "psi")) == Percent(6.0)

    def test_a_sieve_object_works_too(self) -> None:
        from slumpcone.materials.gradation import sieve

        assert air_requirement(ExposureClass.F1, sieve("3/4 in")) == Percent(5.0)

    def test_an_aggregate_the_table_has_no_row_for(self) -> None:
        with pytest.raises(ValidationError, match="no row"):
            air_requirement(ExposureClass.F1, "No. 4")


class CaseExposureSet:
    def test_default_is_all_zero(self) -> None:
        assert str(ExposureSet()) == "F0 S0 W0 C0"

    def test_parse_in_any_order(self) -> None:
        assigned = ExposureSet.parse("C2 F2 W1 S1")
        assert assigned.freeze_thaw is ExposureClass.F2
        assert assigned.corrosion is ExposureClass.C2

    def test_parse_fills_absent_categories(self) -> None:
        assert str(ExposureSet.parse("F3")) == "F3 S0 W0 C0"

    def test_parse_takes_commas(self) -> None:
        assert str(ExposureSet.parse("F1, S1")) == "F1 S1 W0 C0"

    def test_parse_refuses_two_from_one_category(self) -> None:
        with pytest.raises(ValidationError, match="two F classes"):
            ExposureSet.parse("F1 F2")

    def test_a_class_in_the_wrong_slot_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not a S class"):
            ExposureSet(sulfate=ExposureClass.F2)

    def test_the_tightest_ratio_wins(self) -> None:
        assigned = ExposureSet.parse("F1 S1 W2 C2")
        assert assigned.max_water_cementitious == pytest.approx(0.40)

    def test_no_ratio_limit_at_all(self) -> None:
        assert ExposureSet().max_water_cementitious is None

    def test_the_highest_strength_wins(self) -> None:
        assert ExposureSet.parse("F1 S2 C1").min_strength == Quantity(4500, "psi")

    def test_the_tightest_chloride_wins(self) -> None:
        assert ExposureSet.parse("C1").max_chloride == Percent(0.30)

    def test_air_target_reads_the_freeze_thaw_class(self) -> None:
        assert ExposureSet.parse("F2 C2").air_target("1 in") == Percent(6.0)
        assert ExposureSet.parse("S3").air_target("1 in") is None


class CaseGoverningClass:
    assigned = ExposureSet.parse("F1 S1 W2 C2")

    def test_ratio(self) -> None:
        assert self.assigned.governing_class("max_water_cementitious") is ExposureClass.C2

    def test_strength(self) -> None:
        assert self.assigned.governing_class("min_strength") is ExposureClass.C2

    def test_chloride(self) -> None:
        assert self.assigned.governing_class("max_chloride") is ExposureClass.C2

    def test_no_class_governs_when_nothing_imposes_a_limit(self) -> None:
        assert ExposureSet().governing_class("max_water_cementitious") is None

    def test_an_unknown_attribute_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="governing class"):
            self.assigned.governing_class("max_slump")
