from __future__ import annotations

from datetime import date, datetime, time

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.errors import NotFoundError
from slumpcone.project.order import Order, OrderStatus
from slumpcone.store.batch_repo import BatchRepository
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.store.order_repo import OrderRepository
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

DAY = date(2024, 6, 12)


@pytest.fixture()
def database() -> Database:
    db = Database.in_memory()
    migrate(db)
    return db


@pytest.fixture()
def repo(database: Database) -> OrderRepository:
    return OrderRepository(database)


def order(number: str = "ORD-9912", **overrides: object) -> Order:
    fields: dict[str, object] = {
        "number": number,
        "project_code": "P-2024-118",
        "class_code": "SLAB",
        "volume": Quantity(60, "yd3"),
        "placement_date": DAY,
        "mix_code": "4000P-57",
        "start_time": time(6, 30),
        "rate": Quantity(24, "yd3"),
        "placement": "Route 9 shoulder",
        "notes": "night pour",
    }
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


def write_ticket(database: Database, number: str, volume: float) -> None:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(volume, "yd3"), DAY)
    BatchRepository(database).save(
        BatchTicket.from_plan(
            planned,
            number,
            datetime(2024, 6, 12, 7, 42),
            project="Route 9 shoulder",
        )
    )


class CaseRoundTrip:
    def test_everything_comes_back(self, repo: OrderRepository) -> None:
        repo.save(order())
        loaded = repo.get("ord 9912")
        assert loaded.project_code == "P-2024-118"
        assert loaded.volume == Quantity(60, "yd3")
        assert loaded.start_time == time(6, 30)
        assert loaded.rate == Quantity(24, "yd3")
        assert loaded.placement == "Route 9 shoulder"
        assert loaded.notes == "night pour"

    def test_a_bare_order_comes_back(self, repo: OrderRepository) -> None:
        repo.save(order(mix_code=None, start_time=None, rate=None, placement=None, notes=""))
        loaded = repo.get("ORD-9912")
        assert loaded.mix_code is None
        assert loaded.start_time is None
        assert loaded.rate is None

    def test_save_is_an_upsert(self, repo: OrderRepository) -> None:
        repo.save(order())
        repo.save(order(status=OrderStatus.COMPLETE))
        assert repo.get("ORD-9912").status is OrderStatus.COMPLETE

    def test_an_unknown_order_is_named(self, repo: OrderRepository) -> None:
        with pytest.raises(NotFoundError, match="ORD-1"):
            repo.get("ORD-1")

    def test_delete(self, repo: OrderRepository) -> None:
        repo.save(order())
        repo.delete("ORD-9912")
        with pytest.raises(NotFoundError):
            repo.get("ORD-9912")

    def test_delete_names_what_is_missing(self, repo: OrderRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("ORD-1")


class CaseQueries:
    def stock(self, repo: OrderRepository) -> None:
        repo.save(order("ORD-9912"))
        repo.save(order("ORD-9913", status=OrderStatus.CANCELLED))
        repo.save(order("ORD-9920", placement_date=date(2024, 6, 13)))

    def test_for_project(self, repo: OrderRepository) -> None:
        self.stock(repo)
        assert [o.number for o in repo.for_project("p 2024 118")] == [
            "ORD-9912",
            "ORD-9913",
            "ORD-9920",
        ]

    def test_on_date(self, repo: OrderRepository) -> None:
        self.stock(repo)
        assert [o.number for o in repo.on_date(DAY)] == ["ORD-9912", "ORD-9913"]

    def test_open_orders_drops_the_cancelled_one(self, repo: OrderRepository) -> None:
        self.stock(repo)
        assert [o.number for o in repo.open_orders(DAY)] == ["ORD-9912"]


class CaseProgress:
    def test_no_tickets_yet(self, repo: OrderRepository) -> None:
        repo.save(order())
        progress = repo.progress("ORD-9912")
        assert progress.delivered.is_zero()
        assert progress.is_short

    def test_tickets_on_the_placement_count(
        self, repo: OrderRepository, database: Database
    ) -> None:
        repo.save(order())
        write_ticket(database, "881204", 9.0)
        write_ticket(database, "881205", 9.0)
        progress = repo.progress("ORD-9912")
        assert progress.load_count == 2
        assert progress.delivered == Quantity(18, "yd3")

    def test_an_order_with_no_placement_matches_nothing(
        self, repo: OrderRepository, database: Database
    ) -> None:
        repo.save(order(placement=None))
        write_ticket(database, "881204", 9.0)
        assert repo.progress("ORD-9912").load_count == 0

    def test_progress_from_a_named_list(
        self, repo: OrderRepository, database: Database
    ) -> None:
        repo.save(order())
        write_ticket(database, "881204", 9.0)
        write_ticket(database, "881205", 7.0)
        progress = repo.progress_from_tickets("ORD-9912", ["881204"])
        assert progress.delivered == Quantity(9, "yd3")
