from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.weather import (
    DEFAULT_MAX_PLACEMENT,
    AmbientBand,
    SectionSize,
    judge_mixing_temperature,
    judge_placement_temperature,
    min_mixing_temperature,
)
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature


class CaseSectionSize:
    @pytest.mark.parametrize(
        ("inches", "expected"),
        [
            (6.0, SectionSize.THIN),
            (11.9, SectionSize.THIN),
            (12.0, SectionSize.MODERATE),
            (35.9, SectionSize.MODERATE),
            (36.0, SectionSize.THICK),
            (72.0, SectionSize.THICK),
            (72.1, SectionSize.MASS),
        ],
    )
    def test_bands(self, inches: float, expected: SectionSize) -> None:
        assert SectionSize.of(Quantity(inches, "in")) is expected

    def test_a_metric_dimension_works(self) -> None:
        assert SectionSize.of(Quantity(400, "mm")) is SectionSize.MODERATE

    def test_a_non_length_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a length"):
            SectionSize.of(Quantity(12, "lb"))

    def test_a_non_positive_dimension_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            SectionSize.of(Quantity(0, "in"))

    def test_placement_floors(self) -> None:
        assert SectionSize.THIN.min_placement == Temperature(55, "F")
        assert SectionSize.MODERATE.min_placement == Temperature(50, "F")
        assert SectionSize.THICK.min_placement == Temperature(45, "F")
        assert SectionSize.MASS.min_placement == Temperature(40, "F")

    def test_prints_its_own_value(self) -> None:
        assert str(SectionSize.MASS) == "mass"


class CaseAmbientBand:
    @pytest.mark.parametrize(
        ("degrees", "expected"),
        [
            (60.0, AmbientBand.ABOVE_FREEZING),
            (30.1, AmbientBand.ABOVE_FREEZING),
            (30.0, AmbientBand.COLD),
            (0.0, AmbientBand.COLD),
            (-0.1, AmbientBand.SEVERE),
        ],
    )
    def test_bands(self, degrees: float, expected: AmbientBand) -> None:
        assert AmbientBand.of(Temperature(degrees, "F")) is expected

    def test_a_celsius_reading_bands_the_same(self) -> None:
        assert AmbientBand.of(Temperature(-20, "C")) is AmbientBand.SEVERE

    def test_the_increments(self) -> None:
        assert AmbientBand.ABOVE_FREEZING.extra_over_placement == pytest.approx(5.0)
        assert AmbientBand.COLD.extra_over_placement == pytest.approx(10.0)
        assert AmbientBand.SEVERE.extra_over_placement == pytest.approx(15.0)

    def test_prints_its_own_value(self) -> None:
        assert str(AmbientBand.COLD) == "cold"


class CaseMixingMinimum:
    def test_a_thin_section_on_a_mild_day(self) -> None:
        assert min_mixing_temperature(SectionSize.THIN, Temperature(45, "F")) == Temperature(
            60, "F"
        )

    def test_the_same_section_on_a_cold_day(self) -> None:
        assert min_mixing_temperature(SectionSize.THIN, Temperature(20, "F")) == Temperature(
            65, "F"
        )

    def test_the_same_section_in_severe_cold(self) -> None:
        assert min_mixing_temperature(SectionSize.THIN, Temperature(-10, "F")) == Temperature(
            70, "F"
        )

    def test_a_mass_section_in_severe_cold(self) -> None:
        assert min_mixing_temperature(SectionSize.MASS, Temperature(-10, "F")) == Temperature(
            55, "F"
        )


class CasePlacement:
    def test_inside_both_limits(self) -> None:
        verdict = judge_placement_temperature(Temperature(72, "F"), Quantity(8, "in"))
        assert verdict.conforms
        assert "inside" in verdict.describe()

    def test_below_the_floor(self) -> None:
        verdict = judge_placement_temperature(Temperature(50, "F"), Quantity(8, "in"))
        assert verdict.too_cold
        assert not verdict.conforms
        assert "below the" in verdict.describe()
        assert "as placed" in verdict.describe()

    def test_a_thicker_section_allows_it(self) -> None:
        verdict = judge_placement_temperature(Temperature(50, "F"), Quantity(24, "in"))
        assert verdict.conforms

    def test_above_the_ceiling(self) -> None:
        verdict = judge_placement_temperature(Temperature(98, "F"), Quantity(8, "in"))
        assert verdict.too_hot
        assert "above the" in verdict.describe()

    def test_the_ceiling_is_adjustable(self) -> None:
        verdict = judge_placement_temperature(
            Temperature(80, "F"), Quantity(96, "in"), maximum=Temperature(70, "F")
        )
        assert verdict.too_hot

    def test_the_default_ceiling(self) -> None:
        assert DEFAULT_MAX_PLACEMENT.fahrenheit == pytest.approx(95.0)


class CaseMixing:
    def test_a_load_warm_enough_to_place_can_still_be_too_cold_to_leave(self) -> None:
        placement = judge_placement_temperature(Temperature(57, "F"), Quantity(8, "in"))
        mixing = judge_mixing_temperature(
            Temperature(57, "F"), Quantity(8, "in"), Temperature(20, "F")
        )
        assert placement.conforms
        assert mixing.too_cold
        assert "as mixed" in mixing.describe()

    def test_a_mild_day_asks_for_less(self) -> None:
        mixing = judge_mixing_temperature(
            Temperature(62, "F"), Quantity(8, "in"), Temperature(50, "F")
        )
        assert mixing.conforms

    def test_the_ceiling_still_applies(self) -> None:
        mixing = judge_mixing_temperature(
            Temperature(99, "F"), Quantity(8, "in"), Temperature(90, "F")
        )
        assert mixing.too_hot
