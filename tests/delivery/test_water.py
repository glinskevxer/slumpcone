from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.delivery.water import (
    MIXING_REVOLUTIONS_AFTER_WATER,
    RequestedBy,
    WaterAddition,
    judge_addition,
)
from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity

ADDED = datetime(2024, 6, 12, 8, 20)
BATCH_WATER = Quantity(2250, "lb")
CEMENTITIOUS = Quantity(5076, "lb")
DESIGN_RATIO = 0.4433


def addition(**overrides: object) -> WaterAddition:
    fields: dict[str, object] = {
        "ticket_number": "881204",
        "added_at": ADDED,
        "amount": Quantity(5, "gal"),
    }
    fields.update(overrides)
    return WaterAddition(**fields)  # type: ignore[arg-type]


class CaseRequestedBy:
    def test_parse(self) -> None:
        assert RequestedBy.parse("producer") is RequestedBy.PRODUCER
        assert RequestedBy.parse("Contractor") is RequestedBy.PURCHASER
        assert RequestedBy.parse("driver") is RequestedBy.PRODUCER

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="unknown requester"):
            RequestedBy.parse("the weather")

    def test_prints_its_own_value(self) -> None:
        assert str(RequestedBy.PURCHASER) == "purchaser"


class CaseAddition:
    def test_the_ticket_number_is_normalised(self) -> None:
        assert addition(ticket_number=" 881204 ").ticket_number == "881204"

    def test_the_amount_has_to_be_a_volume(self) -> None:
        with pytest.raises(ValidationError, match="added water is a volume"):
            addition(amount=Quantity(5, "lb"))

    def test_a_negative_amount_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            addition(amount=Quantity(-1, "gal"))

    def test_a_negative_revolution_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            addition(revolutions_after=-1)

    def test_the_discharge_before_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a volume"):
            addition(discharged_before=Quantity(1, "lb"))
        with pytest.raises(ValidationError, match="cannot be negative"):
            addition(discharged_before=Quantity(-1, "yd3"))

    def test_the_mass_of_the_water(self) -> None:
        assert addition().mass.to("lb").value == pytest.approx(41.7, abs=0.1)

    def test_mixed_in(self) -> None:
        assert addition().was_mixed_in
        assert not addition(revolutions_after=10).was_mixed_in
        assert MIXING_REVOLUTIONS_AFTER_WATER == 30

    def test_after_discharge_started(self) -> None:
        assert not addition().after_discharge_started
        assert not addition(discharged_before=Quantity(0, "yd3")).after_discharge_started
        assert addition(discharged_before=Quantity(2, "yd3")).after_discharge_started


class CaseJudge:
    def test_a_small_addition_inside_the_design(self) -> None:
        verdict = judge_addition(
            addition(amount=Quantity(1, "gal")), BATCH_WATER, CEMENTITIOUS, 0.46
        )
        assert verdict.conforms
        assert not verdict.exceeds_design
        assert not verdict.warranty_void

    def test_the_resulting_ratio(self) -> None:
        verdict = judge_addition(addition(), BATCH_WATER, CEMENTITIOUS, DESIGN_RATIO)
        assert verdict.resulting_ratio == pytest.approx(0.4515, abs=1e-3)

    def test_an_addition_past_the_design(self) -> None:
        verdict = judge_addition(addition(), BATCH_WATER, CEMENTITIOUS, DESIGN_RATIO)
        assert verdict.exceeds_design
        assert not verdict.conforms
        assert "past the design" in verdict.describe()

    def test_the_purchaser_voids_the_warranty(self) -> None:
        verdict = judge_addition(addition(), BATCH_WATER, CEMENTITIOUS, DESIGN_RATIO)
        assert verdict.warranty_void
        assert "warranty void" in verdict.describe()

    def test_the_producer_does_not(self) -> None:
        verdict = judge_addition(
            addition(requested_by=RequestedBy.PRODUCER), BATCH_WATER, CEMENTITIOUS, DESIGN_RATIO
        )
        assert verdict.exceeds_design
        assert not verdict.warranty_void

    def test_a_specified_limit_is_reported_instead(self) -> None:
        verdict = judge_addition(
            addition(amount=Quantity(20, "gal")), BATCH_WATER, CEMENTITIOUS, DESIGN_RATIO, 0.45
        )
        assert verdict.exceeds_specification
        assert "past the specified" in verdict.reasons[0]

    def test_too_few_revolutions(self) -> None:
        verdict = judge_addition(
            addition(amount=Quantity(1, "gal"), revolutions_after=10),
            BATCH_WATER,
            CEMENTITIOUS,
            0.46,
        )
        assert any("revolutions" in reason for reason in verdict.reasons)

    def test_added_after_discharge_started(self) -> None:
        verdict = judge_addition(
            addition(amount=Quantity(1, "gal"), discharged_before=Quantity(2, "yd3")),
            BATCH_WATER,
            CEMENTITIOUS,
            0.46,
        )
        assert any("discharge had already started" in reason for reason in verdict.reasons)

    def test_several_faults_at_once(self) -> None:
        verdict = judge_addition(
            addition(
                amount=Quantity(20, "gal"),
                revolutions_after=5,
                discharged_before=Quantity(2, "yd3"),
            ),
            BATCH_WATER,
            CEMENTITIOUS,
            DESIGN_RATIO,
        )
        assert len(verdict.reasons) == 3

    def test_a_load_with_no_binder_has_no_ratio(self) -> None:
        verdict = judge_addition(addition(), BATCH_WATER, Quantity(0, "lb"), DESIGN_RATIO)
        with pytest.raises(ValidationError, match="no cementitious material"):
            _ = verdict.resulting_ratio

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="batch_water is a mass"):
            judge_addition(addition(), Quantity(1, "gal"), CEMENTITIOUS, DESIGN_RATIO)
        with pytest.raises(ValidationError, match="cementitious cannot be negative"):
            judge_addition(addition(), BATCH_WATER, Quantity(-1, "lb"), DESIGN_RATIO)
        with pytest.raises(ValidationError, match="design ratio has to be positive"):
            judge_addition(addition(), BATCH_WATER, CEMENTITIOUS, 0.0)

    def test_describe_when_it_is_fine(self) -> None:
        verdict = judge_addition(
            addition(amount=Quantity(1, "gal")), BATCH_WATER, CEMENTITIOUS, 0.46
        )
        assert "added by purchaser" in verdict.describe()
