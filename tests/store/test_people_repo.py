from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import NotFoundError
from slumpcone.people.certification import Certification, Grade, Technician, TestKind
from slumpcone.register import Register

TODAY = date(2024, 6, 12)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


def card(
    grade: Grade = Grade.FIELD_GRADE_I,
    number: str = "ACI-1001",
    *,
    expires: date = date(2027, 6, 1),
) -> Certification:
    return Certification(grade, number, date(2022, 6, 1), expires)


def tech(*cards: Certification, code: str = "T-1") -> Technician:
    return Technician(code, "R. Okafor", cards, "Ashfield testing")


class CaseRoundTrip:
    def test_a_technician_comes_back_whole(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert register.people.get("T-1") == tech(card())

    def test_the_employer_survives(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert register.people.get("T-1").employer == "Ashfield testing"

    def test_somebody_with_no_cards(self, register: Register) -> None:
        register.people.save(tech())
        assert register.people.get("T-1").certifications == ()

    def test_two_cards_both_come_back(self, register: Register) -> None:
        register.people.save(tech(card(), card(Grade.LAB_LEVEL_2, "ACI-2")))
        assert len(register.people.get("T-1").certifications) == 2

    def test_the_cards_come_back_soonest_expiry_first(self, register: Register) -> None:
        register.people.save(
            tech(
                card(number="ACI-1", expires=date(2027, 1, 1)),
                card(Grade.LAB_LEVEL_1, "ACI-2", expires=date(2025, 1, 1)),
            )
        )
        numbers = [one.number for one in register.people.get("T-1").certifications]
        assert numbers == ["ACI-2", "ACI-1"]

    def test_saving_again_replaces_the_cards(self, register: Register) -> None:
        register.people.save(tech(card(), card(Grade.LAB_LEVEL_2, "ACI-2")))
        register.people.save(tech(card()))
        assert len(register.people.get("T-1").certifications) == 1

    def test_an_unknown_technician(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.people.get("T-1")

    def test_the_code_is_normalised(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert register.people.get(" t-1 ").code == "T-1"

    def test_the_listing_is_in_code_order(self, register: Register) -> None:
        register.people.save(tech(card(number="ACI-9"), code="T-9"))
        register.people.save(tech(card(number="ACI-1"), code="T-1"))
        assert [one.code for one in register.people.all()] == ["T-1", "T-9"]

    def test_forgetting_one(self, register: Register) -> None:
        register.people.save(tech(card()))
        register.people.forget("T-1")
        assert register.people.all() == ()

    def test_forgetting_takes_the_cards_with_it(self, register: Register) -> None:
        register.people.save(tech(card()))
        register.people.forget("T-1")
        assert register.database.query("SELECT * FROM certification") == []

    def test_forgetting_somebody_who_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.people.forget("T-1")


class CaseCardLookup:
    def test_whose_card_it_is(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert register.people.holder_of("ACI-1001").code == "T-1"

    def test_a_card_nobody_holds(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.people.holder_of("ACI-9999")

    def test_the_number_is_normalised(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert register.people.holder_of(" aci-1001 ").code == "T-1"


class CaseExpiry:
    def stocked(self, register: Register) -> None:
        register.people.save(tech(card(number="ACI-1", expires=date(2023, 1, 1)), code="T-1"))
        register.people.save(tech(card(number="ACI-2", expires=date(2024, 7, 1)), code="T-2"))
        register.people.save(tech(card(number="ACI-3", expires=date(2027, 6, 1)), code="T-3"))

    def test_the_lapsed_list(self, register: Register) -> None:
        self.stocked(register)
        lapsed = register.people.lapsed(TODAY)
        assert [number for _, one in lapsed for number in [one.number]] == ["ACI-1"]

    def test_the_lapsed_list_names_the_holder(self, register: Register) -> None:
        self.stocked(register)
        assert register.people.lapsed(TODAY)[0][0] == "T-1"

    def test_the_expiring_list(self, register: Register) -> None:
        self.stocked(register)
        found = register.people.expiring(TODAY, days=60)
        assert [one.number for _, one in found] == ["ACI-2"]

    def test_the_expiring_list_leaves_out_the_lapsed(self, register: Register) -> None:
        self.stocked(register)
        found = register.people.expiring(TODAY, days=3650)
        assert "ACI-1" not in [one.number for _, one in found]

    def test_a_card_expiring_today_is_still_reported_as_expiring(
        self, register: Register
    ) -> None:
        register.people.save(tech(card(number="ACI-1", expires=TODAY)))
        assert [one.number for _, one in register.people.expiring(TODAY, days=1)] == ["ACI-1"]

    def test_a_card_expiring_today_has_not_lapsed(self, register: Register) -> None:
        register.people.save(tech(card(number="ACI-1", expires=TODAY)))
        assert register.people.lapsed(TODAY) == ()

    def test_a_longer_window_finds_more(self, register: Register) -> None:
        self.stocked(register)
        short = register.people.expiring(TODAY, days=7)
        long = register.people.expiring(TODAY, days=3650)
        assert len(long) > len(short)

    def test_nothing_on_file(self, register: Register) -> None:
        assert register.people.lapsed(TODAY) == ()
        assert register.people.expiring(TODAY) == ()


class CaseRoster:
    def test_who_may_run_a_field_test(self, register: Register) -> None:
        register.people.save(tech(card(), code="T-1"))
        register.people.save(tech(card(Grade.STRENGTH_TESTING, "ACI-2"), code="T-2"))
        found = register.people.may_run(TestKind.SLUMP, TODAY)
        assert [one.code for one in found] == ["T-1"]

    def test_a_lapsed_card_does_not_count(self, register: Register) -> None:
        register.people.save(tech(card(expires=date(2023, 1, 1))))
        assert register.people.may_run(TestKind.SLUMP, TODAY) == ()

    def test_the_gaps(self, register: Register) -> None:
        register.people.save(tech(card()))
        gaps = register.people.gaps(TODAY)
        assert TestKind.BREAKING_CYLINDERS in gaps
        assert TestKind.SLUMP not in gaps

    def test_asking_about_a_short_list(self, register: Register) -> None:
        register.people.save(tech(card()))
        assert register.people.gaps(TODAY, [TestKind.SLUMP]) == ()

    def test_an_empty_register_has_every_gap(self, register: Register) -> None:
        assert len(register.people.gaps(TODAY)) == len(list(TestKind))


def test_the_health_check_counts_technicians(register: Register) -> None:
    register.people.save(tech(card()))
    assert register.health().counts["technician"] == 1
