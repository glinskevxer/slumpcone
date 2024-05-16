from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.percent import Percent
from slumpcone.store.db import Database
from slumpcone.store.fresh_repo import FreshTestRepository
from slumpcone.store.migrations import migrate
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from slumpcone.units.temperature import Temperature

TAKEN = datetime(2024, 6, 12, 8, 5)


@pytest.fixture()
def repo() -> FreshTestRepository:
    database = Database.in_memory()
    migrate(database)
    return FreshTestRepository(database)


def slump(minutes: int = 0, retest: bool = False, ticket: str = "881204") -> FreshTest:
    return FreshTest(
        ticket,
        FreshTestKind.SLUMP,
        TAKEN + timedelta(minutes=minutes),
        slump=Quantity(4.5, "in"),
        discharged_before_sample=Quantity(3, "yd3"),
        technician="TECH-7",
        is_retest=retest,
        notes="off the chute",
    )


class CaseRoundTrip:
    def test_a_slump_test(self, repo: FreshTestRepository) -> None:
        repo.save(slump())
        assert repo.for_ticket("881204") == (slump(),)

    def test_an_air_test(self, repo: FreshTestRepository) -> None:
        test = FreshTest("881204", FreshTestKind.AIR_PRESSURE, TAKEN, air=Percent(6.2))
        repo.save(test)
        assert repo.for_ticket("881204")[0].air == Percent(6.2)

    def test_a_temperature_test(self, repo: FreshTestRepository) -> None:
        test = FreshTest(
            "881204", FreshTestKind.TEMPERATURE, TAKEN, temperature=Temperature(78, "F")
        )
        repo.save(test)
        loaded = repo.for_ticket("881204")[0]
        assert loaded.temperature is not None
        assert loaded.temperature.fahrenheit == pytest.approx(78.0)

    def test_a_unit_weight_test(self, repo: FreshTestRepository) -> None:
        test = FreshTest(
            "881204",
            FreshTestKind.UNIT_WEIGHT,
            TAKEN,
            unit_weight=MassPerVolume(142.6, "lb", "ft3"),
        )
        repo.save(test)
        loaded = repo.for_ticket("881204")[0]
        assert loaded.unit_weight is not None
        assert loaded.unit_weight.value == pytest.approx(142.6)

    def test_the_optional_fields_survive(self, repo: FreshTestRepository) -> None:
        repo.save(slump())
        loaded = repo.for_ticket("881204")[0]
        assert loaded.technician == "TECH-7"
        assert loaded.notes == "off the chute"
        assert loaded.discharged_before_sample == Quantity(3, "yd3")

    def test_a_bare_test_survives(self, repo: FreshTestRepository) -> None:
        test = FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4, "in"))
        repo.save(test)
        loaded = repo.for_ticket("881204")[0]
        assert loaded.technician is None
        assert loaded.discharged_before_sample is None


class CaseDuplicates:
    def test_the_same_test_twice_is_refused(self, repo: FreshTestRepository) -> None:
        repo.save(slump())
        with pytest.raises(ConflictError, match="881204"):
            repo.save(slump())

    def test_a_retest_at_the_same_moment_is_a_different_test(
        self, repo: FreshTestRepository
    ) -> None:
        repo.save(slump())
        repo.save(slump(retest=True))
        assert len(repo.for_ticket("881204")) == 2

    def test_save_all_rolls_back_on_a_duplicate(self, repo: FreshTestRepository) -> None:
        with pytest.raises(ConflictError):
            repo.save_all([slump(), slump(minutes=5), slump(minutes=5)])
        assert repo.count() == 0


class CaseQueries:
    def stock(self, repo: FreshTestRepository) -> None:
        repo.save_all(
            [
                slump(),
                slump(minutes=6, retest=True),
                FreshTest("881205", FreshTestKind.AIR_PRESSURE, TAKEN, air=Percent(6.0)),
            ]
        )

    def test_for_ticket_is_oldest_first(self, repo: FreshTestRepository) -> None:
        self.stock(repo)
        found = repo.for_ticket("881204")
        assert [t.is_retest for t in found] == [False, True]

    def test_for_ticket_on_an_untested_load(self, repo: FreshTestRepository) -> None:
        assert repo.for_ticket("881299") == ()

    def test_of_kind(self, repo: FreshTestRepository) -> None:
        self.stock(repo)
        found = repo.of_kind(FreshTestKind.SLUMP, date(2024, 6, 1), date(2024, 6, 30))
        assert len(found) == 2

    def test_between(self, repo: FreshTestRepository) -> None:
        self.stock(repo)
        assert len(repo.between(date(2024, 6, 12), date(2024, 6, 12))) == 3
        assert repo.between(date(2024, 7, 1), date(2024, 7, 31)) == ()

    def test_tickets_tested(self, repo: FreshTestRepository) -> None:
        self.stock(repo)
        assert repo.tickets_tested(date(2024, 6, 1), date(2024, 6, 30)) == ("881204", "881205")

    def test_count(self, repo: FreshTestRepository) -> None:
        self.stock(repo)
        assert repo.count() == 3

    def test_delete_for_ticket(self, repo: FreshTestRepository) -> None:
        self.stock(repo)
        assert repo.delete_for_ticket("881204") == 2
        assert repo.count() == 1

    def test_delete_names_what_is_missing(self, repo: FreshTestRepository) -> None:
        with pytest.raises(NotFoundError, match="881299"):
            repo.delete_for_ticket("881299")
