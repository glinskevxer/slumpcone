from __future__ import annotations

import pytest

from slumpcone.report.ticket_print import (
    Clause,
    PrintedTicket,
    TicketItem,
    build_ticket,
    incomplete,
)
from tests.batching.test_engine import plant
from tests.factories import design
from tests.report.test_fleet import delivery, ticket


def printed(**overrides: object) -> PrintedTicket:
    base = ticket("881204")
    fields: dict[str, object] = {
        "truck_code": "TR-114",
        "purchaser": "Ashfield Paving",
        "project": "Route 9 shoulder",
    }
    fields.update(overrides)
    from dataclasses import replace

    return build_ticket(replace(base, **fields), plant(), design=design())  # type: ignore[arg-type]


class CaseTheRequiredTen:
    def test_a_full_ticket_is_complete(self) -> None:
        assert printed().is_complete
        assert printed().missing == ()

    def test_there_are_ten_required_items(self) -> None:
        assert len(printed().required) == 10

    def test_every_required_item_names_its_clause(self) -> None:
        for item in printed().required:
            assert item.clause is Clause.REQUIRED
            assert str(item.clause) == "14.1"

    def test_no_truck_number(self) -> None:
        found = printed(truck_code=None)
        assert not found.is_complete
        assert [one.number for one in found.missing] == ["4"]

    def test_no_purchaser(self) -> None:
        assert [one.number for one in printed(purchaser=None).missing] == ["5"]

    def test_no_job(self) -> None:
        assert [one.number for one in printed(project=None).missing] == ["6"]

    def test_several_missing_at_once(self) -> None:
        found = printed(truck_code=None, purchaser=None, project=None)
        assert len(found.missing) == 3

    def test_a_missing_item_describes(self) -> None:
        found = printed(truck_code=None)
        assert "MISSING" in found.missing[0].describe()
        assert "C94 14.1(4)" in found.missing[0].describe()

    def test_the_class_of_concrete_carries_the_revision(self) -> None:
        item = next(one for one in printed().items if one.number == "7")
        assert "rev" in item.value

    def test_describe(self) -> None:
        assert "complete under C94" in printed().describe()
        assert "1 required item(s) missing" in printed(truck_code=None).describe()


class CaseTheWaterLine:
    def test_it_is_there_by_default(self) -> None:
        assert "initials" in printed().render()

    def test_without_it_the_ticket_is_not_complete(self) -> None:
        from dataclasses import replace

        base = replace(
            ticket("881204"),
            truck_code="TR-114",
            purchaser="Ashfield Paving",
            project="Route 9 shoulder",
        )
        found = build_ticket(base, plant(), design=design(), water_line=False)
        assert not found.is_complete
        assert found.missing == ()

    def test_the_form_says_who_fills_it_in(self) -> None:
        assert "receiver" in printed().render()

    def test_the_item_itself_is_present(self) -> None:
        item = next(one for one in printed().items if one.number == "10")
        assert item.is_present


class CaseTheOptionalSix:
    def test_a_design_supplies_the_cement_content(self) -> None:
        found = printed()
        cement = next(one for one in found.items if one.number == "b")
        assert cement.is_present

    def test_and_the_admixtures(self) -> None:
        found = printed()
        admix = next(one for one in found.items if one.number == "c")
        assert admix.is_present

    def test_without_a_design_they_are_empty(self) -> None:
        from dataclasses import replace

        base = replace(
            ticket("881204"),
            truck_code="TR-114",
            purchaser="Ashfield Paving",
            project="Route 9 shoulder",
        )
        found = build_ticket(base, plant())
        assert not any(one.number == "b" and one.is_present for one in found.items)

    def test_but_the_ticket_is_still_complete(self) -> None:
        from dataclasses import replace

        base = replace(
            ticket("881204"),
            truck_code="TR-114",
            purchaser="Ashfield Paving",
            project="Route 9 shoulder",
        )
        assert build_ticket(base, plant()).is_complete

    def test_a_delivery_supplies_the_revolution_counter(self) -> None:
        from dataclasses import replace

        base = replace(
            ticket("881204"),
            truck_code="TR-114",
            purchaser="Ashfield Paving",
            project="Route 9 shoulder",
        )
        found = build_ticket(
            base,
            plant(),
            delivery=delivery("881204", revolutions_on_arrival=180),
        )
        counter = next(one for one in found.items if one.number == "a")
        assert counter.value == "180"

    def test_the_optional_items_that_are_there(self) -> None:
        assert printed().optional_present

    def test_they_are_all_clause_two(self) -> None:
        for item in printed().optional_present:
            assert item.clause is Clause.ON_REQUEST
            assert not item.clause.is_required


class CaseRendering:
    def test_the_heading_names_the_ticket(self) -> None:
        assert "Delivery ticket 881204" in printed().render()

    def test_the_labels_line_up_at_a_fixed_width(self) -> None:
        lines = [line for line in printed().render().splitlines() if ": " in line and line]
        positions = {line.index(": ") for line in lines}
        assert len(positions) == 1

    def test_a_missing_item_is_left_off_the_paper(self) -> None:
        assert "truck" not in printed(truck_code=None).render()

    def test_the_water_form_can_be_left_off(self) -> None:
        from dataclasses import replace

        base = replace(ticket("881204"), truck_code="TR-114")
        found = build_ticket(base, plant(), water_line=False)
        assert "initials" not in found.render()


class CaseAcrossManyTickets:
    def test_nothing_to_look_at(self) -> None:
        assert incomplete([printed()]) == ()

    def test_the_worst_comes_first(self) -> None:
        one = printed(truck_code=None)
        three = printed(truck_code=None, purchaser=None, project=None)
        assert incomplete([one, three])[0] is three

    def test_a_complete_ticket_is_left_out(self) -> None:
        assert len(incomplete([printed(), printed(truck_code=None)])) == 1

    def test_nothing_at_all(self) -> None:
        assert incomplete([]) == ()


@pytest.mark.parametrize("number", ["1", "2", "3", "8", "9"])
def test_the_items_that_can_never_be_missing(number: str) -> None:
    item = next(one for one in printed().items if one.number == number)
    assert item.is_present


def test_an_item_with_only_whitespace_is_missing() -> None:
    assert not TicketItem("4", Clause.REQUIRED, "truck", "   ").is_present
