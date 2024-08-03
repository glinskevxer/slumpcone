from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.percent import Percent
from slumpcone.plant.receipt import Receipt, apply_receipt, check_receipt
from slumpcone.plant.silo import Silo
from slumpcone.units.quantity import Quantity

RECEIVED = datetime(2024, 6, 11, 5, 40)


def silo(**overrides: object) -> Silo:
    fields: dict[str, object] = {
        "code": "SI-1",
        "name": "Cement silo one",
        "material_code": "CEM-I",
        "capacity": Quantity(200000, "lb"),
        "level": Quantity(120000, "lb"),
        "low_level": Quantity(30000, "lb"),
    }
    fields.update(overrides)
    return Silo(**fields)  # type: ignore[arg-type]


def receipt(**overrides: object) -> Receipt:
    fields: dict[str, object] = {
        "reference": "RCV-2211",
        "plant_code": "PL-1",
        "silo_code": "SI-1",
        "material_code": "CEM-I",
        "received_at": RECEIVED,
        "quantity": Quantity(48000, "lb"),
        "supplier": "Ashfield Cement",
        "supplier_ticket": "AC-77120",
        "certificate_reference": "MC-2024-0412",
    }
    fields.update(overrides)
    return Receipt(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_codes_are_normalised(self) -> None:
        built = receipt(reference=" rcv 2211 ", silo_code="si 1", supplier_ticket="ac 77120")
        assert built.reference == "RCV-2211"
        assert built.silo_code == "SI-1"
        assert built.supplier_ticket == "AC-77120"

    def test_the_supplier_whitespace_collapses(self) -> None:
        assert receipt(supplier="  Ashfield   Cement ").supplier == "Ashfield Cement"

    def test_the_quantity_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="received quantity is a mass"):
            receipt(quantity=Quantity(48000, "yd3"))
        with pytest.raises(ValidationError, match="has to be positive"):
            receipt(quantity=Quantity(0, "lb"))

    def test_a_silly_moisture_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="probe fault"):
            receipt(moisture=Percent(25.0))

    def test_a_sensible_moisture_is_kept(self) -> None:
        assert receipt(moisture=Percent(4.5)).moisture == Percent(4.5)

    def test_has_paper(self) -> None:
        assert receipt().has_paper
        assert not receipt(certificate_reference=None).has_paper

    def test_describe(self) -> None:
        line = receipt().describe()
        assert "RCV-2211" in line
        assert "2024-06-11" in line
        assert "CEM-I into SI-1" in line
        assert "Ashfield Cement" in line


class CaseChecks:
    def test_a_clean_receipt(self) -> None:
        assert check_receipt(receipt(), silo()) == ()

    def test_the_wrong_vessel(self) -> None:
        faults = check_receipt(receipt(silo_code="SI-2"), silo())
        assert any("not the vessel" in fault for fault in faults)

    def test_the_wrong_material(self) -> None:
        faults = check_receipt(receipt(material_code="SCM-F"), silo())
        assert any("holds CEM-I" in fault for fault in faults)

    def test_no_headroom(self) -> None:
        faults = check_receipt(receipt(quantity=Quantity(90000, "lb")), silo())
        assert any("headroom" in fault for fault in faults)

    def test_no_certificate(self) -> None:
        faults = check_receipt(receipt(certificate_reference=None), silo())
        assert faults == ("no certificate reference on the receipt",)


class CaseApply:
    def test_a_clean_receipt_raises_the_level(self) -> None:
        after = apply_receipt(receipt(), silo())
        assert after.level == Quantity(168000, "lb")

    def test_missing_paper_does_not_stop_the_delivery(self) -> None:
        after = apply_receipt(receipt(certificate_reference=None), silo())
        assert after.level == Quantity(168000, "lb")

    def test_the_wrong_material_is_refused(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            apply_receipt(receipt(material_code="SCM-F"), silo())
        assert caught.value.code == "RECEIPT_REFUSED"
        assert "holds CEM-I" in caught.value.detail

    def test_no_headroom_is_refused(self) -> None:
        with pytest.raises(RuleViolationError, match="headroom"):
            apply_receipt(receipt(quantity=Quantity(90000, "lb")), silo())

    def test_the_wrong_vessel_is_refused(self) -> None:
        with pytest.raises(RuleViolationError, match="not the vessel"):
            apply_receipt(receipt(silo_code="SI-2"), silo())

    def test_two_faults_are_reported_together(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            apply_receipt(
                receipt(material_code="SCM-F", quantity=Quantity(90000, "lb")), silo()
            )
        assert caught.value.detail.count(";") == 1

    def test_the_original_silo_is_untouched(self) -> None:
        original = silo()
        apply_receipt(receipt(), original)
        assert original.level == Quantity(120000, "lb")
