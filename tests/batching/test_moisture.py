from __future__ import annotations

import pytest

from slumpcone.batching.moisture import (
    MAX_TOTAL_MOISTURE,
    AggregateMoisture,
    correct_batch,
)
from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from tests.factories import proportions


def wet_stone(total: float = 1.5) -> AggregateMoisture:
    return AggregateMoisture("CA-57", Percent(total), Percent(0.7))


def wet_sand(total: float = 5.0) -> AggregateMoisture:
    return AggregateMoisture("FA-1", Percent(total), Percent(1.4))


class CaseReading:
    def test_code_is_normalised(self) -> None:
        assert AggregateMoisture("ca 57", Percent(1.5), Percent(0.7)).material_code == "CA-57"

    def test_free_moisture_is_the_difference(self) -> None:
        assert wet_stone().free_moisture == Percent(0.8)

    def test_a_dry_aggregate_reads_negative(self) -> None:
        dry = AggregateMoisture("CA-57", Percent(0.2), Percent(0.7))
        assert dry.is_dry
        assert dry.free_moisture.value == pytest.approx(-0.5)

    def test_a_wet_aggregate_is_not_dry(self) -> None:
        assert not wet_stone().is_dry

    def test_negative_total_moisture_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            AggregateMoisture("CA-57", Percent(-0.1), Percent(0.7))

    def test_an_impossible_reading_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="probe fault"):
            AggregateMoisture("CA-57", MAX_TOTAL_MOISTURE + Percent(0.1), Percent(0.7))

    def test_negative_absorption_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="absorption cannot be negative"):
            AggregateMoisture("CA-57", Percent(1.0), Percent(-0.1))

    def test_a_silly_absorption_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not an aggregate"):
            AggregateMoisture("CA-57", Percent(1.0), Percent(31.0))


class CaseFactor:
    def test_the_factor_is_not_one_plus_free(self) -> None:
        reading = AggregateMoisture("LW", Percent(14.0), Percent(12.0))
        shortcut = 1.0 + reading.free_moisture.fraction
        assert reading.factor == pytest.approx(1.0179, abs=1e-4)
        assert reading.factor < shortcut

    def test_ssd_aggregate_has_a_factor_of_one(self) -> None:
        assert AggregateMoisture("CA-57", Percent(0.7), Percent(0.7)).factor == pytest.approx(
            1.0
        )

    def test_batch_weight_is_heavier_when_wet(self) -> None:
        weight = wet_stone().batch_weight(Quantity(1780, "lb"))
        assert weight.value == pytest.approx(1794.14, abs=0.05)

    def test_batch_weight_is_lighter_when_dry(self) -> None:
        dry = AggregateMoisture("CA-57", Percent(0.2), Percent(0.7))
        assert dry.batch_weight(Quantity(1780, "lb")).value < 1780.0

    def test_free_water_follows_the_batch_weight(self) -> None:
        assert wet_stone().free_water(Quantity(1780, "lb")).value == pytest.approx(
            14.14, abs=0.05
        )

    def test_a_non_mass_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="SSD weight is a mass"):
            wet_stone().batch_weight(Quantity(1, "yd3"))


class CaseCorrectBatch:
    readings = {"CA-57": wet_stone(), "FA-1": wet_sand()}

    def test_the_aggregates_go_up(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        assert result.weight_of("CA-57") > result.design_weight_of("CA-57")
        assert result.weight_of("FA-1") > result.design_weight_of("FA-1")

    def test_the_water_comes_down_by_the_free_water(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        assert result.batch_water == result.design_water - result.free_water
        assert result.water_was_cut

    def test_the_cement_is_untouched(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        assert result.weight_of("CEM-I") == result.design_weight_of("CEM-I")

    def test_an_aggregate_with_no_reading_is_batched_dry(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), {"FA-1": wet_sand()})
        assert result.weight_of("CA-57") == result.design_weight_of("CA-57")

    def test_a_dry_pile_raises_the_water(self) -> None:
        dry = {"FA-1": AggregateMoisture("FA-1", Percent(0.2), Percent(1.4))}
        result = correct_batch(proportions(), Quantity(1, "yd3"), dry)
        assert result.batch_water > result.design_water
        assert not result.water_was_cut
        assert "raised" in result.describe()

    def test_it_scales_with_the_load(self) -> None:
        one = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        nine = correct_batch(proportions(), Quantity(9, "yd3"), self.readings)
        assert nine.weight_of("CEM-I").value == pytest.approx(one.weight_of("CEM-I").value * 9)

    def test_the_total_is_everything_on_the_scales(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        assert result.total_batch_weight.value == pytest.approx(
            sum(w.value for _, w in result.batch_weights)
        )

    def test_describe_says_which_way_it_went(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        assert "water cut from" in result.describe()

    def test_a_volume_is_required(self) -> None:
        with pytest.raises(ValidationError, match="batch size is a volume"):
            correct_batch(proportions(), Quantity(1, "lb"), self.readings)

    def test_a_positive_volume_is_required(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            correct_batch(proportions(), Quantity(0, "yd3"), self.readings)

    def test_more_free_water_than_mix_water_is_refused(self) -> None:
        drowned = {
            "CA-57": AggregateMoisture("CA-57", Percent(12.0), Percent(0.7)),
            "FA-1": AggregateMoisture("FA-1", Percent(12.0), Percent(1.4)),
        }
        with pytest.raises(ValidationError, match="more than the mix water"):
            correct_batch(proportions(), Quantity(1, "yd3"), drowned)

    def test_an_unknown_material_is_named(self) -> None:
        result = correct_batch(proportions(), Quantity(1, "yd3"), self.readings)
        with pytest.raises(ValidationError, match="not in this batch"):
            result.weight_of("CEM-III")
        with pytest.raises(ValidationError, match="not in this batch"):
            result.design_weight_of("CEM-III")
