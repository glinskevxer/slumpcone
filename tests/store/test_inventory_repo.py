from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.percent import Percent
from slumpcone.plant.inventory import Movement, MovementKind
from slumpcone.plant.receipt import Receipt
from slumpcone.store.db import Database
from slumpcone.store.inventory_repo import InventoryRepository
from slumpcone.store.migrations import migrate
from slumpcone.units.quantity import Quantity

RECEIVED = datetime(2024, 6, 11, 5, 40)


@pytest.fixture()
def repo() -> InventoryRepository:
    database = Database.in_memory()
    migrate(database)
    return InventoryRepository(database)


def receipt(reference: str = "RCV-2211", **overrides: object) -> Receipt:
    fields: dict[str, object] = {
        "reference": reference,
        "plant_code": "PL-1",
        "silo_code": "SI-1",
        "material_code": "CEM-I",
        "received_at": RECEIVED,
        "quantity": Quantity(48000, "lb"),
        "supplier": "Ashfield Cement",
        "supplier_ticket": "AC-77120",
        "certificate_reference": "MC-2024-0412",
        "moisture": Percent(0.0),
        "notes": "silo one",
    }
    fields.update(overrides)
    return Receipt(**fields)  # type: ignore[arg-type]


def movement(
    kind: MovementKind = MovementKind.DRAWDOWN, pounds: float = 5000.0, hours: int = 4
) -> Movement:
    return Movement(
        "PL-1",
        "SI-1",
        "CEM-I",
        RECEIVED + timedelta(hours=hours),
        kind,
        Quantity(pounds, "lb"),
        reference="881204",
    )


class CaseReceipts:
    def test_round_trip(self, repo: InventoryRepository) -> None:
        repo.save_receipt(receipt())
        assert repo.receipt("rcv 2211") == receipt()

    def test_a_bare_receipt_round_trips(self, repo: InventoryRepository) -> None:
        repo.save_receipt(
            receipt(
                supplier=None,
                supplier_ticket=None,
                certificate_reference=None,
                moisture=None,
                notes="",
            )
        )
        loaded = repo.receipt("RCV-2211")
        assert loaded.supplier is None
        assert loaded.moisture is None
        assert not loaded.has_paper

    def test_a_duplicate_reference_is_refused(self, repo: InventoryRepository) -> None:
        repo.save_receipt(receipt())
        with pytest.raises(ConflictError, match="RCV-2211"):
            repo.save_receipt(receipt())

    def test_an_unknown_receipt_is_named(self, repo: InventoryRepository) -> None:
        with pytest.raises(NotFoundError, match="RCV-9"):
            repo.receipt("RCV-9")

    def test_receipts_between(self, repo: InventoryRepository) -> None:
        repo.save_receipt(receipt("RCV-2211"))
        repo.save_receipt(receipt("RCV-2212", received_at=datetime(2024, 6, 13, 6, 0)))
        found = repo.receipts_between("pl 1", date(2024, 6, 1), date(2024, 6, 12))
        assert [r.reference for r in found] == ["RCV-2211"]

    def test_receipts_of_a_material(self, repo: InventoryRepository) -> None:
        repo.save_receipt(receipt("RCV-2211"))
        repo.save_receipt(receipt("RCV-2212", material_code="SCM-F", silo_code="SI-2"))
        assert [r.reference for r in repo.receipts_of("CEM-I")] == ["RCV-2211"]


class CaseMovements:
    def test_record_and_read_back(self, repo: InventoryRepository) -> None:
        repo.record(movement(MovementKind.RECEIPT, 48000.0, 0))
        ledger = repo.ledger("PL-1")
        assert len(ledger) == 1
        assert ledger.balance("SI-1") == Quantity(48000, "lb")

    def test_a_drawdown_comes_back_signed(self, repo: InventoryRepository) -> None:
        repo.record_all([movement(MovementKind.RECEIPT, 48000.0, 0), movement()])
        assert repo.balance("PL-1", "SI-1") == Quantity(43000, "lb")

    def test_a_negative_adjustment_survives_the_round_trip(
        self, repo: InventoryRepository
    ) -> None:
        repo.record(movement(MovementKind.RECEIPT, 48000.0, 0))
        repo.record(
            Movement(
                "PL-1",
                "SI-1",
                "CEM-I",
                RECEIVED + timedelta(hours=8),
                MovementKind.ADJUSTMENT,
                Quantity(-2000, "lb"),
            )
        )
        assert repo.balance("PL-1", "SI-1") == Quantity(46000, "lb")

    def test_another_plant_has_its_own_ledger(self, repo: InventoryRepository) -> None:
        repo.record(movement(MovementKind.RECEIPT, 48000.0, 0))
        assert len(repo.ledger("PL-2")) == 0

    def test_movements_between(self, repo: InventoryRepository) -> None:
        repo.record_all([movement(MovementKind.RECEIPT, 48000.0, 0), movement(hours=48)])
        found = repo.movements_between("PL-1", date(2024, 6, 11), date(2024, 6, 11))
        assert len(found) == 1

    def test_record_all_rolls_back_on_a_failure(self, repo: InventoryRepository) -> None:
        with pytest.raises(Exception):  # noqa: B017, PT011
            repo.record_all([movement(), movement(pounds=float("nan"))])
        assert len(repo.ledger("PL-1")) == 0


class CasePosting:
    def test_a_receipt_produces_its_ledger_line(self, repo: InventoryRepository) -> None:
        line = repo.receipt_movement(receipt())
        assert line.kind is MovementKind.RECEIPT
        assert line.reference == "RCV-2211"
        assert line.quantity == Quantity(48000, "lb")

    def test_posting_writes_both(self, repo: InventoryRepository) -> None:
        repo.post_receipt(receipt())
        assert repo.receipt("RCV-2211").quantity == Quantity(48000, "lb")
        assert repo.balance("PL-1", "SI-1") == Quantity(48000, "lb")

    def test_a_duplicate_post_leaves_no_movement(self, repo: InventoryRepository) -> None:
        repo.post_receipt(receipt())
        with pytest.raises(ConflictError):
            repo.post_receipt(receipt())
        assert len(repo.ledger("PL-1")) == 1
