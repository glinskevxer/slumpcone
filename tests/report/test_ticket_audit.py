from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.report.ticket_audit import (
    audit_summary,
    render_audit,
    render_audit_report,
    render_ticket,
    ticket_findings,
)
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

DAY = date(2024, 6, 12)


def ticket(
    number: str = "881204",
    hour: int = 7,
    actuals: dict[str, Quantity] | None = None,
    doses: dict[str, Quantity] | None = None,
    **details: object,
) -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
    fields: dict[str, object] = {
        "truck_code": "TR-114",
        "purchaser": "Ashfield Paving",
        "project": "Route 9 shoulder",
        "cumulative_volume": Quantity(27, "yd3"),
        "water_held_back": Quantity(90, "lb"),
    }
    fields.update(details)
    return BatchTicket.from_plan(
        planned,
        number,
        datetime(2024, 6, 12, hour, 42),
        actuals,
        doses,
        **fields,
    )


class CaseRenderTicket:
    def test_the_header_block(self) -> None:
        text = render_ticket(ticket())
        assert "Ticket 881204" in text
        assert "plant     : PL-1" in text
        assert "truck     : TR-114" in text
        assert "mix       : 4000P-57 r1" in text
        assert "quantity  : 9.00 yd3" in text

    def test_a_missing_field_prints_a_dash(self) -> None:
        text = render_ticket(ticket(truck_code=None, cumulative_volume=None))
        assert "truck     : -" in text
        assert "to date   : -" in text

    def test_the_material_table(self) -> None:
        text = render_ticket(ticket())
        assert "material" in text
        assert "CEM-I" in text
        assert "ok" in text

    def test_an_out_of_tolerance_line(self) -> None:
        text = render_ticket(ticket(actuals={"CEM-I": Quantity(4400, "lb")}))
        assert "out high" in text

    def test_the_admixture_table(self) -> None:
        text = render_ticket(ticket())
        assert "admixture" in text
        assert "AD-AE" in text

    def test_a_note_is_printed(self) -> None:
        text = render_ticket(ticket(notes="held water for the finisher"))
        assert "note: held water for the finisher" in text

    def test_no_note_prints_nothing(self) -> None:
        assert "note:" not in render_ticket(ticket())


class CaseFindings:
    def test_a_clean_ticket(self) -> None:
        assert ticket_findings(ticket()) == ()

    def test_a_weight_out_of_tolerance(self) -> None:
        found = ticket_findings(ticket(actuals={"CEM-I": Quantity(4400, "lb")}))
        assert found == ("CEM-I high",)

    def test_a_dose_out_of_tolerance(self) -> None:
        found = ticket_findings(ticket(doses={"AD-AE": Quantity(90, "floz")}))
        assert found == ("AD-AE dose",)

    def test_a_missing_field(self) -> None:
        assert ticket_findings(ticket(purchaser=None)) == ("no purchaser",)

    def test_several_at_once(self) -> None:
        found = ticket_findings(ticket(actuals={"CEM-I": Quantity(4400, "lb")}, purchaser=None))
        assert len(found) == 2


class CaseAudit:
    def run(self) -> list[BatchTicket]:
        return [
            ticket("881204", 7),
            ticket("881205", 9, actuals={"CEM-I": Quantity(4400, "lb")}),
            ticket("881206", 8),
        ]

    def test_one_line_per_ticket_in_time_order(self) -> None:
        text = render_audit(self.run())
        lines = text.splitlines()[2:]
        assert [line.split()[0] for line in lines] == ["881204", "881206", "881205"]

    def test_a_clean_line_says_ok(self) -> None:
        assert "ok" in render_audit([ticket()])

    def test_a_finding_is_named(self) -> None:
        text = render_audit(self.run())
        assert "CEM-I high" in text

    def test_the_summary(self) -> None:
        text = audit_summary(self.run())
        assert "tickets      : 3" in text
        assert "with findings: 1" in text
        assert "volume       : 27.0 yd3" in text
        assert "clean        : 66.7%" in text

    def test_an_empty_run_summarises_to_nothing(self) -> None:
        text = audit_summary([])
        assert "tickets      : 0" in text
        assert "volume       : -" in text

    def test_the_whole_report(self) -> None:
        text = render_audit_report(self.run())
        assert "Ticket audit" in text
        assert "with findings" in text


@pytest.mark.parametrize("count", [1, 3])
def test_the_clean_share_is_a_percentage(count: int) -> None:
    tickets = [ticket(f"88120{index}", 7 + index) for index in range(count)]
    assert "100.0%" in audit_summary(tickets)
