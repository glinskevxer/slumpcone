from __future__ import annotations

from datetime import date

import pytest

from slumpcone.people.certification import Certification, Grade, Technician
from slumpcone.register import Register
from slumpcone.report.compliance import (
    DueKind,
    blocking,
    calendar,
    from_technicians,
    overdue,
    uncovered_tests,
)
from slumpcone.report.daily import summarise_day

TODAY = date(2024, 6, 12)


def card(
    grade: Grade = Grade.FIELD_GRADE_I,
    number: str = "ACI-1001",
    *,
    expires: date = date(2027, 6, 1),
) -> Certification:
    return Certification(grade, number, date(2022, 6, 1), expires)


def tech(*cards: Certification, code: str = "T-1") -> Technician:
    return Technician(code, "R. Okafor", cards)


class CaseCalendarItems:
    def test_a_card_becomes_an_item(self) -> None:
        items = from_technicians([tech(card())], TODAY)
        assert len(items) == 1
        assert items[0].kind is DueKind.TECHNICIAN_CARD

    def test_the_subject_names_the_person_and_the_card(self) -> None:
        items = from_technicians([tech(card())], TODAY)
        assert items[0].subject == "T-1 ACI-1001"

    def test_the_detail_carries_the_grade_and_standing(self) -> None:
        items = from_technicians([tech(card())], TODAY)
        assert "field grade I" in items[0].detail
        assert "current" in items[0].detail

    def test_a_lapsed_card_says_so(self) -> None:
        items = from_technicians([tech(card(expires=date(2023, 1, 1)))], TODAY)
        assert "lapsed" in items[0].detail

    def test_an_old_lapse_is_still_reported(self) -> None:
        ancient = Certification(
            Grade.FIELD_GRADE_I, "ACI-1001", date(2014, 1, 1), date(2019, 1, 1)
        )
        items = from_technicians([tech(ancient)], TODAY)
        assert len(items) == 1
        assert "lapsed" in items[0].detail

    def test_somebody_with_no_cards_contributes_nothing(self) -> None:
        assert from_technicians([tech()], TODAY) == ()

    def test_nobody_at_all(self) -> None:
        assert from_technicians([], TODAY) == ()

    def test_two_people_with_two_cards_each(self) -> None:
        roster = [
            tech(card(number="ACI-1"), card(Grade.LAB_LEVEL_1, "ACI-2"), code="T-1"),
            tech(card(number="ACI-3"), card(Grade.LAB_LEVEL_2, "ACI-4"), code="T-2"),
        ]
        assert len(from_technicians(roster, TODAY)) == 4


class CaseBlocking:
    def test_a_lapsed_card_is_overdue(self) -> None:
        items = from_technicians([tech(card(expires=date(2023, 1, 1)))], TODAY)
        assert len(overdue(items, TODAY)) == 1

    def test_a_lapsed_card_blocks(self) -> None:
        items = from_technicians([tech(card(expires=date(2023, 1, 1)))], TODAY)
        assert len(blocking(items, TODAY)) == 1

    def test_a_card_kind_blocks_batching(self) -> None:
        assert DueKind.TECHNICIAN_CARD.blocks_batching

    def test_a_current_card_does_not_block(self) -> None:
        items = from_technicians([tech(card())], TODAY)
        assert blocking(items, TODAY) == ()

    def test_a_card_running_out_lands_on_the_calendar(self) -> None:
        items = from_technicians([tech(card(expires=date(2024, 7, 1)))], TODAY)
        assert len(calendar(items, TODAY, horizon_days=45)) == 1

    def test_a_card_running_out_next_year_does_not(self) -> None:
        items = from_technicians([tech(card())], TODAY)
        assert calendar(items, TODAY, horizon_days=45) == ()


class CaseUncovered:
    def test_a_field_technician_covers_the_field_tests(self) -> None:
        gaps = uncovered_tests([tech(card())], TODAY)
        assert "slump" not in gaps
        assert "breaking cylinders" in gaps

    def test_nobody_covers_anything(self) -> None:
        assert len(uncovered_tests([], TODAY)) == 9

    def test_a_lapsed_card_covers_nothing(self) -> None:
        gaps = uncovered_tests([tech(card(expires=date(2023, 1, 1)))], TODAY)
        assert "slump" in gaps

    def test_the_names_read_as_words(self) -> None:
        assert "unit weight" in uncovered_tests([], TODAY)


class CaseTheDailyPage:
    @pytest.fixture()
    def register(self) -> Register:
        from slumpcone.demo import seed

        register = Register.in_memory()
        seed(register)
        return register

    def test_a_plant_with_no_technicians_reports_nothing_uncovered(
        self, register: Register
    ) -> None:
        # Nobody on file at all is a plant that has not started keeping this
        # record, not a plant that cannot test. It stays quiet until somebody
        # is filed.
        summary = summarise_day(register, TODAY)
        assert summary.uncovered_tests == ()

    def test_one_field_technician_leaves_the_lab_tests_uncovered(
        self, register: Register
    ) -> None:
        register.people.save(tech(card()))
        summary = summarise_day(register, TODAY)
        assert "breaking cylinders" in summary.uncovered_tests
        assert "slump" not in summary.uncovered_tests

    def test_an_uncovered_test_needs_attention(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert summarise_day(register, TODAY).needs_attention

    def test_the_page_prints_it(self, register: Register) -> None:
        from slumpcone.report.daily import render_day

        register.people.save(tech(card()))
        text = render_day(summarise_day(register, TODAY))
        assert "tests nobody may run" in text
        assert "breaking cylinders" in text

    def test_a_full_roster_leaves_nothing_uncovered(self, register: Register) -> None:
        register.people.save(tech(card(number="ACI-1"), code="T-1"))
        register.people.save(tech(card(Grade.LAB_LEVEL_2, "ACI-2"), code="T-2"))
        assert summarise_day(register, TODAY).uncovered_tests == ()

    def test_the_page_says_none_when_nothing_is_uncovered(self, register: Register) -> None:
        from slumpcone.report.daily import render_day

        register.people.save(tech(card(number="ACI-1"), code="T-1"))
        register.people.save(tech(card(Grade.LAB_LEVEL_2, "ACI-2"), code="T-2"))
        text = render_day(summarise_day(register, TODAY))
        assert "tests nobody may run" in text
        assert "breaking cylinders" not in text
