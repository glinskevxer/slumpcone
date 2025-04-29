from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.delivery.record import Delivery
from slumpcone.dispatch.schedule import CycleTime, ScheduleError
from slumpcone.errors import NotFoundError
from slumpcone.register import Register

DAY = date(2024, 6, 12)
BATCH = datetime(2024, 6, 12, 6, 30)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


def cycle(
    *, loading: int = 10, out: int = 20, site: int = 15, back: int = 20, wash: int = 5
) -> CycleTime:
    return CycleTime(
        timedelta(minutes=loading),
        timedelta(minutes=out),
        timedelta(minutes=site),
        timedelta(minutes=back),
        timedelta(minutes=wash),
    )


def delivery(number: str, *, out_minutes: int = 22, site_minutes: int = 14) -> Delivery:
    left = BATCH + timedelta(minutes=10)
    arrived = left + timedelta(minutes=out_minutes)
    started = arrived + timedelta(minutes=3)
    return Delivery(
        number,
        "TR-1",
        BATCH,
        left_plant_at=left,
        arrived_at=arrived,
        discharge_started_at=started,
        discharge_finished_at=started + timedelta(minutes=site_minutes),
    )


class CaseSaving:
    def test_a_profile_round_trips(self, register: Register) -> None:
        register.haul.save("P-2024-118", cycle())
        assert register.haul.get("P-2024-118") == cycle()

    def test_saving_again_replaces(self, register: Register) -> None:
        register.haul.save("P-2024-118", cycle())
        register.haul.save("P-2024-118", cycle(out=45))
        assert register.haul.get("P-2024-118").haul_out == timedelta(minutes=45)

    def test_the_code_is_normalised(self, register: Register) -> None:
        register.haul.save(" p-2024-118 ", cycle())
        assert register.haul.get("P-2024-118") == cycle()

    def test_an_unknown_profile(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.haul.get("P-2024-118")

    def test_the_fallback_is_used_when_nothing_is_on_file(self, register: Register) -> None:
        assert register.haul.get_or("P-2024-118", cycle(out=99)) == cycle(out=99)

    def test_the_fallback_is_ignored_when_something_is(self, register: Register) -> None:
        register.haul.save("P-2024-118", cycle())
        assert register.haul.get_or("P-2024-118", cycle(out=99)) == cycle()

    def test_the_listing(self, register: Register) -> None:
        register.haul.save("P-2", cycle())
        register.haul.save("P-1", cycle())
        assert register.haul.projects() == ("P-1", "P-2")

    def test_forgetting_one(self, register: Register) -> None:
        register.haul.save("P-2024-118", cycle())
        register.haul.forget("P-2024-118")
        assert register.haul.projects() == ()

    def test_forgetting_one_that_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.haul.forget("P-2024-118")


class CaseProvenance:
    def test_a_hand_entered_profile_says_so(self, register: Register) -> None:
        register.haul.save("P-2024-118", cycle(), notes="off the map")
        measured, count, notes = register.haul.provenance("P-2024-118")
        assert measured is None
        assert count == 0
        assert notes == "off the map"

    def test_a_measured_profile_carries_its_day_and_count(self, register: Register) -> None:
        register.haul.save(
            "P-2024-118", cycle(), measured_on=DAY, from_deliveries=12, notes="fitted"
        )
        measured, count, notes = register.haul.provenance("P-2024-118")
        assert measured == DAY
        assert count == 12
        assert notes == "fitted"

    def test_provenance_of_an_unknown_profile(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.haul.provenance("P-2024-118")


class CaseFitting:
    def test_it_fits_from_the_records(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        fitted = register.haul.fit("P-2024-118", records)
        assert fitted.haul_out == timedelta(minutes=22)
        assert fitted.on_site == timedelta(minutes=14)

    def test_the_run_home_matches_the_run_out_by_default(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        fitted = register.haul.fit("P-2024-118", records)
        assert fitted.haul_back == fitted.haul_out

    def test_the_run_home_can_be_stated(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        fitted = register.haul.fit("P-2024-118", records, haul_back=timedelta(minutes=18))
        assert fitted.haul_back == timedelta(minutes=18)

    def test_loading_and_washing_stay_the_callers(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        fitted = register.haul.fit(
            "P-2024-118",
            records,
            loading=timedelta(minutes=7),
            wash=timedelta(minutes=3),
        )
        assert fitted.loading == timedelta(minutes=7)
        assert fitted.wash == timedelta(minutes=3)

    def test_one_bad_afternoon_does_not_move_the_median(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        records.append(delivery("881299", site_minutes=180))
        fitted = register.haul.fit("P-2024-118", records)
        assert fitted.on_site == timedelta(minutes=14)

    def test_a_mean_would_have_moved(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        records.append(delivery("881299", site_minutes=180))
        minutes = [14.0, 14.0, 14.0, 14.0, 180.0]
        assert sum(minutes) / len(minutes) > 14.0
        assert register.haul.fit("P-2024-118", records).on_site == timedelta(minutes=14)

    def test_the_fit_is_filed(self, register: Register) -> None:
        records = [delivery(f"88120{index}") for index in range(4)]
        register.haul.fit("P-2024-118", records, measured_on=DAY)
        measured, count, notes = register.haul.provenance("P-2024-118")
        assert measured == DAY
        assert count == 4
        assert "fitted" in notes

    def test_too_few_records(self, register: Register) -> None:
        with pytest.raises(ScheduleError) as caught:
            register.haul.fit("P-2024-118", [delivery("881204")])
        assert caught.value.code == "HAUL_FIT_TOO_THIN"

    def test_records_missing_their_moments_do_not_count(self, register: Register) -> None:
        bare = [Delivery(f"88120{index}", "TR-1", BATCH) for index in range(6)]
        with pytest.raises(ScheduleError) as caught:
            register.haul.fit("P-2024-118", bare)
        assert caught.value.code == "HAUL_FIT_TOO_THIN"

    def test_the_refusal_names_both_counts(self, register: Register) -> None:
        with pytest.raises(ScheduleError) as caught:
            register.haul.fit("P-2024-118", [delivery("881204")])
        assert "1 out" in str(caught.value)
        assert "1 on site" in str(caught.value)

    def test_nothing_at_all(self, register: Register) -> None:
        with pytest.raises(ScheduleError):
            register.haul.fit("P-2024-118", [])


def test_a_fitted_profile_can_drive_a_schedule(register: Register) -> None:
    from slumpcone.dispatch.schedule import build_schedule
    from slumpcone.units.quantity import Quantity

    records = [delivery(f"88120{index}") for index in range(4)]
    register.haul.fit("P-2024-118", records)
    found = build_schedule(
        "ORD-1",
        Quantity(90.0, "yd3"),
        Quantity(9.0, "yd3"),
        Quantity(30.0, "yd3"),
        datetime(2024, 6, 12, 7, 0),
        register.haul.get("P-2024-118"),
    )
    assert found.loads[0].batch_at == datetime(2024, 6, 12, 6, 28)
