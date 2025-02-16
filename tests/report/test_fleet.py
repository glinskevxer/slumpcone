from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.errors import ValidationError
from slumpcone.report.fleet import (
    TruckSummary,
    cycle_parts,
    render_fleet,
    render_fleet_report,
    render_stages,
    summarise_fleet,
    turn_times,
)
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

DAY = date(2024, 6, 12)
START = datetime(2024, 6, 12, 7, 42)


def delivery(
    ticket: str, truck: str = "TR-114", offset: int = 0, **overrides: object
) -> Delivery:
    batched = START + timedelta(minutes=offset)
    fields: dict[str, object] = {
        "ticket_number": ticket,
        "truck_code": truck,
        "batched_at": batched,
        "left_plant_at": batched + timedelta(minutes=6),
        "arrived_at": batched + timedelta(minutes=28),
        "discharge_started_at": batched + timedelta(minutes=35),
        "discharge_finished_at": batched + timedelta(minutes=52),
        "revolutions_at_discharge": 210,
    }
    fields.update(overrides)
    return Delivery(**fields)  # type: ignore[arg-type]


def ticket(number: str, volume: float = 9.0) -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(volume, "yd3"), DAY)
    return BatchTicket.from_plan(planned, number, START)


class CaseCycleParts:
    def test_every_stage(self) -> None:
        parts = cycle_parts(delivery("881204"))
        assert parts.loading == pytest.approx(6.0)
        assert parts.haul_out == pytest.approx(22.0)
        assert parts.waiting == pytest.approx(7.0)
        assert parts.discharging == pytest.approx(17.0)
        assert parts.total == pytest.approx(52.0)
        assert parts.is_complete

    def test_a_missing_stage(self) -> None:
        parts = cycle_parts(delivery("881204", arrived_at=None))
        assert parts.haul_out is None
        assert not parts.is_complete
        assert parts.total is not None

    def test_a_delivery_with_nothing_but_a_batch_time(self) -> None:
        parts = cycle_parts(
            delivery(
                "881204",
                left_plant_at=None,
                arrived_at=None,
                discharge_started_at=None,
                discharge_finished_at=None,
                revolutions_at_discharge=None,
            )
        )
        assert parts.total is None

    def test_describe(self) -> None:
        text = cycle_parts(delivery("881204")).describe()
        assert "881204" in text
        assert "wait 7" in text


class CaseTurnTimes:
    def test_gaps_between_consecutive_loads(self) -> None:
        turns = turn_times([delivery("881204"), delivery("881205", offset=95)])
        assert turns["TR-114"] == pytest.approx((95.0,))

    def test_one_load_has_no_turn(self) -> None:
        assert turn_times([delivery("881204")])["TR-114"] == ()

    def test_two_trucks_are_kept_apart(self) -> None:
        turns = turn_times(
            [
                delivery("881204", "TR-114"),
                delivery("881205", "TR-102", offset=10),
                delivery("881206", "TR-114", offset=95),
            ]
        )
        assert len(turns["TR-114"]) == 1
        assert turns["TR-102"] == ()

    def test_it_orders_by_batch_time(self) -> None:
        turns = turn_times([delivery("881205", offset=95), delivery("881204")])
        assert turns["TR-114"] == pytest.approx((95.0,))


class CaseSummary:
    def test_loads_and_volume(self) -> None:
        summaries = summarise_fleet(
            [delivery("881204"), delivery("881205", offset=95)],
            [ticket("881204"), ticket("881205", 7.0)],
        )
        assert summaries[0].loads == 2
        assert summaries[0].volume == Quantity(16, "yd3")
        assert summaries[0].volume_per_load == Quantity(8, "yd3")

    def test_a_delivery_with_no_ticket_carries_nothing(self) -> None:
        summaries = summarise_fleet([delivery("881299")], [])
        assert summaries[0].volume.is_zero()

    def test_the_average_turn(self) -> None:
        summaries = summarise_fleet([delivery("881204"), delivery("881205", offset=95)], [])
        assert summaries[0].average_turn == pytest.approx(95.0)

    def test_one_load_has_no_average_turn(self) -> None:
        assert summarise_fleet([delivery("881204")], [])[0].average_turn is None

    def test_a_truck_that_did_nothing_has_no_volume_per_load(self) -> None:
        summary = TruckSummary("TR-9", 0, Quantity(0, "yd3"), ())
        assert summary.volume_per_load.is_zero()

    def test_utilisation(self) -> None:
        summary = TruckSummary("TR-114", 4, Quantity(36, "yd3"), (90.0, 90.0, 90.0))
        assert summary.utilisation(600.0, 90.0).value == pytest.approx(60.0)

    def test_a_shift_of_nothing(self) -> None:
        summary = TruckSummary("TR-114", 4, Quantity(36, "yd3"), ())
        with pytest.raises(ValidationError, match="shift has to have a length"):
            summary.utilisation(0.0, 90.0)

    def test_a_cycle_of_nothing(self) -> None:
        summary = TruckSummary("TR-114", 4, Quantity(36, "yd3"), ())
        with pytest.raises(ValidationError, match="cycle has to have a length"):
            summary.utilisation(600.0, 0.0)


class CaseRendering:
    def deliveries(self) -> list[Delivery]:
        return [
            delivery("881204", "TR-114"),
            delivery("881205", "TR-102", offset=10),
            delivery("881206", "TR-114", offset=95),
        ]

    def test_the_fleet_table(self) -> None:
        text = render_fleet(summarise_fleet(self.deliveries(), []))
        assert "truck" in text.splitlines()[0]
        assert "TR-114" in text
        assert "avg turn" in text.splitlines()[0]

    def test_the_stage_table(self) -> None:
        text = render_stages(self.deliveries())
        assert "wait" in text.splitlines()[0]
        assert "881204" in text

    def test_a_missing_stage_prints_a_dash(self) -> None:
        text = render_stages([delivery("881204", arrived_at=None)])
        assert "-" in text

    def test_the_whole_report(self) -> None:
        text = render_fleet_report(self.deliveries(), [ticket("881204")])
        assert "Fleet" in text
        assert "average wait" in text
        assert "Where the time went" in text

    def test_a_report_with_no_waits(self) -> None:
        bare = [
            delivery(
                "881204",
                arrived_at=None,
                discharge_started_at=None,
                discharge_finished_at=None,
                revolutions_at_discharge=None,
            )
        ]
        assert "average wait" in render_fleet_report(bare, [])
