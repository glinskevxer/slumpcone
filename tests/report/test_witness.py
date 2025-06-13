from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.people.certification import Certification, Grade, Technician
from slumpcone.report.witness import (
    CERTIFIED_AS,
    WitnessAudit,
    WitnessProblem,
    audit_witnesses,
)
from slumpcone.units.quantity import Quantity

MARCH = datetime(2024, 3, 12, 9, 30)
JUNE = datetime(2024, 6, 12, 9, 30)


def slump(
    technician: str | None = "T-1", *, at: datetime = JUNE, number: str = "881204"
) -> FreshTest:
    return FreshTest(
        number,
        FreshTestKind.SLUMP,
        at,
        slump=Quantity(4.0, "in"),
        technician=technician,
    )


def air(technician: str | None = "T-1", *, at: datetime = JUNE) -> FreshTest:
    from slumpcone.percent import Percent

    return FreshTest(
        "881204",
        FreshTestKind.AIR_PRESSURE,
        at,
        air=Percent(6.0),
        technician=technician,
    )


def tech(
    *,
    code: str = "T-1",
    grade: Grade = Grade.FIELD_GRADE_I,
    issued: date = date(2022, 6, 1),
    expires: date = date(2027, 6, 1),
) -> Technician:
    return Technician(
        code, "R. Okafor", (Certification(grade, f"ACI-{code}", issued, expires),)
    )


class CaseClean:
    def test_a_certified_technician_stands(self) -> None:
        audit = audit_witnesses([slump()], [tech()])
        assert audit.is_clean
        assert audit.sound == 1

    def test_two_results_by_the_same_person(self) -> None:
        audit = audit_witnesses([slump(), air()], [tech()])
        assert audit.is_clean
        assert audit.checked == 2

    def test_nothing_to_check(self) -> None:
        audit = audit_witnesses([], [tech()])
        assert audit.is_clean
        assert audit.checked == 0

    def test_describe(self) -> None:
        assert "every one stands" in audit_witnesses([slump()], [tech()]).describe()


class CaseTheDayMatters:
    def test_a_test_run_before_the_card_lapsed_stands(self) -> None:
        person = tech(issued=date(2019, 1, 1), expires=date(2024, 4, 1))
        audit = audit_witnesses([slump(at=MARCH)], [person])
        assert audit.is_clean

    def test_the_same_person_in_june_does_not(self) -> None:
        person = tech(issued=date(2019, 1, 1), expires=date(2024, 4, 1))
        audit = audit_witnesses([slump(at=JUNE)], [person])
        assert not audit.is_clean
        assert audit.findings[0].problem is WitnessProblem.CARD_LAPSED

    def test_a_renewal_does_not_reach_backwards(self) -> None:
        # The card on file starts in May. A test taken in March was taken by
        # somebody who did not hold it yet.
        person = tech(issued=date(2024, 5, 1), expires=date(2029, 5, 1))
        audit = audit_witnesses([slump(at=MARCH)], [person])
        assert audit.findings[0].problem is WitnessProblem.CARD_LAPSED

    def test_and_the_june_test_by_the_same_person_stands(self) -> None:
        person = tech(issued=date(2024, 5, 1), expires=date(2029, 5, 1))
        assert audit_witnesses([slump(at=JUNE)], [person]).is_clean

    def test_a_mixed_run_splits_correctly(self) -> None:
        person = tech(issued=date(2019, 1, 1), expires=date(2024, 4, 1))
        audit = audit_witnesses([slump(at=MARCH), slump(at=JUNE)], [person])
        assert audit.checked == 2
        assert audit.sound == 1


class CaseProblems:
    def test_no_technician_written_down(self) -> None:
        audit = audit_witnesses([slump(None)], [tech()])
        assert audit.findings[0].problem is WitnessProblem.NOBODY_NAMED

    def test_an_empty_technician_is_the_same_thing(self) -> None:
        test = FreshTest("881204", FreshTestKind.SLUMP, JUNE, slump=Quantity(4.0, "in"))
        audit = audit_witnesses([test], [tech()])
        assert audit.findings[0].problem is WitnessProblem.NOBODY_NAMED

    def test_a_technician_nobody_filed(self) -> None:
        audit = audit_witnesses([slump("T-9")], [tech()])
        assert audit.findings[0].problem is WitnessProblem.NOT_ON_FILE
        assert audit.findings[0].technician == "T-9"

    def test_the_wrong_certification_entirely(self) -> None:
        person = tech(grade=Grade.STRENGTH_TESTING)
        audit = audit_witnesses([slump()], [person])
        assert audit.findings[0].problem is WitnessProblem.NOT_CERTIFIED

    def test_somebody_with_no_cards_at_all(self) -> None:
        person = Technician("T-1", "R. Okafor")
        audit = audit_witnesses([slump()], [person])
        assert audit.findings[0].problem is WitnessProblem.NOT_CERTIFIED

    def test_the_finding_describes(self) -> None:
        audit = audit_witnesses([slump("T-9")], [tech()])
        text = audit.findings[0].describe()
        assert "881204" in text
        assert "not on file" in text

    def test_a_finding_with_nobody_named_describes(self) -> None:
        audit = audit_witnesses([slump(None)], [tech()])
        assert "nobody" in audit.findings[0].describe()


class CaseWhatCanBeFixed:
    def test_a_missing_name_is_paperwork(self) -> None:
        assert WitnessProblem.NOBODY_NAMED.is_a_records_problem
        assert WitnessProblem.NOT_ON_FILE.is_a_records_problem

    def test_a_lapsed_or_absent_card_is_not(self) -> None:
        assert not WitnessProblem.CARD_LAPSED.is_a_records_problem
        assert not WitnessProblem.NOT_CERTIFIED.is_a_records_problem

    def test_the_retest_list(self) -> None:
        person = tech(grade=Grade.STRENGTH_TESTING)
        audit = audit_witnesses([slump(None), slump()], [person])
        assert len(audit.findings) == 2
        assert len(audit.needs_retest) == 1

    def test_describe_counts_the_retests(self) -> None:
        person = tech(grade=Grade.STRENGTH_TESTING)
        text = audit_witnesses([slump(None), slump()], [person]).describe()
        assert "2 would not stand" in text
        assert "1 of those need a retest" in text

    def test_filtering_by_problem(self) -> None:
        audit = audit_witnesses([slump(None), slump("T-9")], [tech()])
        assert len(audit.of_problem(WitnessProblem.NOBODY_NAMED)) == 1
        assert len(audit.of_problem(WitnessProblem.NOT_ON_FILE)) == 1

    def test_the_counts_carry_every_problem(self) -> None:
        counts = audit_witnesses([slump(None)], [tech()]).counts()
        assert set(counts) == set(WitnessProblem)
        assert counts[WitnessProblem.NOBODY_NAMED] == 1
        assert counts[WitnessProblem.CARD_LAPSED] == 0


class CaseMapping:
    def test_every_fresh_test_maps_to_a_certification(self) -> None:
        assert set(CERTIFIED_AS) == set(FreshTestKind)

    def test_both_air_methods_sit_under_one_card(self) -> None:
        assert (
            CERTIFIED_AS[FreshTestKind.AIR_PRESSURE]
            == CERTIFIED_AS[FreshTestKind.AIR_VOLUMETRIC]
        )

    def test_a_volumetric_air_test_is_covered_by_the_field_card(self) -> None:
        from slumpcone.percent import Percent

        test = FreshTest(
            "881204",
            FreshTestKind.AIR_VOLUMETRIC,
            JUNE,
            air=Percent(6.0),
            technician="T-1",
        )
        assert audit_witnesses([test], [tech()]).is_clean


def test_an_empty_audit_is_clean() -> None:
    audit = WitnessAudit(0, ())
    assert audit.is_clean
    assert audit.sound == 0
    assert audit.needs_retest == ()


@pytest.mark.parametrize("code", ["t-1", " T-1 ", "T-1"])
def test_the_technician_code_is_matched_case_insensitively(code: str) -> None:
    assert audit_witnesses([slump(code)], [tech()]).is_clean
