from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.breaks import (
    CORRECTION_THRESHOLD,
    BreakResult,
    FractureType,
    length_diameter_correction,
)
from slumpcone.units.quantity import Quantity

TESTED = datetime(2024, 7, 10, 10, 15)


def result(**overrides: object) -> BreakResult:
    fields: dict[str, object] = {
        "specimen_code": "C-4471-A",
        "tested_at": TESTED,
        "age_days": 28.0,
        "diameter_one": Quantity(4.01, "in"),
        "diameter_two": Quantity(4.00, "in"),
        "length": Quantity(8.02, "in"),
        "max_load": Quantity(63000, "lbf"),
    }
    fields.update(overrides)
    return BreakResult(**fields)  # type: ignore[arg-type]


class CaseFractureType:
    def test_parse(self) -> None:
        assert FractureType.parse("cone") is FractureType.CONE
        assert FractureType.parse("side fracture") is FractureType.SIDE_FRACTURE

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="fracture type"):
            FractureType.parse("crumbled")

    def test_which_patterns_point_at_the_setup(self) -> None:
        assert FractureType.SIDE_FRACTURE.suggests_a_testing_fault
        assert FractureType.POINTED_END.suggests_a_testing_fault
        assert not FractureType.CONE.suggests_a_testing_fault
        assert not FractureType.COLUMNAR.suggests_a_testing_fault

    def test_prints_its_own_value(self) -> None:
        assert str(FractureType.CONE_AND_SPLIT) == "cone_and_split"


class CaseCorrection:
    def test_a_full_length_cylinder_needs_no_correction(self) -> None:
        assert length_diameter_correction(2.0) == pytest.approx(1.0)
        assert length_diameter_correction(CORRECTION_THRESHOLD) == pytest.approx(1.0)

    @pytest.mark.parametrize(
        ("ratio", "factor"),
        [(1.75, 1.0), (1.50, 0.96), (1.25, 0.93), (1.00, 0.87)],
    )
    def test_the_table_rows(self, ratio: float, factor: float) -> None:
        assert length_diameter_correction(ratio) == pytest.approx(factor)

    def test_between_two_rows_it_interpolates(self) -> None:
        assert length_diameter_correction(1.375) == pytest.approx(0.945)

    def test_below_the_table_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="correction table covers"):
            length_diameter_correction(0.9)

    def test_a_non_positive_ratio_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            length_diameter_correction(0.0)


class CaseConstruction:
    def test_codes_are_normalised(self) -> None:
        built = result(specimen_code=" c 4471 a ", tested_by="tech 7")
        assert built.specimen_code == "C-4471-A"
        assert built.tested_by == "TECH-7"

    def test_the_dimensions_have_to_be_lengths(self) -> None:
        with pytest.raises(ValidationError, match="diameter_one is a length"):
            result(diameter_one=Quantity(4, "lb"))

    def test_the_dimensions_have_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="length has to be positive"):
            result(length=Quantity(0, "in"))

    def test_the_load_has_to_be_a_force(self) -> None:
        with pytest.raises(ValidationError, match="load is a force"):
            result(max_load=Quantity(63000, "lb"))

    def test_the_load_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="load has to be positive"):
            result(max_load=Quantity(0, "lbf"))

    def test_the_age_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="age at test has to be positive"):
            result(age_days=0.0)


class CaseGeometry:
    def test_the_diameter_is_the_average(self) -> None:
        assert result().diameter.value == pytest.approx(4.005)

    def test_a_round_cylinder(self) -> None:
        assert result().diameter_difference.value == pytest.approx(0.25, abs=0.01)
        assert not result().is_out_of_round

    def test_an_out_of_round_cylinder(self) -> None:
        broken = result(diameter_one=Quantity(4.10, "in"), diameter_two=Quantity(4.00, "in"))
        assert broken.is_out_of_round
        assert "out of round" in broken.describe()

    def test_area_follows_the_measured_diameter(self) -> None:
        assert result().area == pytest.approx(12.60, abs=0.01)

    def test_the_length_to_diameter_ratio(self) -> None:
        assert result().length_diameter_ratio == pytest.approx(2.002, abs=1e-3)
        assert not result().needs_correction


class CaseStrength:
    def test_a_full_length_cylinder(self) -> None:
        assert result().strength.value == pytest.approx(4999.0, abs=5.0)
        assert result().correction == pytest.approx(1.0)

    def test_a_short_cylinder_is_corrected_down(self) -> None:
        short = result(length=Quantity(6.0, "in"))
        assert short.needs_correction
        assert short.correction < 1.0
        assert short.strength < short.uncorrected_strength

    def test_the_correction_is_the_table_value(self) -> None:
        short = result(length=Quantity(6.0075, "in"))
        assert short.correction == pytest.approx(0.96, abs=1e-3)

    def test_a_metric_load_converts(self) -> None:
        metric = result(max_load=Quantity(280.2, "kN"))
        assert metric.strength.value == pytest.approx(4999.0, abs=15.0)

    def test_describe(self) -> None:
        line = result().describe()
        assert "C-4471-A" in line
        assert "28 d" in line
        assert "cone" in line
