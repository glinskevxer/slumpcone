from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.store.batch_repo import BatchRepository
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

DAY = date(2024, 6, 12)


@pytest.fixture()
def repo() -> BatchRepository:
    database = Database.in_memory()
    migrate(database)
    return BatchRepository(database)


def ticket(number: str = "881204", hour: int = 7, **details: object) -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
    fields: dict[str, object] = {
        "truck_code": "TR-114",
        "purchaser": "Ashfield Paving",
        "project": "Route 9 shoulder",
        "cumulative_volume": Quantity(27, "yd3"),
        "revolution_counter": 12,
        "water_held_back": Quantity(90, "lb"),
        "notes": "hold water for the finisher",
    }
    fields.update(details)
    return BatchTicket.from_plan(
        planned,
        number,
        datetime(2024, 6, 12, hour, 42),
        {"CEM-I": Quantity(4235, "lb")},
        {"AD-AE": Quantity(61.0, "floz")},
        **fields,
    )


class CaseRoundTrip:
    def test_the_header_comes_back(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        loaded = repo.get("881204")
        assert loaded.plant_code == "PL-1"
        assert loaded.mix_code == "4000P-57"
        assert loaded.truck_code == "TR-114"
        assert loaded.project == "Route 9 shoulder"
        assert loaded.batched_at == datetime(2024, 6, 12, 7, 42)
        assert loaded.volume == Quantity(9, "yd3")

    def test_the_optional_fields_come_back(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        loaded = repo.get("881204")
        assert loaded.cumulative_volume == Quantity(27, "yd3")
        assert loaded.revolution_counter == 12
        assert loaded.water_held_back == Quantity(90, "lb")
        assert loaded.notes == "hold water for the finisher"

    def test_a_bare_ticket_comes_back(self, repo: BatchRepository) -> None:
        repo.save(
            ticket(
                truck_code=None,
                purchaser=None,
                project=None,
                cumulative_volume=None,
                revolution_counter=None,
                water_held_back=None,
                notes="",
            )
        )
        loaded = repo.get("881204")
        assert loaded.truck_code is None
        assert loaded.cumulative_volume is None
        assert not loaded.is_complete

    def test_the_lines_come_back_in_order(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        loaded = repo.get("881204")
        codes = [line.material_code for line in loaded.lines]
        assert codes == ["CEM-I", "SCM-F", "CA-57", "FA-1", "W-1"]

    def test_the_recorded_weight_comes_back(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        assert repo.get("881204").line("CEM-I").actual == Quantity(4235, "lb")

    def test_the_doses_come_back(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        loaded = repo.get("881204")
        assert loaded.admixtures[0].dispensed.value == pytest.approx(61.0)

    def test_the_verdicts_survive_the_round_trip(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        assert repo.get("881204").out_of_tolerance == ()


class CaseAppendOnly:
    def test_a_second_save_is_refused(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        with pytest.raises(ConflictError, match="881204"):
            repo.save(ticket())

    def test_get_names_what_is_missing(self, repo: BatchRepository) -> None:
        with pytest.raises(NotFoundError, match="881204"):
            repo.get("881204")

    def test_delete_takes_the_lines_with_it(self, repo: BatchRepository) -> None:
        repo.save(ticket())
        repo.delete("881204")
        assert repo.count() == 0
        assert repo._db.scalar("SELECT count(*) FROM batch_ticket_line") == 0
        assert repo._db.scalar("SELECT count(*) FROM batch_ticket_admixture") == 0

    def test_delete_names_what_is_missing(self, repo: BatchRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("881204")


class CaseQueries:
    def stock(self, repo: BatchRepository) -> None:
        repo.save(ticket("881204", hour=7))
        repo.save(ticket("881205", hour=9, project="Mill Street kerb"))

    def test_between_is_oldest_first(self, repo: BatchRepository) -> None:
        self.stock(repo)
        found = repo.between(date(2024, 6, 1), date(2024, 6, 30))
        assert [t.number for t in found] == ["881204", "881205"]

    def test_between_excludes_other_days(self, repo: BatchRepository) -> None:
        self.stock(repo)
        assert repo.between(date(2024, 7, 1), date(2024, 7, 31)) == ()

    def test_between_includes_the_last_day(self, repo: BatchRepository) -> None:
        self.stock(repo)
        assert len(repo.between(date(2024, 6, 12), date(2024, 6, 12))) == 2

    def test_for_plant(self, repo: BatchRepository) -> None:
        self.stock(repo)
        assert len(repo.for_plant("pl 1", date(2024, 6, 1), date(2024, 6, 30))) == 2
        assert repo.for_plant("PL-9", date(2024, 6, 1), date(2024, 6, 30)) == ()

    def test_for_mix(self, repo: BatchRepository) -> None:
        self.stock(repo)
        assert len(repo.for_mix("4000p 57")) == 2

    def test_for_project(self, repo: BatchRepository) -> None:
        self.stock(repo)
        assert [t.number for t in repo.for_project("Mill Street kerb")] == ["881205"]

    def test_count(self, repo: BatchRepository) -> None:
        assert repo.count() == 0
        self.stock(repo)
        assert repo.count() == 2
