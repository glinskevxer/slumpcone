from __future__ import annotations

import pytest

from slumpcone.errors import NotFoundError
from slumpcone.ingest.pipeline import run_ingest
from slumpcone.ingest.profiles import (
    BATCH_RECORDER,
    FIELD_TESTS,
    LAB_BREAKS,
    MATERIAL_RECEIPTS,
    PROFILES,
    codes,
    profile,
    validators_for,
)
from slumpcone.units.quantity import Quantity


class CaseRegistry:
    def test_codes_are_sorted(self) -> None:
        assert codes() == (
            "BATCH-RECORDER",
            "FIELD-TESTS",
            "LAB-BREAKS",
            "MATERIAL-RECEIPTS",
        )

    def test_lookup(self) -> None:
        assert profile("batch recorder").code == "BATCH-RECORDER"

    def test_an_unknown_profile_is_named(self) -> None:
        with pytest.raises(NotFoundError, match="NOTHING"):
            profile("nothing")

    def test_every_profile_has_required_fields(self) -> None:
        for candidate in PROFILES:
            assert candidate.required_names


class CaseBatchRecorder:
    def test_a_typical_export(self) -> None:
        text = (
            "Doc No,Plant ID,Product,Batch Time,CY,Unit,Customer,Job\n"
            "881204,PL-1,4000P-57,2024-06-12 07:42,9.0,114,Ashfield Paving,Route 9\n"
        )
        result = run_ingest(BATCH_RECORDER, text, "recorder.csv")
        row = result.accepted[0]
        assert row.get("ticket_number") == "881204"
        assert row.get("volume") == Quantity(9.0, "yd3")
        assert row.get("truck_code") == "114"
        assert row.get("project") == "Route 9"

    def test_another_vendor_spelling_of_the_same_columns(self) -> None:
        text = (
            "ticket_number,plant_code,mix_id,load_time,quantity\n"
            "881204,PL-1,4000P-57,2024-06-12 07:42,9.0\n"
        )
        result = run_ingest(BATCH_RECORDER, text, "recorder.csv")
        assert result.accepted_count == 1

    def test_a_file_with_no_volume_column_is_refused(self) -> None:
        text = "ticket,plant,mix,batched\n881204,PL-1,4000P-57,2024-06-12 07:42\n"
        with pytest.raises(Exception, match="volume"):
            run_ingest(BATCH_RECORDER, text, "recorder.csv")


class CaseLabBreaks:
    def test_a_typical_export(self) -> None:
        text = (
            "Specimen,Set No,Break Date,Age,D1,D2,Length,Peak Load,Break Type,Tech\n"
            "C-4471-A,S-4471,2024-07-10,28,4.00,4.01,8.02,63000,cone,DK\n"
        )
        result = run_ingest(
            LAB_BREAKS, text, "breaks.csv", validators=validators_for("LAB-BREAKS")
        )
        row = result.accepted[0]
        assert row.get("specimen_code") == "C-4471-A"
        assert row.get("max_load") == Quantity(63000, "lbf")
        assert row.get("fracture") == "cone"

    def test_one_diameter_without_the_other_is_quarantined(self) -> None:
        text = "specimen,set,tested,age,d1,load\nC-A,S-1,2024-07-10,28,4.00,63000\n"
        result = run_ingest(
            LAB_BREAKS, text, "breaks.csv", validators=validators_for("LAB-BREAKS")
        )
        assert "present without diameter_two" in result.quarantined[0].reasons[0]

    def test_no_dimensions_at_all_is_quarantined(self) -> None:
        text = "specimen,set,tested,age,load\nC-A,S-1,2024-07-10,28,63000\n"
        result = run_ingest(
            LAB_BREAKS, text, "breaks.csv", validators=validators_for("LAB-BREAKS")
        )
        assert "none of diameter_one, length" in result.quarantined[0].reasons[0]


class CaseFieldTests:
    def test_a_typical_sheet(self) -> None:
        text = (
            "Ticket,Sample Time,Slump,Air %,Temp F,Tech,Retest\n"
            "881204,2024-06-12 08:05,4.5,6.2,78,DK,no\n"
        )
        result = run_ingest(
            FIELD_TESTS, text, "field.csv", validators=validators_for("FIELD-TESTS")
        )
        row = result.accepted[0]
        assert row.get("slump") == Quantity(4.5, "in")
        assert row.get("air").value == pytest.approx(6.2)
        assert row.get("is_retest") is False

    def test_a_sheet_with_no_readings_at_all_is_quarantined(self) -> None:
        text = "ticket,sample_time,slump,air\n881204,2024-06-12 08:05,,\n"
        result = run_ingest(
            FIELD_TESTS, text, "field.csv", validators=validators_for("FIELD-TESTS")
        )
        assert "none of slump" in result.quarantined[0].reasons[0]

    def test_the_retest_flag_defaults_to_no(self) -> None:
        text = "ticket,sample_time,slump\n881204,2024-06-12 08:05,4.5\n"
        result = run_ingest(FIELD_TESTS, text, "field.csv")
        assert result.accepted[0].get("is_retest") is False


class CaseMaterialReceipts:
    def test_a_typical_list(self) -> None:
        text = (
            "Ref,Plant,Bin,Product,Delivery Time,Net Weight,Vendor,BOL,Mill Cert\n"
            "RCV-2211,PL-1,SI-1,CEM-I,2024-06-11 05:40,48000,Ashfield,AC-77120,MC-2024-0412\n"
        )
        result = run_ingest(MATERIAL_RECEIPTS, text, "receipts.csv")
        row = result.accepted[0]
        assert row.get("silo_code") == "SI-1"
        assert row.get("quantity") == Quantity(48000, "lb")
        assert row.get("certificate_reference") == "MC-2024-0412"

    def test_a_weight_with_a_thousands_separator(self) -> None:
        text = (
            "ref,plant,silo,material,received,net_lb\n"
            'RCV-2211,PL-1,SI-1,CEM-I,2024-06-11 05:40,"48,000"\n'
        )
        result = run_ingest(MATERIAL_RECEIPTS, text, "receipts.csv")
        assert result.accepted[0].get("quantity") == Quantity(48000, "lb")


class CaseValidatorsFor:
    def test_the_batch_recorder_needs_none(self) -> None:
        assert validators_for("BATCH-RECORDER") == ()

    def test_the_lab_profile_has_two(self) -> None:
        assert len(validators_for("LAB-BREAKS")) == 2

    def test_an_unknown_profile_is_named(self) -> None:
        with pytest.raises(NotFoundError):
            validators_for("nothing")
