from __future__ import annotations

from datetime import timedelta

import pytest

from slumpcone.materials.wash_water import (
    RETURNED_AGE_LIMIT,
    RETURNED_SHARE_LIMIT,
    SOLIDS_LIMIT_PPM,
    ReturnedConcrete,
    WashWater,
    WashWaterError,
    blend_into,
    usable_tanks,
)
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


def tank(
    specific_gravity: float = 1.02, *, name: str = "WW-1", gallons: float = 2000.0
) -> WashWater:
    return WashWater(name, specific_gravity, Quantity(gallons, "gal"))


def returned(
    *, yards: float = 3.0, minutes: float = 45.0, number: str = "881204"
) -> ReturnedConcrete:
    return ReturnedConcrete(
        number, "4000P-57", Quantity(yards, "yd3"), timedelta(minutes=minutes)
    )


class CaseSolids:
    def test_clean_water_carries_none(self) -> None:
        assert tank(1.000).solids_ppm == pytest.approx(0.0)
        assert tank(1.000).solids_share.value == pytest.approx(0.0)

    def test_a_light_tank(self) -> None:
        assert tank(1.02).solids_ppm == pytest.approx(35948.0, rel=1e-4)

    def test_the_share_is_the_ppm_over_ten_thousand(self) -> None:
        assert tank(1.02).solids_share.value == pytest.approx(3.5948, rel=1e-4)

    def test_a_denser_tank_carries_more(self) -> None:
        assert tank(1.05).solids_ppm > tank(1.02).solids_ppm

    def test_a_tank_inside_the_limit(self) -> None:
        assert tank(1.02).meets_solids_limit

    def test_a_tank_over_the_limit(self) -> None:
        assert not tank(1.05).meets_solids_limit

    def test_the_limit_is_where_the_standard_puts_it(self) -> None:
        assert pytest.approx(50_000.0) == SOLIDS_LIMIT_PPM

    def test_water_lighter_than_water(self) -> None:
        with pytest.raises(WashWaterError) as caught:
            tank(0.99)
        assert caught.value.code == "WASH_WATER_LIGHTER_THAN_WATER"

    def test_a_negative_tank(self) -> None:
        with pytest.raises(WashWaterError) as caught:
            WashWater("WW-1", 1.02, Quantity(-1.0, "gal"))
        assert caught.value.code == "WASH_WATER_NEGATIVE_VOLUME"

    def test_describe(self) -> None:
        assert "usable" in tank(1.02).describe()
        assert "over the solids limit" in tank(1.05).describe()


class CaseDrawing:
    def test_a_draw_is_mostly_water(self) -> None:
        drawn = Quantity(100.0, "gal")
        assert tank(1.02).water_in(drawn).value == pytest.approx(
            100.0 * (1 - 0.035948), rel=1e-4
        )

    def test_the_rest_is_solids(self) -> None:
        drawn = Quantity(100.0, "gal")
        one = tank(1.02)
        assert (one.water_in(drawn) + one.solids_in(drawn)).value == pytest.approx(100.0)

    def test_clean_water_is_all_water(self) -> None:
        drawn = Quantity(100.0, "gal")
        assert tank(1.000).water_in(drawn).value == pytest.approx(100.0)
        assert tank(1.000).solids_in(drawn).is_zero()

    def test_drawing_the_whole_tank(self) -> None:
        assert tank(gallons=100.0).water_in(Quantity(100.0, "gal")).value > 0.0

    def test_overdrawing(self) -> None:
        with pytest.raises(WashWaterError) as caught:
            tank(gallons=100.0).water_in(Quantity(101.0, "gal"))
        assert caught.value.code == "WASH_WATER_OVERDRAWN"

    def test_the_refusal_names_both_volumes(self) -> None:
        with pytest.raises(WashWaterError) as caught:
            tank(gallons=100.0).water_in(Quantity(101.0, "gal"))
        assert "100.0 gal" in str(caught.value)


class CaseTanks:
    def test_nothing_on_the_rack(self) -> None:
        assert usable_tanks([]) == ()

    def test_the_cleanest_comes_first(self) -> None:
        found = usable_tanks([tank(1.025, name="WW-2"), tank(1.01, name="WW-1")])
        assert [one.tank for one in found] == ["WW-1", "WW-2"]

    def test_a_dirty_tank_is_left_out(self) -> None:
        found = usable_tanks([tank(1.02, name="WW-1"), tank(1.08, name="WW-2")])
        assert [one.tank for one in found] == ["WW-1"]

    def test_every_tank_dirty(self) -> None:
        assert usable_tanks([tank(1.08), tank(1.09)]) == ()


class CaseReturned:
    def test_it_holds_what_it_was_given(self) -> None:
        one = returned()
        assert one.volume == Quantity(3.0, "yd3")
        assert one.age_at_return == timedelta(minutes=45)

    def test_a_young_load_is_usable(self) -> None:
        assert returned(minutes=45).is_usable()

    def test_an_old_load_is_not(self) -> None:
        assert not returned(minutes=150).is_usable()

    def test_the_limit_is_two_hours(self) -> None:
        assert timedelta(hours=2) == RETURNED_AGE_LIMIT
        assert returned(minutes=120).is_usable()
        assert not returned(minutes=121).is_usable()

    def test_waiting_on_the_yard_ages_it(self) -> None:
        one = returned(minutes=90)
        assert one.is_usable()
        assert not one.is_usable(timedelta(minutes=45))

    def test_the_age_after_waiting(self) -> None:
        assert returned(minutes=45).age_at(timedelta(minutes=30)) == timedelta(minutes=75)

    def test_a_zero_volume(self) -> None:
        with pytest.raises(WashWaterError) as caught:
            returned(yards=0.0)
        assert caught.value.code == "RETURNED_NO_VOLUME"

    def test_a_negative_age(self) -> None:
        with pytest.raises(WashWaterError) as caught:
            ReturnedConcrete("881204", "4000P-57", Quantity(3.0, "yd3"), timedelta(-1))
        assert caught.value.code == "RETURNED_NEGATIVE_AGE"

    def test_describe(self) -> None:
        assert "usable" in returned().describe()
        assert "too old to reuse" in returned(minutes=200).describe()


class CaseBlending:
    def test_the_cap_is_fifteen_percent(self) -> None:
        assert Percent(15.0) == RETURNED_SHARE_LIMIT

    def test_a_nine_yard_load_takes_a_yard_and_a_third(self) -> None:
        found = returned(yards=3.0).most_into(Quantity(9.0, "yd3"))
        assert found.value == pytest.approx(1.35)

    def test_it_never_offers_more_than_there_is(self) -> None:
        found = returned(yards=0.5).most_into(Quantity(9.0, "yd3"))
        assert found.value == pytest.approx(0.5)

    def test_a_tighter_cap(self) -> None:
        found = returned(yards=3.0).most_into(Quantity(9.0, "yd3"), cap=Percent(5.0))
        assert found.value == pytest.approx(0.45)

    def test_blending_a_young_load(self) -> None:
        assert blend_into(returned(minutes=45), Quantity(9.0, "yd3")).value > 0.0

    def test_blending_an_old_load_gives_nothing(self) -> None:
        assert blend_into(returned(minutes=200), Quantity(9.0, "yd3")).is_zero()

    def test_a_load_that_ages_out_while_it_waits(self) -> None:
        found = blend_into(
            returned(minutes=110), Quantity(9.0, "yd3"), waited=timedelta(minutes=30)
        )
        assert found.is_zero()

    def test_the_refusal_keeps_the_unit(self) -> None:
        found = blend_into(returned(minutes=200), Quantity(9.0, "yd3"))
        assert found.unit == "yd3"

    def test_a_cap_that_the_purchaser_agreed_to_raise(self) -> None:
        found = blend_into(returned(yards=3.0), Quantity(9.0, "yd3"), cap=Percent(30.0))
        assert found.value == pytest.approx(2.7)
