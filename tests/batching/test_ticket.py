from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.batching.engine import PlannedBatch, plan_batch
from slumpcone.batching.ticket import (
    REQUIRED_TICKET_FIELDS,
    BatchTicket,
    TicketAdmixture,
    TicketLine,
)
from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

BATCHED_AT = datetime(2024, 6, 12, 7, 42)
DAY = date(2024, 6, 12)


def planned() -> PlannedBatch:
    return plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)


def ticket(**details: object) -> BatchTicket:
    fields: dict[str, object] = {
        "truck_code": "TR-114",
        "purchaser": "Ashfield Paving",
        "project": "Route 9 shoulder",
    }
    fields.update(details)
    return BatchTicket.from_plan(planned(), "881204", BATCHED_AT, **fields)  # type: ignore[arg-type]


class CaseTicketLine:
    def test_code_is_normalised(self) -> None:
        line = TicketLine(
            "cem i",
            MaterialClass.CEMENT,
            Quantity(4230, "lb"),
            Quantity(4230, "lb"),
            Quantity(42, "lb"),
        )
        assert line.material_code == "CEM-I"

    def test_the_weights_have_to_be_masses(self) -> None:
        with pytest.raises(ValidationError, match="required is a mass"):
            TicketLine(
                "CEM-I",
                MaterialClass.CEMENT,
                Quantity(1, "yd3"),
                Quantity(1, "lb"),
                Quantity(1, "lb"),
            )

    def test_a_negative_recorded_weight_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            TicketLine(
                "CEM-I",
                MaterialClass.CEMENT,
                Quantity(1, "lb"),
                Quantity(-1, "lb"),
                Quantity(1, "lb"),
            )

    def test_the_result_carries_the_verdict(self) -> None:
        line = TicketLine(
            "CEM-I",
            MaterialClass.CEMENT,
            Quantity(4230, "lb"),
            Quantity(4300, "lb"),
            Quantity(42, "lb"),
        )
        assert not line.result.conforms


class CaseTicketAdmixture:
    def test_inside_three_percent(self) -> None:
        entry = TicketAdmixture("AD-AE", Quantity(60.0, "floz"), Quantity(61.5, "floz"))
        assert entry.conforms
        assert entry.error.value == pytest.approx(1.5)

    def test_outside_three_percent(self) -> None:
        entry = TicketAdmixture("AD-AE", Quantity(60.0, "floz"), Quantity(64.0, "floz"))
        assert not entry.conforms

    def test_a_zero_call_wants_a_zero_dose(self) -> None:
        assert TicketAdmixture("AD-AE", Quantity(0, "floz"), Quantity(0, "floz")).conforms
        assert not TicketAdmixture("AD-AE", Quantity(0, "floz"), Quantity(1, "floz")).conforms

    def test_the_doses_have_to_be_volumes(self) -> None:
        with pytest.raises(ValidationError, match="called_for is a volume"):
            TicketAdmixture("AD-AE", Quantity(1, "lb"), Quantity(1, "floz"))


class CaseConstruction:
    def test_identifiers_are_normalised(self) -> None:
        built = ticket(truck_code="tr 114", purchaser="  Ashfield   Paving ")
        assert built.number == "881204"
        assert built.truck_code == "TR-114"
        assert built.purchaser == "Ashfield Paving"

    def test_the_volume_has_to_be_a_volume(self) -> None:
        with pytest.raises(ValidationError, match="load size is a volume"):
            BatchTicket("1", "PL-1", "M", 1, BATCHED_AT, Quantity(1, "lb"), ())

    def test_the_volume_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            BatchTicket("1", "PL-1", "M", 1, BATCHED_AT, Quantity(0, "yd3"), ())

    def test_the_revision_starts_at_one(self) -> None:
        with pytest.raises(ValidationError, match="revision starts at one"):
            BatchTicket("1", "PL-1", "M", 0, BATCHED_AT, Quantity(9, "yd3"), ())

    def test_a_negative_revolution_counter_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot read negative"):
            BatchTicket(
                "1", "PL-1", "M", 1, BATCHED_AT, Quantity(9, "yd3"), (), revolution_counter=-1
            )


class CaseFromPlan:
    def test_every_line_is_carried_over(self) -> None:
        assert len(ticket().lines) == 5

    def test_an_unrecorded_line_is_taken_as_exact(self) -> None:
        assert ticket().line("CEM-I").actual == Quantity(4230, "lb")
        assert ticket().out_of_tolerance == ()

    def test_a_recorded_weight_is_judged(self) -> None:
        written = BatchTicket.from_plan(
            planned(), "881204", BATCHED_AT, {"CEM-I": Quantity(4300, "lb")}
        )
        assert [r.material_code for r in written.out_of_tolerance] == ["CEM-I"]

    def test_a_recorded_dose_is_judged(self) -> None:
        written = BatchTicket.from_plan(
            planned(), "881204", BATCHED_AT, None, {"AD-AE": Quantity(80, "floz")}
        )
        assert [a.material_code for a in written.admixtures_out_of_tolerance] == ["AD-AE"]

    def test_the_admixtures_are_carried_over(self) -> None:
        assert [a.material_code for a in ticket().admixtures] == ["AD-AE", "AD-WR"]

    def test_the_mix_identity_comes_from_the_plan(self) -> None:
        assert ticket().mix_code == "4000P-57"
        assert ticket().mix_revision == 1

    def test_an_unknown_line_is_named(self) -> None:
        with pytest.raises(ValidationError, match="not on this ticket"):
            ticket().line("CEM-III")


class CaseCompleteness:
    def test_a_full_ticket(self) -> None:
        assert ticket().is_complete
        assert ticket().missing_required_fields() == ()

    def test_a_ticket_with_no_truck(self) -> None:
        assert ticket(truck_code=None).missing_required_fields() == ("truck_code",)

    def test_a_ticket_with_nothing_filled_in(self) -> None:
        bare = BatchTicket.from_plan(planned(), "881204", BATCHED_AT)
        assert set(bare.missing_required_fields()) == {"truck_code", "purchaser", "project"}
        assert not bare.is_complete

    def test_the_required_list_is_the_c94_one(self) -> None:
        assert "batched_at" in REQUIRED_TICKET_FIELDS
        assert "volume" in REQUIRED_TICKET_FIELDS


class CaseReporting:
    def test_batched_weight(self) -> None:
        assert ticket().batched_weight.value == pytest.approx(
            sum(line.actual.value for line in ticket().lines)
        )

    def test_describe(self) -> None:
        text = ticket().describe()
        assert "ticket 881204" in text
        assert "4000P-57 r1" in text
        assert "9.00 yd3" in text
        assert "2024-06-12 07:42" in text
