from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.delivery.record import Delivery
from slumpcone.delivery.truck import Truck
from slumpcone.delivery.water import RequestedBy, WaterAddition
from slumpcone.errors import NotFoundError
from slumpcone.store.db import Database
from slumpcone.store.delivery_repo import DeliveryRepository
from slumpcone.store.migrations import migrate
from slumpcone.units.quantity import Quantity

BATCHED = datetime(2024, 6, 12, 7, 42)


@pytest.fixture()
def repo() -> DeliveryRepository:
    database = Database.in_memory()
    migrate(database)
    return DeliveryRepository(database)


def at(minutes: int) -> datetime:
    return BATCHED + timedelta(minutes=minutes)


def truck(code: str = "TR-114") -> Truck:
    return Truck(
        code,
        Quantity(11.0, "yd3"),
        fleet="Northmoor",
        last_uniformity_test=date(2024, 2, 1),
    )


def delivery(ticket: str = "881204", **overrides: object) -> Delivery:
    fields: dict[str, object] = {
        "ticket_number": ticket,
        "truck_code": "TR-114",
        "batched_at": BATCHED,
        "left_plant_at": at(6),
        "arrived_at": at(28),
        "discharge_started_at": at(35),
        "discharge_finished_at": at(52),
        "revolutions_on_arrival": 140,
        "revolutions_at_discharge": 210,
        "returned_volume": Quantity(0.5, "yd3"),
        "notes": "held at the gate",
    }
    fields.update(overrides)
    return Delivery(**fields)  # type: ignore[arg-type]


class CaseTrucks:
    def test_round_trip(self, repo: DeliveryRepository) -> None:
        repo.save_truck(truck())
        assert repo.truck("tr 114") == truck()

    def test_save_is_an_upsert(self, repo: DeliveryRepository) -> None:
        repo.save_truck(truck())
        repo.save_truck(Truck("TR-114", Quantity(10.0, "yd3")))
        loaded = repo.truck("TR-114")
        assert loaded.drum_volume == Quantity(10.0, "yd3")
        assert loaded.fleet is None

    def test_an_unknown_truck_is_named(self, repo: DeliveryRepository) -> None:
        with pytest.raises(NotFoundError, match="TR-999"):
            repo.truck("TR-999")

    def test_trucks_are_sorted(self, repo: DeliveryRepository) -> None:
        repo.save_truck(truck("TR-114"))
        repo.save_truck(truck("TR-102"))
        assert [t.code for t in repo.trucks()] == ["TR-102", "TR-114"]


class CaseDeliveries:
    def test_round_trip(self, repo: DeliveryRepository) -> None:
        repo.save(delivery())
        loaded = repo.get("881204")
        assert loaded.truck_code == "TR-114"
        assert loaded.arrived_at == at(28)
        assert loaded.revolutions_at_discharge == 210
        assert loaded.returned_volume == Quantity(0.5, "yd3")
        assert loaded.notes == "held at the gate"

    def test_an_unfinished_load_round_trips(self, repo: DeliveryRepository) -> None:
        repo.save(
            delivery(
                arrived_at=None,
                discharge_started_at=None,
                discharge_finished_at=None,
                revolutions_at_discharge=None,
                returned_volume=None,
            )
        )
        loaded = repo.get("881204")
        assert not loaded.is_complete
        assert loaded.arrived_at is None
        assert loaded.returned_volume is None

    def test_the_row_grows_as_stages_come_in(self, repo: DeliveryRepository) -> None:
        repo.save(
            delivery(
                arrived_at=None,
                discharge_started_at=None,
                discharge_finished_at=None,
                revolutions_at_discharge=None,
            )
        )
        repo.save(delivery())
        loaded = repo.get("881204")
        assert loaded.is_complete
        assert loaded.discharge_finished_at == at(52)

    def test_an_unknown_delivery_is_named(self, repo: DeliveryRepository) -> None:
        with pytest.raises(NotFoundError, match="881299"):
            repo.get("881299")


class CaseWaterAdditions:
    def additions(self) -> tuple[WaterAddition, ...]:
        return (
            WaterAddition(
                "881204",
                at(30),
                Quantity(5, "gal"),
                RequestedBy.PURCHASER,
                revolutions_after=35,
                discharged_before=Quantity(0, "yd3"),
            ),
        )

    def test_round_trip(self, repo: DeliveryRepository) -> None:
        repo.save(delivery(water_additions=self.additions()))
        loaded = repo.get("881204")
        assert len(loaded.water_additions) == 1
        assert loaded.water_additions[0].requested_by is RequestedBy.PURCHASER
        assert loaded.water_additions[0].revolutions_after == 35

    def test_saving_again_replaces_them(self, repo: DeliveryRepository) -> None:
        repo.save(delivery(water_additions=self.additions()))
        repo.save(delivery())
        assert repo.get("881204").water_additions == ()

    def test_delete_takes_them_with_it(self, repo: DeliveryRepository) -> None:
        repo.save(delivery(water_additions=self.additions()))
        repo.delete("881204")
        assert repo._db.scalar("SELECT count(*) FROM water_addition") == 0

    def test_delete_names_what_is_missing(self, repo: DeliveryRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("881299")


class CaseQueries:
    def stock(self, repo: DeliveryRepository) -> None:
        repo.save(delivery("881204"))
        repo.save(
            delivery(
                "881205",
                truck_code="TR-102",
                discharge_finished_at=None,
                revolutions_at_discharge=None,
            )
        )

    def test_between(self, repo: DeliveryRepository) -> None:
        self.stock(repo)
        found = repo.between(date(2024, 6, 12), date(2024, 6, 12))
        assert [d.ticket_number for d in found] == ["881204", "881205"]

    def test_between_excludes_other_days(self, repo: DeliveryRepository) -> None:
        self.stock(repo)
        assert repo.between(date(2024, 7, 1), date(2024, 7, 31)) == ()

    def test_for_truck(self, repo: DeliveryRepository) -> None:
        self.stock(repo)
        found = repo.for_truck("tr 102", date(2024, 6, 1), date(2024, 6, 30))
        assert [d.ticket_number for d in found] == ["881205"]

    def test_unfinished(self, repo: DeliveryRepository) -> None:
        self.stock(repo)
        found = repo.unfinished(date(2024, 6, 1), date(2024, 6, 30))
        assert [d.ticket_number for d in found] == ["881205"]
