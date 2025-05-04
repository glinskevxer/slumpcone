from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.delivery.record import Delivery
from slumpcone.demo import DEMO_DAY, seed
from slumpcone.register import Register
from slumpcone.report.utilisation import FleetDay, TruckDay, utilisation
from slumpcone.units.quantity import Quantity
from tests.report.test_fleet import ticket

BATCH = datetime(2024, 6, 12, 6, 30)


def delivery(
    number: str,
    truck: str = "TR-1",
    *,
    out: int = 20,
    wait: int = 10,
    discharge: int = 15,
    complete: bool = True,
    batched: datetime = BATCH,
) -> Delivery:
    if not complete:
        return Delivery(number, truck, batched)
    left = batched + timedelta(minutes=10)
    arrived = left + timedelta(minutes=out)
    started = arrived + timedelta(minutes=wait)
    return Delivery(
        number,
        truck,
        batched,
        left_plant_at=left,
        arrived_at=arrived,
        discharge_started_at=started,
        discharge_finished_at=started + timedelta(minutes=discharge),
    )


class CaseOneTruck:
    def test_it_counts_the_loads(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204")])
        assert day.loads == 1
        assert day.trucks[0].truck_code == "TR-1"

    def test_the_volume_comes_off_the_ticket(self) -> None:
        day = utilisation([ticket("881204", 8.5)], [delivery("881204")])
        assert day.volume == Quantity(8.5, "yd3")

    def test_the_driving_counts_the_run_home(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204", out=20)])
        assert day.trucks[0].driving == timedelta(minutes=40)

    def test_the_waiting_is_the_gap_before_the_chute(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204", wait=25)])
        assert day.trucks[0].waiting == timedelta(minutes=25)

    def test_the_working_time_is_the_three_legs(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204")])
        assert day.trucks[0].working == timedelta(minutes=40 + 10 + 15)

    def test_the_rate(self) -> None:
        day = utilisation([ticket("881204", 9.0)], [delivery("881204")])
        # 9 yards over 65 minutes.
        assert day.trucks[0].yards_per_hour == pytest.approx(9.0 / (65 / 60))

    def test_the_waiting_share(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204")])
        assert day.trucks[0].waiting_share.value == pytest.approx(100.0 * 10 / 65)

    def test_the_average_load(self) -> None:
        day = utilisation(
            [ticket("881204", 9.0), ticket("881205", 7.0)],
            [delivery("881204"), delivery("881205")],
        )
        assert day.trucks[0].average_load.value == pytest.approx(8.0)


class CaseMissingMoments:
    def test_a_bare_record_carries_a_load_and_no_time(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204", complete=False)])
        assert day.loads == 1
        assert day.working == timedelta(0)

    def test_a_bare_record_does_not_drag_the_rate_down(self) -> None:
        good = utilisation([ticket("881204")], [delivery("881204")])
        with_bare = utilisation(
            [ticket("881204"), ticket("881205")],
            [delivery("881204"), delivery("881205", complete=False)],
        )
        assert with_bare.working == good.working

    def test_the_complete_count_is_kept(self) -> None:
        day = utilisation(
            [ticket("881204"), ticket("881205")],
            [delivery("881204"), delivery("881205", complete=False)],
        )
        assert day.trucks[0].complete_records == 1

    def test_too_few_complete_records_reads_as_thin(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204")])
        assert day.trucks[0].is_thin
        assert "(thin)" in day.trucks[0].describe()

    def test_three_complete_records_are_not_thin(self) -> None:
        numbers = ["881204", "881205", "881206"]
        day = utilisation(
            [ticket(number) for number in numbers],
            [delivery(number) for number in numbers],
        )
        assert not day.trucks[0].is_thin

    def test_a_delivery_with_no_ticket_carries_time_and_no_volume(self) -> None:
        day = utilisation([], [delivery("881204")])
        assert day.loads == 1
        assert day.volume.is_zero()
        assert day.working > timedelta(0)


class CaseFleet:
    def test_two_trucks(self) -> None:
        day = utilisation(
            [ticket("881204"), ticket("881205")],
            [delivery("881204", "TR-1"), delivery("881205", "TR-2")],
        )
        assert len(day.trucks) == 2
        assert day.loads == 2

    def test_the_fleet_rate_divides_the_totals(self) -> None:
        day = utilisation(
            [ticket("881204", 9.0), ticket("881205", 1.0)],
            [
                delivery("881204", "TR-1"),
                delivery("881205", "TR-2", out=1, wait=1, discharge=1),
            ],
        )
        hours = day.working.total_seconds() / 3600
        assert day.yards_per_hour == pytest.approx(10.0 / hours)

    def test_a_quick_single_load_does_not_dominate_the_fleet_rate(self) -> None:
        day = utilisation(
            [ticket("881204", 9.0), ticket("881205", 1.0)],
            [
                delivery("881204", "TR-1"),
                delivery("881205", "TR-2", out=1, wait=1, discharge=1),
            ],
        )
        rates = [one.yards_per_hour for one in day.trucks]
        assert day.yards_per_hour < max(rates)

    def test_the_busiest_truck(self) -> None:
        day = utilisation(
            [ticket("881204", 9.0), ticket("881205", 3.0)],
            [delivery("881204", "TR-1"), delivery("881205", "TR-2")],
        )
        busiest = day.busiest()
        assert busiest is not None
        assert busiest.truck_code == "TR-1"

    def test_the_worst_waiter(self) -> None:
        day = utilisation(
            [ticket("881204"), ticket("881205")],
            [
                delivery("881204", "TR-1", wait=5),
                delivery("881205", "TR-2", wait=60),
            ],
        )
        worst = day.worst_waiter()
        assert worst is not None
        assert worst.truck_code == "TR-2"

    def test_ranked_is_most_delivered_first(self) -> None:
        day = utilisation(
            [ticket("881204", 3.0), ticket("881205", 9.0)],
            [delivery("881204", "TR-1"), delivery("881205", "TR-2")],
        )
        assert day.ranked()[0].truck_code == "TR-2"

    def test_describe(self) -> None:
        day = utilisation([ticket("881204")], [delivery("881204")])
        text = day.describe()
        assert "1 truck(s)" in text
        assert "waiting" in text


class CaseEmpty:
    def test_nothing_at_all(self) -> None:
        day = utilisation([], [])
        assert day.loads == 0
        assert day.volume.is_zero()
        assert day.yards_per_hour == pytest.approx(0.0)
        assert day.waiting_share.value == pytest.approx(0.0)
        assert day.busiest() is None
        assert day.worst_waiter() is None
        assert day.ranked() == ()

    def test_a_truck_that_went_nowhere(self) -> None:
        idle = TruckDay(
            "TR-1", 0, Quantity(0.0, "yd3"), timedelta(0), timedelta(0), timedelta(0), 0
        )
        assert idle.yards_per_hour == pytest.approx(0.0)
        assert idle.waiting_share.value == pytest.approx(0.0)
        assert idle.average_load.is_zero()

    def test_an_empty_fleet_describes(self) -> None:
        assert "0 truck(s)" in FleetDay(()).describe()


def test_the_seeded_day() -> None:
    register = Register.in_memory()
    seed(register)
    day = utilisation(
        list(register.batches.between(DEMO_DAY, DEMO_DAY)),
        list(register.deliveries.between(DEMO_DAY, DEMO_DAY)),
    )
    assert day.loads > 0
    assert day.volume.value > 0.0
