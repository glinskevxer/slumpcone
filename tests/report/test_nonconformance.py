from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.haul import judge_haul
from slumpcone.fresh.acceptance import judge_load
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.report.nonconformance import (
    NonConformance,
    Severity,
    counts_by_severity,
    from_haul,
    from_load,
    from_strength,
    from_ticket,
    register_from,
    render_register,
    severity_of,
)
from slumpcone.strength.acceptance import evaluate_strength
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design
from tests.strength.test_acceptance import a_test

DAY = date(2024, 6, 12)
BATCHED = datetime(2024, 6, 12, 7, 42)


def ticket(**details: object) -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
    fields: dict[str, object] = {
        "truck_code": "TR-114",
        "purchaser": "Ashfield Paving",
        "project": "Route 9 shoulder",
    }
    fields.update(details)
    return BatchTicket.from_plan(planned, "881204", BATCHED, **fields)  # type: ignore[arg-type]


class CaseSeverity:
    def test_rank_puts_the_worst_first(self) -> None:
        assert Severity.MAJOR.rank < Severity.MINOR.rank < Severity.OBSERVATION.rank

    def test_which_need_a_response(self) -> None:
        assert Severity.MAJOR.needs_a_response
        assert Severity.MINOR.needs_a_response
        assert not Severity.OBSERVATION.needs_a_response

    def test_known_codes(self) -> None:
        assert severity_of("LOAD_REJECTED") is Severity.MAJOR
        assert severity_of("TICKET_INCOMPLETE") is Severity.MINOR

    def test_an_unknown_code_is_minor_not_ignored(self) -> None:
        assert severity_of("SOMETHING_NEW") is Severity.MINOR

    def test_prints_its_own_value(self) -> None:
        assert str(Severity.OBSERVATION) == "observation"


class CaseFromTicket:
    def test_a_clean_ticket_raises_nothing(self) -> None:
        assert from_ticket(ticket()) == ()

    def test_a_weight_out_of_tolerance(self) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        written = BatchTicket.from_plan(
            planned,
            "881204",
            BATCHED,
            {"CEM-I": Quantity(4400, "lb")},
            truck_code="TR-114",
            purchaser="Ashfield",
            project="Route 9",
        )
        found = from_ticket(written)
        assert found[0].code == "BATCH_WEIGHT_OUT_OF_TOLERANCE"
        assert found[0].severity is Severity.MINOR

    def test_an_admixture_dose_out_of_tolerance(self) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        written = BatchTicket.from_plan(
            planned,
            "881204",
            BATCHED,
            None,
            {"AD-AE": Quantity(90, "floz")},
            truck_code="TR-114",
            purchaser="Ashfield",
            project="Route 9",
        )
        found = from_ticket(written)
        assert found[0].code == "ADMIXTURE_DOSE_OUT_OF_TOLERANCE"
        assert "AD-AE" in found[0].detail

    def test_an_incomplete_ticket(self) -> None:
        found = from_ticket(ticket(truck_code=None))
        assert found[0].code == "TICKET_INCOMPLETE"
        assert "truck_code" in found[0].detail


class CaseFromLoad:
    def slump(self, value: float, minutes: int = 0, retest: bool = False) -> FreshTest:
        return FreshTest(
            "881204",
            FreshTestKind.SLUMP,
            BATCHED + timedelta(minutes=minutes),
            slump=Quantity(value, "in"),
            is_retest=retest,
        )

    def test_an_accepted_load_raises_nothing(self) -> None:
        verdict = judge_load("881204", [self.slump(4.0)], design())
        assert from_load(verdict, DAY) == ()

    def test_a_rejected_load(self) -> None:
        verdict = judge_load("881204", [self.slump(7.0), self.slump(6.9, 4, True)], design())
        found = from_load(verdict, DAY)
        assert found[0].code == "LOAD_REJECTED"
        assert found[0].severity is Severity.MAJOR

    def test_an_outstanding_retest(self) -> None:
        verdict = judge_load("881204", [self.slump(7.0)], design())
        found = from_load(verdict, DAY)
        assert found[0].code == "LOAD_RETEST_OUTSTANDING"
        assert found[0].severity is Severity.OBSERVATION


class CaseFromHaul:
    def test_a_good_haul_raises_nothing(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=50), 180)
        assert from_haul(verdict, "881204", DAY) == ()

    def test_a_late_discharge(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=100), 180)
        found = from_haul(verdict, "881204", DAY)
        assert found[0].code == "DISCHARGE_LATE"

    def test_too_many_revolutions(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=50), 340)
        found = from_haul(verdict, "881204", DAY)
        assert found[0].code == "REVOLUTIONS_EXCEEDED"

    def test_both_at_once(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=120), 340)
        assert len(from_haul(verdict, "881204", DAY)) == 2


class CaseFromStrength:
    def test_a_satisfactory_record_raises_nothing(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 4500.0), a_test("S-2", 4600.0, 1), a_test("S-3", 4700.0, 2)],
            Quantity(4000, "psi"),
        )
        assert from_strength(report, DAY) == ()

    def test_an_investigation(self) -> None:
        report = evaluate_strength(
            "4000P-57",
            [a_test("S-1", 3000.0), a_test("S-2", 3100.0, 1), a_test("S-3", 3200.0, 2)],
            Quantity(4000, "psi"),
        )
        found = from_strength(report, DAY)
        assert found[0].code == "STRENGTH_INVESTIGATE"
        assert found[0].subject == "mix 4000P-57"


class CaseRegister:
    def entries(self) -> tuple[NonConformance, ...]:
        return register_from(
            [
                from_ticket(ticket(truck_code=None)),
                (
                    NonConformance(
                        "DISCHARGE_LATE", "ticket 881205", DAY, "97 minutes", "delivery"
                    ),
                ),
                (
                    NonConformance(
                        "LOAD_RETEST_OUTSTANDING",
                        "ticket 881206",
                        date(2024, 6, 11),
                        "no retest",
                    ),
                ),
            ]
        )

    def test_worst_first(self) -> None:
        assert [entry.severity for entry in self.entries()] == [
            Severity.MAJOR,
            Severity.MINOR,
            Severity.OBSERVATION,
        ]

    def test_counts_include_the_empty_severities(self) -> None:
        tally = counts_by_severity(())
        assert tally == dict.fromkeys(Severity, 0)

    def test_counts(self) -> None:
        tally = counts_by_severity(self.entries())
        assert tally[Severity.MAJOR] == 1
        assert tally[Severity.MINOR] == 1

    def test_render(self) -> None:
        text = render_register(self.entries())
        assert "raised" in text.splitlines()[0]
        assert "DISCHARGE_LATE" in text
        assert "ticket 881204" in text

    def test_an_empty_register_still_prints_a_heading(self) -> None:
        assert "severity" in render_register(()).splitlines()[0]

    def test_describe(self) -> None:
        entry = NonConformance("DISCHARGE_LATE", "ticket 881205", DAY, "97 minutes")
        assert (
            entry.describe() == "2024-06-12  major  DISCHARGE_LATE  ticket 881205  97 minutes"
        )


@pytest.mark.parametrize(
    "code", list({"LOAD_REJECTED", "DISCHARGE_LATE", "STRENGTH_INVESTIGATE"})
)
def test_the_major_codes_all_need_a_response(code: str) -> None:
    assert severity_of(code).needs_a_response
