"""Putting trucks against loads, and what the dispatcher watches while it runs.

The schedule says when each load should be batched. The board says who is taking
it, and whether that is possible with the trucks actually on the yard.

Assignment is greedy on purpose. A dispatcher assigns the truck that has been
back longest, because that is fair to the drivers and because anything cleverer
falls apart the first time a truck breaks down. So the rule here is: take the
truck free earliest, break ties by whoever has done fewest loads today, and
break the remaining tie by code so two runs of the same day come out the same.

What matters more than the assignment is what happens when there are not enough
trucks. The honest answer is that the load slips, and the pour with it. A board
that silently assigned a truck that has not come back yet would show a schedule
that cannot happen, which is worse than showing one that is late. So a slipped
load carries how late it is, and the board totals that up.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from slumpcone.dispatch.schedule import Schedule, ScheduledLoad, ScheduleError
from slumpcone.identity import normalize_code


class TruckState(Enum):
    """Where a truck is in its cycle."""

    AT_PLANT = "at plant"
    LOADING = "loading"
    TO_SITE = "to site"
    ON_SITE = "on site"
    RETURNING = "returning"
    WASHING = "washing"

    def __str__(self) -> str:
        return self.value

    @property
    def is_working(self) -> bool:
        """Whether the truck is carrying or discharging concrete."""
        return self in {TruckState.LOADING, TruckState.TO_SITE, TruckState.ON_SITE}


@dataclass(frozen=True, slots=True)
class Assignment:
    """One load, given to one truck."""

    truck_code: str
    load: ScheduledLoad
    batch_at: datetime
    free_at: datetime

    @property
    def slip(self) -> timedelta:
        """How much later than scheduled this load actually goes."""
        return self.batch_at - self.load.batch_at

    @property
    def is_late(self) -> bool:
        """Whether the load slipped at all."""
        return self.slip > timedelta(0)

    def state_at(self, moment: datetime, schedule: Schedule) -> TruckState | None:
        """What the truck is doing at a moment, or nothing if this load is not running."""
        cycle = schedule.cycle
        marks = (
            (self.batch_at + cycle.loading, TruckState.LOADING),
            (self.batch_at + cycle.to_site, TruckState.TO_SITE),
            (self.batch_at + cycle.to_site + cycle.on_site, TruckState.ON_SITE),
            (
                self.batch_at + cycle.to_site + cycle.on_site + cycle.haul_back,
                TruckState.RETURNING,
            ),
            (self.free_at, TruckState.WASHING),
        )
        if moment < self.batch_at or moment >= self.free_at:
            return None
        for ends_at, state in marks:
            if moment < ends_at:
                return state
        return TruckState.WASHING

    def describe(self) -> str:
        """One line."""
        tail = f", {self.slip.total_seconds() / 60:.0f} min late" if self.is_late else ""
        return f"{self.truck_code} takes load {self.load.sequence}{tail}"


@dataclass(frozen=True, slots=True)
class Board:
    """A whole pour, with the trucks against it."""

    schedule: Schedule
    assignments: tuple[Assignment, ...]
    unassigned: tuple[ScheduledLoad, ...] = ()

    @property
    def trucks(self) -> tuple[str, ...]:
        """Every truck on the board, in the order it first appears."""
        seen: list[str] = []
        for one in self.assignments:
            if one.truck_code not in seen:
                seen.append(one.truck_code)
        return tuple(seen)

    @property
    def late(self) -> tuple[Assignment, ...]:
        """The loads that slipped."""
        return tuple(one for one in self.assignments if one.is_late)

    @property
    def worst_slip(self) -> timedelta:
        """The largest slip on the board."""
        return max((one.slip for one in self.assignments), default=timedelta(0))

    @property
    def holds_the_schedule(self) -> bool:
        """Whether every load goes when it was meant to and none was dropped."""
        return not self.late and not self.unassigned

    def loads_for(self, truck_code: str) -> tuple[Assignment, ...]:
        """What one truck is carrying, in order."""
        key = normalize_code(truck_code, field="truck_code")
        return tuple(one for one in self.assignments if one.truck_code == key)

    def state_at(self, moment: datetime) -> dict[str, TruckState]:
        """What every truck is doing at a moment.

        A truck between loads is at the plant rather than missing, because a
        dispatcher scanning the board wants a row per truck either way.
        """
        states: dict[str, TruckState] = dict.fromkeys(self.trucks, TruckState.AT_PLANT)
        for one in self.assignments:
            state = one.state_at(moment, self.schedule)
            if state is not None:
                states[one.truck_code] = state
        return states

    def working_at(self, moment: datetime) -> int:
        """How many trucks are carrying concrete at a moment."""
        return sum(1 for state in self.state_at(moment).values() if state.is_working)

    def describe(self) -> str:
        """One line."""
        if self.holds_the_schedule:
            return (
                f"{self.schedule.order_number}: {len(self.assignments)} load(s) on "
                f"{len(self.trucks)} truck(s), on schedule"
            )
        return (
            f"{self.schedule.order_number}: {len(self.late)} load(s) late by up to "
            f"{self.worst_slip.total_seconds() / 60:.0f} min, "
            f"{len(self.unassigned)} unassigned"
        )


def assign(schedule: Schedule, truck_codes: Sequence[str], *, allow_slip: bool = True) -> Board:
    """Put the available trucks against a schedule.

    With ``allow_slip`` off, a load that cannot be taken on time is left
    unassigned rather than pushed back. That is the right answer when the
    question is whether the yard can hold the pour, and the wrong one when the
    question is what actually happens, which is why it is a choice.
    """
    codes = [normalize_code(code, field="truck_code") for code in truck_codes]
    if not codes:
        raise ScheduleError("BOARD_NO_TRUCKS", "a board needs at least one truck")
    if len(set(codes)) != len(codes):
        raise ScheduleError("BOARD_TRUCK_TWICE", "a truck cannot be on the board twice")

    cycle = schedule.cycle.total
    free_at: dict[str, datetime] = {}
    carried: dict[str, int] = dict.fromkeys(codes, 0)
    assignments: list[Assignment] = []
    unassigned: list[ScheduledLoad] = []

    for load in schedule.loads:
        ready = sorted(
            codes,
            key=lambda code: (
                free_at.get(code, load.batch_at),
                carried[code],
                code,
            ),
        )
        chosen = ready[0]
        available = free_at.get(chosen, load.batch_at)
        if available > load.batch_at and not allow_slip:
            unassigned.append(load)
            continue
        batch_at = max(available, load.batch_at)
        assignments.append(Assignment(chosen, load, batch_at, batch_at + cycle))
        free_at[chosen] = batch_at + cycle
        carried[chosen] += 1

    return Board(schedule, tuple(assignments), tuple(unassigned))


def trucks_to_hold(schedule: Schedule, available: Sequence[str]) -> int:
    """How many of the available trucks are actually needed to run on time.

    The schedule already says how many the arithmetic calls for. This runs the
    assignment with more and more of them until nothing slips, which catches the
    cases where the rounding in the arithmetic was optimistic.
    """
    codes = [normalize_code(code, field="truck_code") for code in available]
    for count in range(1, len(codes) + 1):
        if assign(schedule, codes[:count]).holds_the_schedule:
            return count
    return len(codes)
