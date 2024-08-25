from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.tests import FreshTestKind
from slumpcone.ingest.adapters import (
    to_break_result,
    to_delivery,
    to_fresh_tests,
    to_receipt,
)
from slumpcone.ingest.pipeline import run_ingest
from slumpcone.ingest.profiles import (
    BATCH_RECORDER,
    FIELD_TESTS,
    LAB_BREAKS,
    MATERIAL_RECEIPTS,
)
from slumpcone.ingest.result import AcceptedRow
from slumpcone.strength.breaks import FractureType
from slumpcone.units.quantity import Quantity


def only(profile: object, text: str) -> AcceptedRow:
    result = run_ingest(profile, text, "file.csv")  # type: ignore[arg-type]
    assert result.is_clean, result.describe()
    return result.accepted[0]


class CaseDelivery:
    text = (
        "ticket,plant,mix,batched,volume,truck\n"
        "881204,PL-1,4000P-57,2024-06-12 07:42,9.0,TR-114\n"
    )

    def test_it_builds_a_delivery(self) -> None:
        delivery = to_delivery(only(BATCH_RECORDER, self.text))
        assert delivery.ticket_number == "881204"
        assert delivery.truck_code == "TR-114"
        assert delivery.batched_at == datetime(2024, 6, 12, 7, 42)
        assert "line 2" in delivery.notes

    def test_a_row_with_no_truck_is_refused(self) -> None:
        text = "ticket,plant,mix,batched,volume\n881204,PL-1,4000P-57,2024-06-12 07:42,9.0\n"
        with pytest.raises(ValidationError, match="no truck on line 2"):
            to_delivery(only(BATCH_RECORDER, text))

    def test_a_missing_field_is_named(self) -> None:
        row = AcceptedRow(2, {"truck_code": "TR-114"}, "x")
        with pytest.raises(ValidationError, match="batched_at is missing on line 2"):
            to_delivery(row)

    def test_a_batched_at_that_is_not_a_timestamp(self) -> None:
        row = AcceptedRow(2, {"truck_code": "T", "ticket_number": "1", "batched_at": "x"}, "d")
        with pytest.raises(ValidationError, match="not a timestamp"):
            to_delivery(row)


class CaseBreakResult:
    text = (
        "specimen,set,tested,age,d1,d2,length,load,break_type,tech\n"
        "C-4471-A,S-4471,2024-07-10,28,4.00,4.01,8.02,63000,cone,DK\n"
    )

    def test_it_builds_a_break(self) -> None:
        result = to_break_result(only(LAB_BREAKS, self.text))
        assert result.specimen_code == "C-4471-A"
        assert result.age_days == pytest.approx(28.0)
        assert result.fracture is FractureType.CONE
        assert result.tested_by == "DK"

    def test_one_diameter_is_taken_as_round(self) -> None:
        text = "specimen,set,tested,age,d1,length,load\nC-A,S-1,2024-07-10,28,4.00,8.00,63000\n"
        result = to_break_result(only(LAB_BREAKS, text))
        assert result.diameter_one == result.diameter_two

    def test_a_missing_length_is_taken_as_twice_the_diameter(self) -> None:
        text = "specimen,set,tested,age,d1,d2,load\nC-A,S-1,2024-07-10,28,4.00,4.00,63000\n"
        result = to_break_result(only(LAB_BREAKS, text))
        assert result.length == Quantity(8.0, "in")

    def test_a_missing_fracture_defaults_to_a_cone(self) -> None:
        text = "specimen,set,tested,age,d1,d2,length,load\nC-A,S-1,2024-07-10,28,4,4,8,63000\n"
        assert to_break_result(only(LAB_BREAKS, text)).fracture is FractureType.CONE

    def test_an_unreadable_fracture_is_refused(self) -> None:
        text = (
            "specimen,set,tested,age,d1,d2,length,load,break_type\n"
            "C-A,S-1,2024-07-10,28,4,4,8,63000,crumbled\n"
        )
        with pytest.raises(ValidationError, match="fracture type"):
            to_break_result(only(LAB_BREAKS, text))

    def test_a_row_with_no_diameter_is_refused(self) -> None:
        row = AcceptedRow(2, {"specimen_code": "C-A"}, "x")
        with pytest.raises(ValidationError, match="no diameter on line 2"):
            to_break_result(row)


class CaseFreshTests:
    def test_one_row_can_be_four_tests(self) -> None:
        text = (
            "ticket,sample_time,slump,air,temp_f,unit_wt,tech\n"
            "881204,2024-06-12 08:05,4.5,6.2,78,142.6,DK\n"
        )
        tests = to_fresh_tests(only(FIELD_TESTS, text))
        assert [test.kind for test in tests] == [
            FreshTestKind.SLUMP,
            FreshTestKind.AIR_PRESSURE,
            FreshTestKind.TEMPERATURE,
            FreshTestKind.UNIT_WEIGHT,
        ]

    def test_the_readings_are_carried(self) -> None:
        text = "ticket,sample_time,slump,temp_f\n881204,2024-06-12 08:05,4.5,78\n"
        tests = to_fresh_tests(only(FIELD_TESTS, text))
        assert tests[0].slump == Quantity(4.5, "in")
        assert tests[1].temperature is not None
        assert tests[1].temperature.fahrenheit == pytest.approx(78.0)

    def test_the_technician_and_retest_flag_travel(self) -> None:
        text = "ticket,sample_time,slump,tech,retest\n881204,2024-06-12 08:05,4.5,DK,yes\n"
        tests = to_fresh_tests(only(FIELD_TESTS, text))
        assert tests[0].technician == "DK"
        assert tests[0].is_retest

    def test_a_row_with_no_readings_is_refused(self) -> None:
        row = AcceptedRow(
            2, {"ticket_number": "881204", "taken_at": datetime(2024, 6, 12, 8, 5)}, "x"
        )
        with pytest.raises(ValidationError, match="no readings on line 2"):
            to_fresh_tests(row)

    def test_an_impossible_reading_is_refused_by_the_record(self) -> None:
        text = "ticket,sample_time,slump\n881204,2024-06-12 08:05,15\n"
        with pytest.raises(ValidationError, match="collapsed cone"):
            to_fresh_tests(only(FIELD_TESTS, text))


class CaseReceipt:
    text = (
        "ref,plant,silo,material,received,net_lb,vendor,bol,mill_cert\n"
        "RCV-2211,PL-1,SI-1,CEM-I,2024-06-11 05:40,48000,Ashfield,AC-77120,MC-2024-0412\n"
    )

    def test_it_builds_a_receipt(self) -> None:
        receipt = to_receipt(only(MATERIAL_RECEIPTS, self.text))
        assert receipt.reference == "RCV-2211"
        assert receipt.quantity == Quantity(48000, "lb")
        assert receipt.supplier == "Ashfield"
        assert receipt.has_paper

    def test_a_receipt_with_no_paper(self) -> None:
        text = (
            "ref,plant,silo,material,received,net_lb\nRCV-1,PL-1,SI-1,CEM-I,2024-06-11,4800\n"
        )
        assert not to_receipt(only(MATERIAL_RECEIPTS, text)).has_paper

    def test_a_quantity_that_is_not_a_weight(self) -> None:
        row = AcceptedRow(
            2,
            {
                "reference": "RCV-1",
                "plant_code": "PL-1",
                "silo_code": "SI-1",
                "material_code": "CEM-I",
                "received_at": datetime(2024, 6, 11, 5, 40),
                "quantity": 48000.0,
            },
            "x",
        )
        with pytest.raises(ValidationError, match="not a weight"):
            to_receipt(row)
