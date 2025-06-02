from __future__ import annotations

from datetime import date

import pytest

from slumpcone.people.certification import (
    FIELD_TESTS,
    Certification,
    CertificationError,
    Grade,
    Technician,
    TestKind,
    uncovered,
    who_may_run,
)

TODAY = date(2024, 6, 12)


def card(
    grade: Grade = Grade.FIELD_GRADE_I,
    number: str = "ACI-1001",
    *,
    issued: date = date(2022, 6, 1),
    expires: date = date(2027, 6, 1),
) -> Certification:
    return Certification(grade, number, issued, expires)


def tech(*cards: Certification, code: str = "T-1", name: str = "R. Okafor") -> Technician:
    return Technician(code, name, cards)


class CaseGrades:
    def test_field_grade_one_covers_the_field_tests(self) -> None:
        assert Grade.FIELD_GRADE_I.covers == FIELD_TESTS

    def test_it_does_not_cover_breaking_cylinders(self) -> None:
        assert not Grade.FIELD_GRADE_I.allows(TestKind.BREAKING_CYLINDERS)

    def test_a_strength_technician_cannot_run_a_slump_cone(self) -> None:
        assert not Grade.STRENGTH_TESTING.allows(TestKind.SLUMP)
        assert Grade.STRENGTH_TESTING.allows(TestKind.BREAKING_CYLINDERS)

    def test_level_two_covers_level_one(self) -> None:
        assert Grade.LAB_LEVEL_1.covers <= Grade.LAB_LEVEL_2.covers

    def test_level_two_adds_grading(self) -> None:
        assert Grade.LAB_LEVEL_2.allows(TestKind.AGGREGATE_GRADING)
        assert not Grade.LAB_LEVEL_1.allows(TestKind.AGGREGATE_GRADING)

    def test_the_grade_reads_as_words(self) -> None:
        assert str(Grade.FIELD_GRADE_I) == "field grade I"

    def test_a_test_kind_reads_as_words(self) -> None:
        assert str(TestKind.UNIT_WEIGHT) == "unit weight"

    def test_field_and_lab_tests_are_told_apart(self) -> None:
        assert TestKind.SLUMP.is_field_test
        assert not TestKind.BREAKING_CYLINDERS.is_field_test


class CaseCard:
    def test_it_holds_what_it_was_given(self) -> None:
        one = card()
        assert one.grade is Grade.FIELD_GRADE_I
        assert one.number == "ACI-1001"

    def test_the_number_is_normalised(self) -> None:
        assert card(number=" aci-1001 ").number == "ACI-1001"

    def test_an_expiry_before_the_issue(self) -> None:
        with pytest.raises(CertificationError) as caught:
            card(issued=date(2024, 1, 1), expires=date(2023, 1, 1))
        assert caught.value.code == "CERTIFICATION_EXPIRES_BEFORE_ISSUE"

    def test_an_expiry_on_the_issue_day(self) -> None:
        with pytest.raises(CertificationError):
            card(issued=date(2024, 1, 1), expires=date(2024, 1, 1))

    def test_a_current_card(self) -> None:
        assert card().is_current(TODAY)

    def test_a_card_not_issued_yet(self) -> None:
        assert not card(issued=date(2025, 1, 1), expires=date(2030, 1, 1)).is_current(TODAY)

    def test_a_lapsed_card(self) -> None:
        assert not card(expires=date(2023, 1, 1)).is_current(TODAY)

    def test_the_expiry_day_itself_still_counts(self) -> None:
        assert card(expires=TODAY).is_current(TODAY)
        assert card(expires=TODAY).days_left(TODAY) == 0

    def test_days_left(self) -> None:
        assert card(expires=date(2024, 6, 22)).days_left(TODAY) == 10

    def test_days_left_goes_negative(self) -> None:
        assert card(expires=date(2024, 6, 2)).days_left(TODAY) == -10

    def test_expiring_within_a_window(self) -> None:
        assert card(expires=date(2024, 7, 1)).expires_within(TODAY, 60)
        assert not card(expires=date(2027, 6, 1)).expires_within(TODAY, 60)

    def test_a_lapsed_card_is_not_expiring(self) -> None:
        assert not card(expires=date(2023, 1, 1)).expires_within(TODAY, 60)

    def test_describe(self) -> None:
        assert "expires 2027-06-01" in card().describe()


class CaseTechnician:
    def test_the_code_and_name_are_normalised(self) -> None:
        person = tech(card(), code=" t-1 ")
        assert person.code == "T-1"
        assert person.name == "R. Okafor"

    def test_the_same_card_number_twice(self) -> None:
        with pytest.raises(CertificationError) as caught:
            tech(card(number="ACI-1"), card(Grade.LAB_LEVEL_1, "ACI-1"))
        assert caught.value.code == "CERTIFICATION_TWICE"

    def test_somebody_with_no_cards(self) -> None:
        person = tech()
        assert person.current(TODAY) == ()
        assert person.qualified_for() == frozenset()
        assert not person.may_run(TestKind.SLUMP, TODAY)

    def test_a_current_field_card_allows_the_field_tests(self) -> None:
        person = tech(card())
        for kind in FIELD_TESTS:
            assert person.may_run(kind, TODAY)

    def test_it_does_not_allow_a_lab_test(self) -> None:
        assert not tech(card()).may_run(TestKind.BREAKING_CYLINDERS, TODAY)

    def test_a_lapsed_card_allows_nothing(self) -> None:
        person = tech(card(expires=date(2023, 1, 1)))
        assert not person.may_run(TestKind.SLUMP, TODAY)
        assert person.current(TODAY) == ()

    def test_but_they_are_still_qualified_on_paper(self) -> None:
        person = tech(card(expires=date(2023, 1, 1)))
        assert TestKind.SLUMP in person.qualified_for()

    def test_two_cards_add_up(self) -> None:
        person = tech(card(), card(Grade.STRENGTH_TESTING, "ACI-2"))
        assert person.may_run(TestKind.SLUMP, TODAY)
        assert person.may_run(TestKind.BREAKING_CYLINDERS, TODAY)

    def test_the_lapsed_list(self) -> None:
        person = tech(card(), card(Grade.LAB_LEVEL_1, "ACI-2", expires=date(2023, 1, 1)))
        assert [one.number for one in person.lapsed(TODAY)] == ["ACI-2"]

    def test_the_expiring_list_is_soonest_first(self) -> None:
        person = tech(
            card(number="ACI-1", expires=date(2024, 8, 1)),
            card(Grade.LAB_LEVEL_1, "ACI-2", expires=date(2024, 7, 1)),
        )
        assert [one.number for one in person.expiring(TODAY, days=90)] == [
            "ACI-2",
            "ACI-1",
        ]

    def test_nothing_expiring_in_a_short_window(self) -> None:
        assert tech(card()).expiring(TODAY, days=7) == ()

    def test_describe(self) -> None:
        person = tech(card(), card(Grade.LAB_LEVEL_1, "ACI-2", expires=date(2023, 1, 1)))
        text = person.describe(TODAY)
        assert "1 current card(s)" in text
        assert "1 lapsed" in text


class CaseRoster:
    def roster(self) -> list[Technician]:
        return [
            tech(card(number="ACI-1"), code="T-2"),
            tech(card(Grade.STRENGTH_TESTING, "ACI-2"), code="T-1"),
            tech(card(number="ACI-3", expires=date(2023, 1, 1)), code="T-3"),
        ]

    def test_who_may_run_a_field_test(self) -> None:
        found = who_may_run(self.roster(), TestKind.SLUMP, TODAY)
        assert [one.code for one in found] == ["T-2"]

    def test_who_may_break_cylinders(self) -> None:
        found = who_may_run(self.roster(), TestKind.BREAKING_CYLINDERS, TODAY)
        assert [one.code for one in found] == ["T-1"]

    def test_the_result_is_in_code_order(self) -> None:
        roster = [
            tech(card(number="ACI-9"), code="T-9"),
            tech(card(number="ACI-1"), code="T-1"),
        ]
        assert [one.code for one in who_may_run(roster, TestKind.SLUMP, TODAY)] == [
            "T-1",
            "T-9",
        ]

    def test_nobody_at_all(self) -> None:
        assert who_may_run([], TestKind.SLUMP, TODAY) == ()

    def test_what_nobody_can_do(self) -> None:
        gaps = uncovered(self.roster(), list(TestKind), TODAY)
        assert TestKind.AGGREGATE_GRADING in gaps
        assert TestKind.SLUMP not in gaps

    def test_nothing_uncovered_when_everything_is(self) -> None:
        roster = [
            tech(card(number="ACI-1"), code="T-1"),
            tech(card(Grade.LAB_LEVEL_2, "ACI-2"), code="T-2"),
        ]
        assert uncovered(roster, list(TestKind), TODAY) == ()

    def test_an_empty_roster_covers_nothing(self) -> None:
        assert set(uncovered([], list(TestKind), TODAY)) == set(TestKind)

    def test_asking_about_nothing(self) -> None:
        assert uncovered(self.roster(), [], TODAY) == ()

    def test_a_roster_that_lapses_overnight(self) -> None:
        roster = [tech(card(number="ACI-1", expires=TODAY), code="T-1")]
        assert uncovered(roster, [TestKind.SLUMP], TODAY) == ()
        assert uncovered(roster, [TestKind.SLUMP], date(2024, 6, 13)) == (TestKind.SLUMP,)
