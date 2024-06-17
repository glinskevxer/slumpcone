from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.store.strength_repo import StrengthRepository
from slumpcone.strength.breaks import BreakResult, FractureType
from slumpcone.strength.specimen import (
    CureCondition,
    Specimen,
    SpecimenPurpose,
    SpecimenSize,
)
from slumpcone.units.quantity import Quantity

CAST = datetime(2024, 6, 12, 9, 20)


@pytest.fixture()
def repo() -> StrengthRepository:
    database = Database.in_memory()
    migrate(database)
    return StrengthRepository(database)


def open_set(repo: StrengthRepository, set_code: str = "S-4471", **overrides: object) -> str:
    fields: dict[str, object] = {
        "ticket_number": "881204",
        "project": "Route 9 shoulder",
        "size": SpecimenSize.CYL_6X12,
    }
    fields.update(overrides)
    return repo.open_set(set_code, "4000P-57", 1, CAST, **fields)  # type: ignore[arg-type]


def cylinder(code: str, set_code: str = "S-4471", **overrides: object) -> Specimen:
    fields: dict[str, object] = {
        "code": code,
        "set_code": set_code,
        "ticket_number": "881204",
        "cast_at": CAST,
        "size": SpecimenSize.CYL_6X12,
    }
    fields.update(overrides)
    return Specimen(**fields)  # type: ignore[arg-type]


def a_break(code: str, load: float = 141000.0, day: int = 28) -> BreakResult:
    return BreakResult(
        code,
        CAST + timedelta(days=day),
        float(day),
        Quantity(6.0, "in"),
        Quantity(6.0, "in"),
        Quantity(12.0, "in"),
        Quantity(load, "lbf"),
        FractureType.CONE,
        tested_by="TECH-7",
    )


class CaseSets:
    def test_open_a_set(self, repo: StrengthRepository) -> None:
        assert open_set(repo) == "S-4471"

    def test_the_same_set_twice_is_refused(self, repo: StrengthRepository) -> None:
        open_set(repo)
        with pytest.raises(ConflictError, match="S-4471"):
            open_set(repo)

    def test_delete_takes_everything_with_it(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        repo.save_break(a_break("C-A"))
        repo.delete_set("S-4471")
        assert repo.specimens_in("S-4471") == ()
        assert repo.breaks_in("S-4471") == ()

    def test_delete_names_what_is_missing(self, repo: StrengthRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete_set("S-4471")


class CaseSpecimens:
    def test_round_trip(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        loaded = repo.specimens_in("S-4471")
        assert [s.code for s in loaded] == ["C-A"]
        assert loaded[0].size is SpecimenSize.CYL_6X12
        assert loaded[0].cast_at == CAST

    def test_a_specimen_needs_its_set(self, repo: StrengthRepository) -> None:
        with pytest.raises(NotFoundError, match="S-4471"):
            repo.save_specimen(cylinder("C-A"))

    def test_the_same_specimen_twice_is_refused(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        with pytest.raises(ConflictError, match="C-A"):
            repo.save_specimen(cylinder("C-A"))

    def test_the_cure_and_purpose_survive(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(
            cylinder("C-A", cure=CureCondition.FIELD, purpose=SpecimenPurpose.FORM_REMOVAL)
        )
        loaded = repo.specimens_in("S-4471")[0]
        assert loaded.cure is CureCondition.FIELD
        assert loaded.purpose is SpecimenPurpose.FORM_REMOVAL


class CaseBreaks:
    def test_round_trip(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        repo.save_break(a_break("C-A"))
        loaded = repo.breaks_in("S-4471")
        assert loaded[0].specimen_code == "C-A"
        assert loaded[0].tested_by == "TECH-7"
        assert loaded[0].strength.value == pytest.approx(4987.0, abs=10.0)

    def test_a_break_needs_its_specimen(self, repo: StrengthRepository) -> None:
        with pytest.raises(NotFoundError, match="C-A"):
            repo.save_break(a_break("C-A"))

    def test_a_cylinder_breaks_only_once(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        repo.save_break(a_break("C-A"))
        with pytest.raises(ConflictError, match="C-A"):
            repo.save_break(a_break("C-A"))


class CasePending:
    def test_a_cylinder_past_its_age_is_pending(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        assert [s.code for s in repo.pending_breaks(date(2024, 7, 11))] == ["C-A"]

    def test_a_cylinder_not_yet_due_is_not(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        assert repo.pending_breaks(date(2024, 6, 20)) == ()

    def test_a_broken_cylinder_drops_off(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A"))
        repo.save_break(a_break("C-A"))
        assert repo.pending_breaks(date(2024, 7, 11)) == ()

    def test_a_seven_day_cylinder_comes_due_sooner(self, repo: StrengthRepository) -> None:
        open_set(repo)
        repo.save_specimen(cylinder("C-A", age_days=7))
        assert [s.code for s in repo.pending_breaks(date(2024, 6, 20))] == ["C-A"]


class CaseStrengthTests:
    def stock(self, repo: StrengthRepository) -> None:
        open_set(repo)
        for letter, load in (("A", 141000.0), ("B", 143000.0)):
            repo.save_specimen(cylinder(f"C-{letter}"))
            repo.save_break(a_break(f"C-{letter}", load))

    def test_a_set_adds_up_to_a_test(self, repo: StrengthRepository) -> None:
        self.stock(repo)
        built = repo.strength_test("S-4471")
        assert built.mix_code == "4000P-57"
        assert built.ticket_number == "881204"
        assert built.project == "Route 9 shoulder"
        assert built.is_complete
        assert built.average.value == pytest.approx(5022.0, abs=10.0)

    def test_a_set_with_no_breaks_has_no_test(self, repo: StrengthRepository) -> None:
        open_set(repo)
        with pytest.raises(NotFoundError, match="break for set"):
            repo.strength_test("S-4471")

    def test_an_unknown_set_has_no_test(self, repo: StrengthRepository) -> None:
        with pytest.raises(NotFoundError, match="specimen set"):
            repo.strength_test("S-9999")

    def test_tests_for_mix(self, repo: StrengthRepository) -> None:
        self.stock(repo)
        open_set(repo, "S-4472")
        assert [t.set_code for t in repo.tests_for_mix("4000p 57")] == ["S-4471"]

    def test_tests_for_project(self, repo: StrengthRepository) -> None:
        self.stock(repo)
        assert [t.set_code for t in repo.tests_for_project("Route 9 shoulder")] == ["S-4471"]
        assert repo.tests_for_project("Mill Street kerb") == ()
