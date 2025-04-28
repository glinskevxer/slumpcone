from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.dispatch.schedule import (
    DISCHARGE_LIMIT,
    CycleTime,
    Schedule,
    ScheduleError,
    build_schedule,
    overlaps,
    spacing_for,
    trucks_for,
)
from slumpcone.units.quantity import Quantity

START = datetime(2024, 6, 12, 7, 0)


def cycle(
    *,
    loading: int = 10,
    haul_out: int = 20,
    on_site: int = 15,
    haul_back: int = 20,
    wash: int = 5,
) -> CycleTime:
    return CycleTime(
        timedelta(minutes=loading),
        timedelta(minutes=haul_out),
        timedelta(minutes=on_site),
        timedelta(minutes=haul_back),
        timedelta(minutes=wash),
    )


def schedule(*, volume: float = 90.0, load: float = 9.0, rate: float = 30.0) -> Schedule:
    return build_schedule(
        "ORD-1",
        Quantity(volume, "yd3"),
        Quantity(load, "yd3"),
        Quantity(rate, "yd3"),
        START,
        cycle(),
    )


class CaseCycle:
    def test_the_legs_add_up(self) -> None:
        assert cycle().total == timedelta(minutes=70)

    def test_the_trip_to_site_is_loading_plus_haul(self) -> None:
        assert cycle().to_site == timedelta(minutes=30)

    def test_the_wash_counts(self) -> None:
        assert cycle(wash=0).total == cycle().total - timedelta(minutes=5)

    def test_a_negative_leg(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            cycle(haul_out=-1)
        assert caught.value.code == "CYCLE_LEG_NEGATIVE"

    def test_a_cycle_of_nothing(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            cycle(loading=0, haul_out=0, on_site=0, haul_back=0, wash=0)
        assert caught.value.code == "CYCLE_EMPTY"

    def test_a_short_haul_stays_inside_the_discharge_limit(self) -> None:
        assert cycle().within_discharge_limit

    def test_a_long_haul_does_not(self) -> None:
        assert not cycle(haul_out=70, on_site=30).within_discharge_limit

    def test_describe(self) -> None:
        assert "70 min round trip" in cycle().describe()
        assert "30 min to site" in cycle().describe()


class CaseSpacing:
    def test_nine_yards_at_thirty_an_hour_is_eighteen_minutes(self) -> None:
        found = spacing_for(Quantity(9.0, "yd3"), Quantity(30.0, "yd3"), timedelta(hours=1))
        assert found == timedelta(minutes=18)

    def test_a_faster_crew_wants_them_closer(self) -> None:
        slow = spacing_for(Quantity(9.0, "yd3"), Quantity(30.0, "yd3"), timedelta(hours=1))
        fast = spacing_for(Quantity(9.0, "yd3"), Quantity(60.0, "yd3"), timedelta(hours=1))
        assert fast < slow

    def test_a_bigger_load_spreads_them_out(self) -> None:
        small = spacing_for(Quantity(9.0, "yd3"), Quantity(30.0, "yd3"), timedelta(hours=1))
        big = spacing_for(Quantity(10.0, "yd3"), Quantity(30.0, "yd3"), timedelta(hours=1))
        assert big > small

    def test_a_zero_load_size(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            spacing_for(Quantity(0.0, "yd3"), Quantity(30.0, "yd3"), timedelta(hours=1))
        assert caught.value.code == "SCHEDULE_NO_LOAD_SIZE"

    def test_a_zero_pour_rate(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            spacing_for(Quantity(9.0, "yd3"), Quantity(0.0, "yd3"), timedelta(hours=1))
        assert caught.value.code == "SCHEDULE_NO_POUR_RATE"


class CaseTruckCount:
    def test_a_seventy_minute_cycle_on_eighteen_minute_spacing(self) -> None:
        assert trucks_for(cycle(), timedelta(minutes=18)) == 4

    def test_it_rounds_up_rather_than_down(self) -> None:
        # 70 over 20 is three and a half, and half a truck delivers nothing.
        assert trucks_for(cycle(), timedelta(minutes=20)) == 4

    def test_an_exact_division_does_not_round_up(self) -> None:
        assert trucks_for(cycle(), timedelta(minutes=35)) == 2

    def test_a_slow_pour_still_needs_one_truck(self) -> None:
        assert trucks_for(cycle(), timedelta(hours=8)) == 1

    def test_leaving_the_wash_out_can_cost_a_truck(self) -> None:
        with_wash = trucks_for(cycle(), timedelta(minutes=18))
        without = trucks_for(cycle(wash=0), timedelta(minutes=18))
        assert with_wash >= without

    def test_a_zero_spacing(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            trucks_for(cycle(), timedelta(0))
        assert caught.value.code == "SCHEDULE_NO_SPACING"


class CaseBuilding:
    def test_ninety_yards_in_nine_yard_loads(self) -> None:
        found = schedule()
        assert len(found.loads) == 10
        assert found.total_volume == Quantity(90.0, "yd3")

    def test_the_first_load_arrives_when_asked(self) -> None:
        assert schedule().loads[0].arrive_at == START

    def test_the_first_batch_is_set_back_by_the_trip_out(self) -> None:
        assert schedule().loads[0].batch_at == START - timedelta(minutes=30)

    def test_the_loads_are_spaced(self) -> None:
        loads = schedule().loads
        assert loads[1].arrive_at - loads[0].arrive_at == timedelta(minutes=18)

    def test_the_truck_count_comes_out(self) -> None:
        assert schedule().trucks_needed == 4

    def test_nothing_is_short_when_it_divides(self) -> None:
        assert schedule().short_load is None
        assert not any(load.is_short for load in schedule().loads)

    def test_the_last_load_is_short_when_it_does_not_divide(self) -> None:
        found = schedule(volume=85.0)
        assert len(found.loads) == 10
        short = found.short_load
        assert short is not None
        assert short.sequence == 10
        assert short.volume.value == pytest.approx(4.0)

    def test_the_short_load_still_adds_up(self) -> None:
        assert schedule(volume=85.0).total_volume.value == pytest.approx(85.0)

    def test_a_pour_smaller_than_one_load(self) -> None:
        found = schedule(volume=4.0)
        assert len(found.loads) == 1
        assert not found.loads[0].is_short

    def test_a_zero_volume(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            schedule(volume=0.0)
        assert caught.value.code == "SCHEDULE_NO_VOLUME"

    def test_the_discharge_deadline_runs_from_batching(self) -> None:
        load = schedule().loads[0]
        assert load.discharge_deadline == load.batch_at + DISCHARGE_LIMIT

    def test_a_load_describes(self) -> None:
        assert "load 1" in schedule().loads[0].describe()

    def test_a_short_load_says_so(self) -> None:
        short = schedule(volume=85.0).short_load
        assert short is not None
        assert "(short)" in short.describe()


class CaseSchedule:
    def test_the_first_and_last_moments(self) -> None:
        found = schedule()
        assert found.first_batch == START - timedelta(minutes=30)
        assert found.last_arrival == START + timedelta(minutes=18 * 9)

    def test_the_duration_is_arrival_to_arrival(self) -> None:
        assert schedule().duration == timedelta(minutes=18 * 9)

    def test_one_load_has_no_duration(self) -> None:
        assert schedule(volume=4.0).duration == timedelta(0)

    def test_what_is_left_at_a_moment(self) -> None:
        found = schedule()
        left = found.at_or_after(START + timedelta(hours=1))
        assert len(left) < len(found.loads)
        assert all(load.batch_at >= START + timedelta(hours=1) for load in left)

    def test_everything_is_left_before_it_starts(self) -> None:
        found = schedule()
        assert len(found.at_or_after(START - timedelta(hours=4))) == len(found.loads)

    def test_nothing_is_left_after_it_ends(self) -> None:
        found = schedule()
        assert found.at_or_after(START + timedelta(days=1)) == ()

    def test_describe(self) -> None:
        text = schedule().describe()
        assert "10 load(s)" in text
        assert "every 18 min" in text
        assert "4 truck(s)" in text

    def test_an_empty_schedule_totals_nothing(self) -> None:
        empty = Schedule("ORD-1", (), timedelta(minutes=18), cycle(), 1)
        assert empty.total_volume.is_zero()
        assert empty.first_batch is None
        assert empty.last_arrival is None
        assert empty.short_load is None


class CaseOverlaps:
    def test_nothing_to_compare(self) -> None:
        assert overlaps([]) == ()

    def test_one_pour_overlaps_nothing(self) -> None:
        assert overlaps([schedule()]) == ()

    def test_two_pours_at_the_same_time_collide(self) -> None:
        first = schedule()
        second = build_schedule(
            "ORD-2",
            Quantity(90.0, "yd3"),
            Quantity(9.0, "yd3"),
            Quantity(30.0, "yd3"),
            START + timedelta(minutes=30),
            cycle(),
        )
        assert overlaps([first, second]) == (("ORD-1", "ORD-2"),)

    def test_two_pours_a_day_apart_do_not(self) -> None:
        first = schedule()
        second = build_schedule(
            "ORD-2",
            Quantity(90.0, "yd3"),
            Quantity(9.0, "yd3"),
            Quantity(30.0, "yd3"),
            START + timedelta(days=1),
            cycle(),
        )
        assert overlaps([first, second]) == ()

    def test_three_pours_report_every_pair(self) -> None:
        found = [
            build_schedule(
                f"ORD-{index}",
                Quantity(90.0, "yd3"),
                Quantity(9.0, "yd3"),
                Quantity(30.0, "yd3"),
                START + timedelta(minutes=10 * index),
                cycle(),
            )
            for index in range(3)
        ]
        assert len(overlaps(found)) == 3

    def test_an_empty_schedule_is_skipped(self) -> None:
        empty = Schedule("ORD-9", (), timedelta(minutes=18), cycle(), 1)
        assert overlaps([schedule(), empty]) == ()
