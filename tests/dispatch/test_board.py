from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.dispatch.board import Board, TruckState, assign, trucks_to_hold
from slumpcone.dispatch.schedule import (
    CycleTime,
    Schedule,
    ScheduleError,
    build_schedule,
)
from slumpcone.units.quantity import Quantity

START = datetime(2024, 6, 12, 7, 0)
FLEET = ("TR-1", "TR-2", "TR-3", "TR-4", "TR-5")


def cycle() -> CycleTime:
    return CycleTime(
        timedelta(minutes=10),
        timedelta(minutes=20),
        timedelta(minutes=15),
        timedelta(minutes=20),
        timedelta(minutes=5),
    )


def schedule(volume: float = 90.0) -> Schedule:
    return build_schedule(
        "ORD-1",
        Quantity(volume, "yd3"),
        Quantity(9.0, "yd3"),
        Quantity(30.0, "yd3"),
        START,
        cycle(),
    )


class CaseAssigning:
    def test_every_load_gets_a_truck(self) -> None:
        board = assign(schedule(), FLEET[:4])
        assert len(board.assignments) == 10
        assert board.unassigned == ()

    def test_four_trucks_hold_this_pour(self) -> None:
        assert assign(schedule(), FLEET[:4]).holds_the_schedule

    def test_three_trucks_do_not(self) -> None:
        board = assign(schedule(), FLEET[:3])
        assert not board.holds_the_schedule
        assert board.late

    def test_the_first_four_loads_go_to_four_different_trucks(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first_four = {one.truck_code for one in board.assignments[:4]}
        assert len(first_four) == 4

    def test_the_fifth_load_comes_back_to_the_first_truck(self) -> None:
        board = assign(schedule(), FLEET[:4])
        assert board.assignments[4].truck_code == board.assignments[0].truck_code

    def test_the_work_is_spread_evenly(self) -> None:
        board = assign(schedule(), FLEET[:4])
        counts = [len(board.loads_for(code)) for code in board.trucks]
        assert max(counts) - min(counts) <= 1

    def test_one_truck_takes_everything_late(self) -> None:
        board = assign(schedule(), ("TR-1",))
        assert board.trucks == ("TR-1",)
        assert len(board.late) == 9

    def test_a_board_with_no_trucks(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            assign(schedule(), ())
        assert caught.value.code == "BOARD_NO_TRUCKS"

    def test_the_same_truck_twice(self) -> None:
        with pytest.raises(ScheduleError) as caught:
            assign(schedule(), ("TR-1", "TR-1"))
        assert caught.value.code == "BOARD_TRUCK_TWICE"

    def test_the_codes_are_normalised(self) -> None:
        board = assign(schedule(), (" tr-1 ",))
        assert board.trucks == ("TR-1",)

    def test_the_same_fleet_assigns_the_same_way_twice(self) -> None:
        first = assign(schedule(), FLEET[:4])
        second = assign(schedule(), FLEET[:4])
        assert [one.truck_code for one in first.assignments] == [
            one.truck_code for one in second.assignments
        ]


class CaseSlipping:
    def test_an_on_time_load_has_no_slip(self) -> None:
        board = assign(schedule(), FLEET[:4])
        assert board.assignments[0].slip == timedelta(0)
        assert not board.assignments[0].is_late

    def test_a_late_load_carries_how_late(self) -> None:
        board = assign(schedule(), FLEET[:2])
        late = board.late[0]
        assert late.slip > timedelta(0)

    def test_the_worst_slip_grows_as_the_day_runs_on(self) -> None:
        board = assign(schedule(), FLEET[:2])
        assert board.worst_slip >= board.late[0].slip

    def test_no_slip_at_all_on_a_full_fleet(self) -> None:
        assert assign(schedule(), FLEET).worst_slip == timedelta(0)

    def test_refusing_to_slip_leaves_loads_unassigned(self) -> None:
        board = assign(schedule(), FLEET[:2], allow_slip=False)
        assert board.unassigned
        assert board.late == ()
        assert not board.holds_the_schedule

    def test_refusing_to_slip_still_takes_what_it_can(self) -> None:
        board = assign(schedule(), FLEET[:2], allow_slip=False)
        assert board.assignments
        assert len(board.assignments) + len(board.unassigned) == 10

    def test_a_full_fleet_leaves_nothing_unassigned_either_way(self) -> None:
        assert assign(schedule(), FLEET, allow_slip=False).unassigned == ()

    def test_describe_on_schedule(self) -> None:
        assert "on schedule" in assign(schedule(), FLEET[:4]).describe()

    def test_describe_when_it_slips(self) -> None:
        text = assign(schedule(), FLEET[:2]).describe()
        assert "late by up to" in text

    def test_an_assignment_describes(self) -> None:
        board = assign(schedule(), FLEET[:4])
        assert "takes load 1" in board.assignments[0].describe()

    def test_a_late_assignment_says_so(self) -> None:
        board = assign(schedule(), FLEET[:2])
        assert "min late" in board.late[0].describe()


class CaseStates:
    def test_a_truck_is_loading_right_after_it_is_batched(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first = board.assignments[0]
        assert first.state_at(first.batch_at, board.schedule) is TruckState.LOADING

    def test_then_it_is_driving_out(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first = board.assignments[0]
        moment = first.batch_at + timedelta(minutes=15)
        assert first.state_at(moment, board.schedule) is TruckState.TO_SITE

    def test_then_it_is_on_site(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first = board.assignments[0]
        moment = first.batch_at + timedelta(minutes=35)
        assert first.state_at(moment, board.schedule) is TruckState.ON_SITE

    def test_then_it_is_coming_back(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first = board.assignments[0]
        moment = first.batch_at + timedelta(minutes=55)
        assert first.state_at(moment, board.schedule) is TruckState.RETURNING

    def test_then_it_is_washing(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first = board.assignments[0]
        moment = first.batch_at + timedelta(minutes=67)
        assert first.state_at(moment, board.schedule) is TruckState.WASHING

    def test_before_and_after_it_is_not_on_this_load(self) -> None:
        board = assign(schedule(), FLEET[:4])
        first = board.assignments[0]
        assert first.state_at(first.batch_at - timedelta(minutes=1), board.schedule) is None
        assert first.state_at(first.free_at, board.schedule) is None

    def test_the_board_gives_a_row_per_truck(self) -> None:
        board = assign(schedule(), FLEET[:4])
        states = board.state_at(START)
        assert set(states) == set(board.trucks)

    def test_a_truck_between_loads_is_at_the_plant(self) -> None:
        board = assign(schedule(), FLEET[:4])
        states = board.state_at(START + timedelta(hours=6))
        assert set(states.values()) == {TruckState.AT_PLANT}

    def test_working_counts_only_the_loaded_legs(self) -> None:
        board = assign(schedule(), FLEET[:4])
        assert board.working_at(START) >= 1
        assert board.working_at(START + timedelta(hours=6)) == 0

    def test_loading_and_hauling_count_as_working(self) -> None:
        assert TruckState.LOADING.is_working
        assert TruckState.ON_SITE.is_working

    def test_washing_and_waiting_do_not(self) -> None:
        assert not TruckState.WASHING.is_working
        assert not TruckState.AT_PLANT.is_working

    def test_the_state_reads_as_words(self) -> None:
        assert str(TruckState.TO_SITE) == "to site"


class CaseHowMany:
    def test_it_finds_the_count_the_arithmetic_predicted(self) -> None:
        assert trucks_to_hold(schedule(), FLEET) == 4

    def test_it_agrees_with_the_schedule(self) -> None:
        found = schedule()
        assert trucks_to_hold(found, FLEET) == found.trucks_needed

    def test_a_short_fleet_gives_back_what_it_has(self) -> None:
        assert trucks_to_hold(schedule(), FLEET[:2]) == 2

    def test_one_load_needs_one_truck(self) -> None:
        assert trucks_to_hold(schedule(volume=4.0), FLEET) == 1


def test_an_empty_board_holds_trivially() -> None:
    empty = Board(schedule(), ())
    assert empty.holds_the_schedule
    assert empty.trucks == ()
    assert empty.worst_slip == timedelta(0)
    assert empty.state_at(START) == {}


def test_loads_for_a_truck_that_carried_nothing() -> None:
    board = assign(schedule(), FLEET[:4])
    assert board.loads_for("TR-9") == ()
