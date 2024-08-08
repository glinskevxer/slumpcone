from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.plant.inventory import InventoryLedger, Movement, MovementKind
from slumpcone.units.quantity import Quantity

START = datetime(2024, 6, 1, 6, 0)


def at(hours: int) -> datetime:
    return START + timedelta(hours=hours)


def movement(
    kind: MovementKind = MovementKind.RECEIPT,
    pounds: float = 48000.0,
    hours: int = 0,
    silo: str = "SI-1",
    **overrides: object,
) -> Movement:
    fields: dict[str, object] = {
        "plant_code": "PL-1",
        "silo_code": silo,
        "material_code": "CEM-I",
        "at": at(hours),
        "kind": kind,
        "quantity": Quantity(pounds, "lb"),
    }
    fields.update(overrides)
    return Movement(**fields)  # type: ignore[arg-type]


class CaseKind:
    def test_parse(self) -> None:
        assert MovementKind.parse("receipt") is MovementKind.RECEIPT
        assert MovementKind.parse("TRANSFER-OUT") is MovementKind.TRANSFER_OUT

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="movement kind"):
            MovementKind.parse("evaporation")

    def test_direction(self) -> None:
        assert MovementKind.RECEIPT.adds
        assert MovementKind.TRANSFER_IN.adds
        assert MovementKind.DRAWDOWN.removes
        assert MovementKind.WASTE.removes
        assert not MovementKind.ADJUSTMENT.adds
        assert not MovementKind.ADJUSTMENT.removes

    def test_only_an_adjustment_carries_its_own_sign(self) -> None:
        assert MovementKind.ADJUSTMENT.is_signed
        assert not MovementKind.RECEIPT.is_signed


class CaseMovement:
    def test_codes_are_normalised(self) -> None:
        built = movement(silo_code=" si 1 ", reference="rcv 2211")
        assert built.silo_code == "SI-1"
        assert built.reference == "RCV-2211"

    def test_the_quantity_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="movement quantity is a mass"):
            movement(quantity=Quantity(1, "yd3"))

    def test_a_negative_receipt_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="use an adjustment"):
            movement(quantity=Quantity(-1, "lb"))

    def test_a_negative_adjustment_is_allowed(self) -> None:
        entry = movement(MovementKind.ADJUSTMENT, -8000.0)
        assert entry.signed.value == pytest.approx(-8000.0)

    def test_the_sign_follows_the_kind(self) -> None:
        assert movement(MovementKind.RECEIPT).signed.value == pytest.approx(48000.0)
        assert movement(MovementKind.DRAWDOWN, 5000.0).signed.value == pytest.approx(-5000.0)

    def test_describe(self) -> None:
        line = movement(reference="RCV-2211").describe()
        assert "2024-06-01" in line
        assert "SI-1" in line
        assert "receipt" in line
        assert "RCV-2211" in line


class CaseLedger:
    def stocked(self) -> InventoryLedger:
        return InventoryLedger(
            [
                movement(MovementKind.RECEIPT, 48000.0, 0),
                movement(MovementKind.DRAWDOWN, 5000.0, 4),
                movement(MovementKind.DRAWDOWN, 4000.0, 8),
            ]
        )

    def test_length_and_iteration(self) -> None:
        ledger = self.stocked()
        assert len(ledger) == 3
        assert [entry.kind for entry in ledger][0] is MovementKind.RECEIPT

    def test_it_keeps_time_order(self) -> None:
        ledger = InventoryLedger(
            [movement(MovementKind.DRAWDOWN, 5000.0, 4), movement(hours=0)]
        )
        assert [entry.at for entry in ledger] == [at(0), at(4)]

    def test_record_keeps_the_order(self) -> None:
        ledger = self.stocked()
        ledger.record(movement(MovementKind.RECEIPT, 12000.0, 2))
        assert [entry.at for entry in ledger][1] == at(2)

    def test_balance(self) -> None:
        assert self.stocked().balance("SI-1") == Quantity(39000, "lb")

    def test_balance_at_a_moment(self) -> None:
        assert self.stocked().balance("SI-1", until=at(5)) == Quantity(43000, "lb")

    def test_balance_of_an_unknown_vessel_is_nothing(self) -> None:
        assert self.stocked().balance("SI-9").is_zero()

    def test_usage_over_a_window(self) -> None:
        assert self.stocked().usage("SI-1", at(0), at(24)) == Quantity(9000, "lb")

    def test_usage_excludes_receipts(self) -> None:
        assert self.stocked().usage("SI-1", at(5), at(24)) == Quantity(4000, "lb")

    def test_movements_for_another_vessel(self) -> None:
        ledger = self.stocked()
        ledger.record(movement(silo="SI-2"))
        assert len(ledger.movements_for("SI-1")) == 3
        assert ledger.silo_codes() == ("SI-1", "SI-2")


class CaseReconciliation:
    def stocked(self) -> InventoryLedger:
        return InventoryLedger(
            [
                movement(MovementKind.RECEIPT, 48000.0, 0),
                movement(MovementKind.DRAWDOWN, 9000.0, 4),
            ]
        )

    def test_a_short_reading_records_a_negative_adjustment(self) -> None:
        ledger = self.stocked()
        entry = ledger.reconcile("SI-1", Quantity(37000, "lb"), at(8))
        assert entry is not None
        assert entry.kind is MovementKind.ADJUSTMENT
        assert entry.signed.value == pytest.approx(-2000.0)
        assert ledger.balance("SI-1") == Quantity(37000, "lb")

    def test_a_long_reading_records_a_positive_one(self) -> None:
        ledger = self.stocked()
        entry = ledger.reconcile("SI-1", Quantity(41000, "lb"), at(8))
        assert entry is not None
        assert entry.signed.value == pytest.approx(2000.0)

    def test_agreement_records_nothing(self) -> None:
        ledger = self.stocked()
        assert ledger.reconcile("SI-1", Quantity(39000, "lb"), at(8)) is None
        assert len(ledger) == 2

    def test_the_adjustment_keeps_the_material_and_plant(self) -> None:
        ledger = self.stocked()
        entry = ledger.reconcile("SI-1", Quantity(37000, "lb"), at(8), reference="PROBE-4")
        assert entry is not None
        assert entry.material_code == "CEM-I"
        assert entry.plant_code == "PL-1"
        assert entry.reference == "PROBE-4"

    def test_adjustments_can_be_listed(self) -> None:
        ledger = self.stocked()
        ledger.reconcile("SI-1", Quantity(37000, "lb"), at(8))
        assert len(ledger.adjustments("SI-1")) == 1

    def test_a_vessel_with_no_history_cannot_be_reconciled(self) -> None:
        with pytest.raises(ValidationError, match="no movements"):
            self.stocked().reconcile("SI-9", Quantity(1000, "lb"), at(8))

    def test_a_non_mass_reading_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="measured level is a mass"):
            self.stocked().reconcile("SI-1", Quantity(1, "yd3"), at(8))
