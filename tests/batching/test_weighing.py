from __future__ import annotations

import pytest

from slumpcone.batching.weighing import (
    SMALL_CHARGE_THRESHOLD,
    check_weighing,
    weighing_allowance,
    weighing_band,
)
from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.percent import Percent
from slumpcone.tolerance import Side
from slumpcone.units.quantity import Quantity

BIG_SCALE = Quantity(12000, "lb")
CEMENT_SCALE = Quantity(6000, "lb")


class CaseAllowance:
    def test_a_large_aggregate_charge_gets_two_percent(self) -> None:
        allowance = weighing_allowance(
            MaterialClass.COARSE_AGGREGATE, Quantity(8000, "lb"), BIG_SCALE
        )
        assert allowance.value == pytest.approx(160.0)

    def test_a_large_cement_charge_gets_one_percent(self) -> None:
        allowance = weighing_allowance(MaterialClass.CEMENT, Quantity(4000, "lb"), CEMENT_SCALE)
        assert allowance.value == pytest.approx(40.0)

    def test_water_gets_one_percent_with_no_scale(self) -> None:
        allowance = weighing_allowance(MaterialClass.WATER, Quantity(2250, "lb"))
        assert allowance.value == pytest.approx(22.5)

    def test_an_admixture_gets_three_percent(self) -> None:
        allowance = weighing_allowance(MaterialClass.ADMIXTURE, Quantity(20, "lb"))
        assert allowance.value == pytest.approx(0.6)

    def test_a_small_charge_takes_the_lesser_of_two_rules(self) -> None:
        # 1000 lb on a 12000 lb scale is 8.3 percent of capacity.
        # 0.3 percent of capacity is 36 lb, 3 percent of the charge is 30 lb.
        allowance = weighing_allowance(
            MaterialClass.COARSE_AGGREGATE, Quantity(1000, "lb"), BIG_SCALE
        )
        assert allowance.value == pytest.approx(30.0)

    def test_a_very_small_charge_is_capped_by_the_scale(self) -> None:
        # 2000 lb on a 12000 lb scale: 0.3 percent of capacity is 36 lb,
        # 3 percent of the charge is 60 lb, so the scale rule binds.
        allowance = weighing_allowance(
            MaterialClass.COARSE_AGGREGATE, Quantity(2000, "lb"), BIG_SCALE
        )
        assert allowance.value == pytest.approx(36.0)

    def test_the_small_charge_rule_is_tighter_than_the_plain_percentage(self) -> None:
        small = weighing_allowance(
            MaterialClass.COARSE_AGGREGATE, Quantity(2000, "lb"), BIG_SCALE
        )
        plain = Quantity(2000, "lb") * 0.02
        assert small < plain

    def test_the_threshold_is_thirty_percent_of_capacity(self) -> None:
        assert SMALL_CHARGE_THRESHOLD.value == pytest.approx(30.0)
        at_line = weighing_allowance(
            MaterialClass.COARSE_AGGREGATE, Quantity(3600, "lb"), BIG_SCALE
        )
        assert at_line.value == pytest.approx(72.0)

    def test_a_class_with_no_rule_of_its_own_falls_back(self) -> None:
        allowance = weighing_allowance(MaterialClass.FIBER, Quantity(100, "lb"))
        assert allowance.value == pytest.approx(2.0)

    def test_a_non_mass_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="required weight is a mass"):
            weighing_allowance(MaterialClass.CEMENT, Quantity(1, "yd3"))

    def test_a_negative_requirement_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            weighing_allowance(MaterialClass.CEMENT, Quantity(-1, "lb"))

    def test_a_bad_scale_capacity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="scale capacity is a mass"):
            weighing_allowance(MaterialClass.CEMENT, Quantity(1, "lb"), Quantity(1, "yd3"))
        with pytest.raises(ValidationError, match="has to be positive"):
            weighing_allowance(MaterialClass.CEMENT, Quantity(1, "lb"), Quantity(0, "lb"))


class CaseBand:
    def test_the_band_straddles_the_requirement(self) -> None:
        band = weighing_band(MaterialClass.CEMENT, Quantity(4000, "lb"), CEMENT_SCALE)
        assert band.low == pytest.approx(3960.0)
        assert band.high == pytest.approx(4040.0)


class CaseResult:
    def test_inside(self) -> None:
        result = check_weighing(
            "CEM-I",
            MaterialClass.CEMENT,
            Quantity(4000, "lb"),
            Quantity(4020, "lb"),
            CEMENT_SCALE,
        )
        assert result.conforms
        assert result.side is Side.IN
        assert result.error == Quantity(20, "lb")
        assert result.error_percent.value == pytest.approx(0.5)
        assert "ok" in result.describe()

    def test_over(self) -> None:
        result = check_weighing(
            "CEM-I",
            MaterialClass.CEMENT,
            Quantity(4000, "lb"),
            Quantity(4100, "lb"),
            CEMENT_SCALE,
        )
        assert not result.conforms
        assert result.side is Side.HIGH
        assert "out high" in result.describe()

    def test_under(self) -> None:
        result = check_weighing(
            "CA-57",
            MaterialClass.COARSE_AGGREGATE,
            Quantity(8000, "lb"),
            Quantity(7700, "lb"),
            BIG_SCALE,
        )
        assert result.side is Side.LOW

    def test_a_zero_requirement_reports_no_percentage(self) -> None:
        result = check_weighing(
            "AD-AE", MaterialClass.ADMIXTURE, Quantity(0, "lb"), Quantity(0, "lb")
        )
        assert result.error_percent == Percent(0.0)
        assert result.conforms

    def test_units_convert_on_the_way_in(self) -> None:
        result = check_weighing(
            "CEM-I",
            MaterialClass.CEMENT,
            Quantity(4000, "lb"),
            Quantity(1814, "kg"),
            CEMENT_SCALE,
        )
        assert result.conforms
