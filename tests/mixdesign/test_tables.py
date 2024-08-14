from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.mixdesign.tables import (
    MODULI,
    SIZES,
    ExposureSeverity,
    SlumpBand,
    coarse_aggregate_factor,
    entrapped_air,
    ratio_for_strength,
    target_air,
    water_demand,
)
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

ONE_INCH = Quantity(1.0, "in")


class CaseSlumpBand:
    @pytest.mark.parametrize(
        ("inches", "band"),
        [
            (1.0, SlumpBand.LOW),
            (2.0, SlumpBand.LOW),
            (3.0, SlumpBand.MEDIUM),
            (4.0, SlumpBand.MEDIUM),
            (6.0, SlumpBand.HIGH),
            (7.0, SlumpBand.HIGH),
        ],
    )
    def test_the_bands(self, inches: float, band: SlumpBand) -> None:
        assert SlumpBand.of(Quantity(inches, "in")) is band

    def test_below_the_table(self) -> None:
        with pytest.raises(ValidationError, match="starts at a one inch"):
            SlumpBand.of(Quantity(0.5, "in"))

    def test_above_the_table_names_the_reason(self) -> None:
        with pytest.raises(ValidationError, match="high range admixture"):
            SlumpBand.of(Quantity(8.0, "in"))

    def test_a_non_length_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="slump is a length"):
            SlumpBand.of(Quantity(4, "lb"))

    def test_a_metric_slump_bands_the_same(self) -> None:
        assert SlumpBand.of(Quantity(100, "mm")) is SlumpBand.MEDIUM

    def test_prints_its_own_value(self) -> None:
        assert str(SlumpBand.MEDIUM) == "3 to 4 in"


class CaseWaterDemand:
    def test_a_plain_mixture(self) -> None:
        demand = water_demand(ONE_INCH, Quantity(4.0, "in"), air_entrained=False)
        assert demand.value == pytest.approx(325.0)

    def test_entrainment_lowers_the_demand(self) -> None:
        plain = water_demand(ONE_INCH, Quantity(4.0, "in"), air_entrained=False)
        entrained = water_demand(ONE_INCH, Quantity(4.0, "in"), air_entrained=True)
        assert entrained < plain

    def test_a_bigger_aggregate_lowers_it_too(self) -> None:
        small = water_demand(Quantity(0.5, "in"), Quantity(4.0, "in"), air_entrained=False)
        big = water_demand(Quantity(1.5, "in"), Quantity(4.0, "in"), air_entrained=False)
        assert big < small

    def test_a_wetter_mixture_wants_more(self) -> None:
        stiff = water_demand(ONE_INCH, Quantity(2.0, "in"), air_entrained=False)
        wet = water_demand(ONE_INCH, Quantity(7.0, "in"), air_entrained=False)
        assert wet > stiff

    def test_it_does_not_interpolate_within_a_band(self) -> None:
        three = water_demand(ONE_INCH, Quantity(3.0, "in"), air_entrained=False)
        four = water_demand(ONE_INCH, Quantity(4.0, "in"), air_entrained=False)
        assert three == four

    def test_an_aggregate_the_table_has_no_row_for(self) -> None:
        with pytest.raises(ValidationError, match="no row for a 1.25 inch"):
            water_demand(Quantity(1.25, "in"), Quantity(4.0, "in"), air_entrained=False)

    def test_a_non_length_size_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a length"):
            water_demand(Quantity(1, "lb"), Quantity(4.0, "in"), air_entrained=False)


class CaseAir:
    def test_entrapped_air_falls_with_aggregate_size(self) -> None:
        assert entrapped_air(Quantity(0.375, "in")) == Percent(3.0)
        assert entrapped_air(Quantity(3.0, "in")) == Percent(0.3)

    def test_target_air_by_severity(self) -> None:
        assert target_air(ONE_INCH, ExposureSeverity.MILD) == Percent(3.0)
        assert target_air(ONE_INCH, ExposureSeverity.MODERATE) == Percent(4.5)
        assert target_air(ONE_INCH, ExposureSeverity.SEVERE) == Percent(6.0)

    def test_severity_prints_its_own_value(self) -> None:
        assert str(ExposureSeverity.SEVERE) == "severe"

    def test_every_size_has_a_row(self) -> None:
        for size in SIZES:
            assert entrapped_air(Quantity(size, "in")).value > 0.0


class CaseCoarseFactor:
    def test_the_table_corners(self) -> None:
        assert coarse_aggregate_factor(ONE_INCH, 2.40) == pytest.approx(0.71)
        assert coarse_aggregate_factor(ONE_INCH, 3.00) == pytest.approx(0.65)

    def test_it_interpolates_on_fineness_modulus(self) -> None:
        assert coarse_aggregate_factor(ONE_INCH, 2.70) == pytest.approx(0.68)
        assert coarse_aggregate_factor(ONE_INCH, 2.84) == pytest.approx(0.666, abs=1e-3)

    def test_a_coarser_sand_leaves_room_for_less_stone(self) -> None:
        fine = coarse_aggregate_factor(ONE_INCH, 2.40)
        coarse = coarse_aggregate_factor(ONE_INCH, 3.00)
        assert coarse < fine

    def test_a_bigger_aggregate_packs_more(self) -> None:
        small = coarse_aggregate_factor(Quantity(0.375, "in"), 2.80)
        big = coarse_aggregate_factor(Quantity(1.5, "in"), 2.80)
        assert big > small

    def test_outside_the_table_is_refused_not_clamped(self) -> None:
        with pytest.raises(ValidationError, match="outside the 2.40 to 3.00"):
            coarse_aggregate_factor(ONE_INCH, 3.40)
        with pytest.raises(ValidationError):
            coarse_aggregate_factor(ONE_INCH, 2.10)

    def test_the_index(self) -> None:
        assert MODULI[0] == pytest.approx(2.40)


class CaseRatioForStrength:
    def test_the_table_rows(self) -> None:
        assert ratio_for_strength(Quantity(4000, "psi"), air_entrained=False) == pytest.approx(
            0.57
        )
        assert ratio_for_strength(Quantity(4000, "psi"), air_entrained=True) == pytest.approx(
            0.48
        )

    def test_it_interpolates_between_rows(self) -> None:
        assert ratio_for_strength(Quantity(4500, "psi"), air_entrained=False) == pytest.approx(
            0.525
        )

    def test_a_stronger_mixture_wants_a_lower_ratio(self) -> None:
        low = ratio_for_strength(Quantity(3000, "psi"), air_entrained=False)
        high = ratio_for_strength(Quantity(6000, "psi"), air_entrained=False)
        assert high < low

    def test_entrainment_tightens_the_ratio(self) -> None:
        plain = ratio_for_strength(Quantity(4000, "psi"), air_entrained=False)
        entrained = ratio_for_strength(Quantity(4000, "psi"), air_entrained=True)
        assert entrained < plain

    def test_above_the_table_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="outside the 2000 to 6000"):
            ratio_for_strength(Quantity(7000, "psi"), air_entrained=False)

    def test_the_entrained_table_stops_lower(self) -> None:
        with pytest.raises(ValidationError, match="outside the 2000 to 5000"):
            ratio_for_strength(Quantity(6000, "psi"), air_entrained=True)

    def test_a_non_pressure_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="strength is a pressure"):
            ratio_for_strength(Quantity(4000, "lb"), air_entrained=False)

    def test_a_metric_strength_works(self) -> None:
        assert ratio_for_strength(Quantity(27.58, "MPa"), air_entrained=False) == pytest.approx(
            0.57, abs=1e-3
        )
