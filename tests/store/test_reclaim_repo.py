from __future__ import annotations

from datetime import date, timedelta

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.materials.wash_water import ReturnedConcrete, WashWater
from slumpcone.register import Register
from slumpcone.units.quantity import Quantity

DAY = date(2024, 6, 12)
LATER = date(2024, 6, 13)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


def tank(name: str = "WW-1", specific_gravity: float = 1.02) -> WashWater:
    return WashWater(name, specific_gravity, Quantity(2000.0, "gal"))


def returned(number: str = "881204", *, minutes: float = 45.0) -> ReturnedConcrete:
    return ReturnedConcrete(
        number, "4000P-57", Quantity(3.0, "yd3"), timedelta(minutes=minutes)
    )


class CaseReadings:
    def test_a_reading_round_trips(self, register: Register) -> None:
        register.reclaim.save_reading(tank(), "PL-1", DAY)
        assert register.reclaim.reading("PL-1", "WW-1", DAY) == tank()

    def test_the_volume_unit_survives(self, register: Register) -> None:
        register.reclaim.save_reading(WashWater("WW-1", 1.02, Quantity(7.5, "m3")), "PL-1", DAY)
        back = register.reclaim.reading("PL-1", "WW-1", DAY)
        assert back.volume.unit == "m3"

    def test_yesterdays_reading_is_not_overwritten(self, register: Register) -> None:
        register.reclaim.save_reading(tank(specific_gravity=1.01), "PL-1", DAY)
        register.reclaim.save_reading(tank(specific_gravity=1.04), "PL-1", LATER)
        assert register.reclaim.reading("PL-1", "WW-1", DAY).specific_gravity == pytest.approx(
            1.01
        )

    def test_the_same_tank_twice_in_a_day(self, register: Register) -> None:
        register.reclaim.save_reading(tank(), "PL-1", DAY)
        with pytest.raises(ConflictError):
            register.reclaim.save_reading(tank(), "PL-1", DAY)

    def test_replace_takes_the_new_reading(self, register: Register) -> None:
        register.reclaim.save_reading(tank(specific_gravity=1.01), "PL-1", DAY)
        register.reclaim.save_reading(tank(specific_gravity=1.04), "PL-1", DAY, replace=True)
        assert register.reclaim.reading("PL-1", "WW-1", DAY).specific_gravity == pytest.approx(
            1.04
        )

    def test_an_unknown_reading(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.reclaim.reading("PL-1", "WW-1", DAY)

    def test_the_days_readings_are_in_tank_order(self, register: Register) -> None:
        register.reclaim.save_reading(tank("WW-2"), "PL-1", DAY)
        register.reclaim.save_reading(tank("WW-1"), "PL-1", DAY)
        found = register.reclaim.readings_on("PL-1", DAY)
        assert [one.tank for one in found] == ["WW-1", "WW-2"]

    def test_another_plant_is_separate(self, register: Register) -> None:
        register.reclaim.save_reading(tank(), "PL-1", DAY)
        assert register.reclaim.readings_on("PL-2", DAY) == ()

    def test_only_the_clean_tanks(self, register: Register) -> None:
        register.reclaim.save_reading(tank("WW-1", 1.02), "PL-1", DAY)
        register.reclaim.save_reading(tank("WW-2", 1.08), "PL-1", DAY)
        found = register.reclaim.usable_on("PL-1", DAY)
        assert [one.tank for one in found] == ["WW-1"]

    def test_the_latest_reading(self, register: Register) -> None:
        register.reclaim.save_reading(tank(specific_gravity=1.01), "PL-1", DAY)
        register.reclaim.save_reading(tank(specific_gravity=1.04), "PL-1", LATER)
        latest = register.reclaim.latest_reading("PL-1", "WW-1")
        assert latest is not None
        assert latest.specific_gravity == pytest.approx(1.04)

    def test_a_tank_never_read(self, register: Register) -> None:
        assert register.reclaim.latest_reading("PL-1", "WW-9") is None


class CaseReturnedLoads:
    def test_it_round_trips(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        assert register.reclaim.returned("881204") == returned()

    def test_the_age_survives(self, register: Register) -> None:
        register.reclaim.save_returned(returned(minutes=95), DAY)
        assert register.reclaim.returned("881204").age_at_return == timedelta(minutes=95)

    def test_the_same_ticket_twice(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        with pytest.raises(ConflictError):
            register.reclaim.save_returned(returned(), DAY)

    def test_an_unknown_load(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.reclaim.returned("881204")

    def test_the_window(self, register: Register) -> None:
        register.reclaim.save_returned(returned("881204"), DAY)
        register.reclaim.save_returned(returned("881205"), LATER)
        assert len(register.reclaim.returned_between(DAY, DAY)) == 1
        assert len(register.reclaim.returned_between(DAY, LATER)) == 2

    def test_forgetting_one(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.forget("881204")
        with pytest.raises(NotFoundError):
            register.reclaim.returned("881204")

    def test_forgetting_one_that_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.reclaim.forget("881204")


class CaseFate:
    def test_a_fresh_return_has_no_fate(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        assert register.reclaim.fate_of("881204") == (None, None)

    def test_using_it(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.use_in("881204", "881210")
        assert register.reclaim.fate_of("881204") == ("881210", None)

    def test_dumping_it(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.dispose("881204", LATER)
        assert register.reclaim.fate_of("881204") == (None, LATER)

    def test_using_it_clears_a_disposal(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.dispose("881204", LATER)
        register.reclaim.use_in("881204", "881210")
        assert register.reclaim.fate_of("881204") == ("881210", None)

    def test_dumping_it_clears_a_use(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.use_in("881204", "881210")
        register.reclaim.dispose("881204", LATER)
        assert register.reclaim.fate_of("881204") == (None, LATER)

    def test_a_fate_for_a_load_that_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.reclaim.fate_of("881204")

    def test_using_a_load_that_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.reclaim.use_in("881204", "881210")

    def test_dumping_a_load_that_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.reclaim.dispose("881204", LATER)


class CaseOnTheYard:
    def test_a_fresh_return_is_on_the_yard(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        assert len(register.reclaim.still_on_the_yard(DAY)) == 1

    def test_a_used_load_is_not(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.use_in("881204", "881210")
        assert register.reclaim.still_on_the_yard(DAY) == ()

    def test_a_dumped_load_is_not(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), DAY)
        register.reclaim.dispose("881204", DAY)
        assert register.reclaim.still_on_the_yard(DAY) == ()

    def test_a_load_returned_later_does_not_show_yet(self, register: Register) -> None:
        register.reclaim.save_returned(returned(), LATER)
        assert register.reclaim.still_on_the_yard(DAY) == ()

    def test_an_empty_yard(self, register: Register) -> None:
        assert register.reclaim.still_on_the_yard(DAY) == ()


def test_the_health_check_counts_returned_loads(register: Register) -> None:
    register.reclaim.save_returned(returned(), DAY)
    assert register.health().counts["returned_concrete"] == 1
