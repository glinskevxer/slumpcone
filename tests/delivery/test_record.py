from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.delivery.haul import haul_limits
from slumpcone.delivery.record import Delivery
from slumpcone.delivery.water import WaterAddition
from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity

BATCHED = datetime(2024, 6, 12, 7, 42)


def at(minutes: int) -> datetime:
    return BATCHED + timedelta(minutes=minutes)


def delivery(**overrides: object) -> Delivery:
    fields: dict[str, object] = {
        "ticket_number": "881204",
        "truck_code": "TR-114",
        "batched_at": BATCHED,
        "left_plant_at": at(6),
        "arrived_at": at(28),
        "discharge_started_at": at(35),
        "discharge_finished_at": at(52),
        "revolutions_on_arrival": 140,
        "revolutions_at_discharge": 210,
    }
    fields.update(overrides)
    return Delivery(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_identifiers_are_normalised(self) -> None:
        built = delivery(ticket_number=" 881204 ", truck_code="tr 114")
        assert built.ticket_number == "881204"
        assert built.truck_code == "TR-114"

    def test_a_stage_out_of_order_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="arrived_at is before left_plant_at"):
            delivery(arrived_at=at(2))

    def test_a_gap_in_the_middle_does_not_break_the_ordering(self) -> None:
        built = delivery(arrived_at=None)
        assert built.is_complete

    def test_discharge_finishing_before_it_starts_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="discharge_finished_at is before"):
            delivery(discharge_finished_at=at(30))

    def test_a_negative_revolution_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            delivery(revolutions_on_arrival=-1)

    def test_returned_concrete_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="returned concrete is a volume"):
            delivery(returned_volume=Quantity(1, "lb"))
        with pytest.raises(ValidationError, match="cannot be negative"):
            delivery(returned_volume=Quantity(-1, "yd3"))

    def test_a_water_addition_for_another_ticket_is_refused(self) -> None:
        other = WaterAddition("881205", at(30), Quantity(5, "gal"))
        with pytest.raises(ValidationError, match="881205"):
            delivery(water_additions=(other,))


class CaseTimings:
    def test_the_spans(self) -> None:
        built = delivery()
        assert built.haul_time == timedelta(minutes=22)
        assert built.wait_time == timedelta(minutes=7)
        assert built.discharge_time == timedelta(minutes=17)
        assert built.total_time == timedelta(minutes=52)

    def test_a_missing_stage_leaves_its_span_unknown(self) -> None:
        built = delivery(arrived_at=None, discharge_started_at=None)
        assert built.haul_time is None
        assert built.wait_time is None
        assert built.discharge_time is None

    def test_an_unfinished_load(self) -> None:
        built = delivery(discharge_finished_at=None)
        assert not built.is_complete
        assert built.total_time is None
        assert "in progress" in built.describe()


class CaseWater:
    def test_no_additions(self) -> None:
        assert delivery().water_added.is_zero()
        assert not delivery().has_multiple_additions

    def test_one_addition(self) -> None:
        addition = WaterAddition("881204", at(30), Quantity(5, "gal"))
        built = delivery(water_additions=(addition,))
        assert built.water_added.value == pytest.approx(5.0)
        assert not built.has_multiple_additions
        assert "5.0 gal added" in built.describe()

    def test_two_additions_are_flagged(self) -> None:
        built = delivery(
            water_additions=(
                WaterAddition("881204", at(30), Quantity(5, "gal")),
                WaterAddition("881204", at(38), Quantity(3, "gal")),
            )
        )
        assert built.has_multiple_additions
        assert built.water_added.value == pytest.approx(8.0)

    def test_additions_in_other_units_add_up(self) -> None:
        built = delivery(water_additions=(WaterAddition("881204", at(30), Quantity(20, "L")),))
        assert built.water_added.value == pytest.approx(5.28, abs=0.01)


class CaseHaulVerdict:
    def test_a_finished_load_is_judged(self) -> None:
        verdict = delivery().haul_verdict()
        assert verdict is not None
        assert verdict.conforms

    def test_an_unfinished_load_is_not(self) -> None:
        assert delivery(discharge_finished_at=None).haul_verdict() is None

    def test_a_load_with_no_counter_reading_is_not(self) -> None:
        assert delivery(revolutions_at_discharge=None).haul_verdict() is None

    def test_a_slow_load_fails(self) -> None:
        verdict = delivery(discharge_finished_at=at(100)).haul_verdict()
        assert verdict is not None
        assert verdict.over_time

    def test_the_limits_can_be_supplied(self) -> None:
        verdict = delivery(discharge_finished_at=at(100)).haul_verdict(
            haul_limits(has_retarder=True)
        )
        assert verdict is not None
        assert verdict.conforms

    def test_describe(self) -> None:
        assert delivery().describe() == "881204  TR-114  52 min"
