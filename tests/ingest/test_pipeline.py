from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.ingest.mapping import FieldKind, FieldSpec, MappingProfile
from slumpcone.ingest.pipeline import one_of, required_together, run_ingest
from slumpcone.ingest.result import RowOutcome
from slumpcone.units.quantity import Quantity

FILE = (
    "Ticket No.,Mix,Volume (yd3),Batched,Operator\n"
    "881204,4000P-57,9.0,2024-06-12 07:42,DK\n"
    "881205,4000P-57,7.5,2024-06-12 08:15,DK\n"
)


def profile(**overrides: object) -> MappingProfile:
    fields: dict[str, object] = {
        "code": "MARCOTTE-V4",
        "name": "Marcotte batch recorder",
        "fields": (
            FieldSpec("ticket_number", ("ticket_no",), required=True),
            FieldSpec("mix_code", ("mix",), required=True),
            FieldSpec("volume", ("volume_yd3",), kind=FieldKind.QUANTITY, unit="yd3"),
            FieldSpec("batched_at", ("batched",), kind=FieldKind.DATETIME),
            FieldSpec("plant_code", ("plant",), default="PL-1"),
        ),
    }
    fields.update(overrides)
    return MappingProfile(**fields)  # type: ignore[arg-type]


class CaseCleanRun:
    def test_every_row_lands(self) -> None:
        result = run_ingest(profile(), FILE, "batches.csv")
        assert result.accepted_count == 2
        assert result.is_clean

    def test_the_values_are_coerced(self) -> None:
        result = run_ingest(profile(), FILE, "batches.csv")
        row = result.accepted[0]
        assert row.get("ticket_number") == "881204"
        assert row.get("volume") == Quantity(9.0, "yd3")
        assert row.get("batched_at").isoformat() == "2024-06-12T07:42:00"

    def test_defaults_are_applied(self) -> None:
        result = run_ingest(profile(), FILE, "batches.csv")
        assert result.accepted[0].get("plant_code") == "PL-1"

    def test_unmapped_columns_are_reported(self) -> None:
        result = run_ingest(profile(), FILE, "batches.csv")
        assert result.unmapped_columns == ("operator",)

    def test_line_numbers_point_at_the_file(self) -> None:
        result = run_ingest(profile(), FILE, "batches.csv")
        assert [row.line_number for row in result.accepted] == [2, 3]


class CaseQuarantine:
    def test_a_blank_required_field(self) -> None:
        text = "ticket_no,mix\n,4000P-57\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert result.quarantined[0].reasons == ("ticket_number is blank",)

    def test_an_unreadable_number(self) -> None:
        text = "ticket_no,mix,volume_yd3\n881204,4000P-57,nine\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert "as a number" in result.quarantined[0].reasons[0]

    def test_every_complaint_is_collected(self) -> None:
        text = "ticket_no,mix,volume_yd3,batched\n,4000P-57,nine,never\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert len(result.quarantined[0].reasons) == 3

    def test_a_ragged_row_is_quarantined(self) -> None:
        text = "ticket_no,mix\n881204,4000P-57,junk\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert "past the end of the header" in result.quarantined[0].reasons[0]

    def test_the_raw_values_are_kept_for_the_operator(self) -> None:
        text = "ticket_no,mix,volume_yd3\n881204,4000P-57,nine\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert result.quarantined[0].values["volume"] == "nine"

    def test_a_good_row_beside_a_bad_one_still_lands(self) -> None:
        text = "ticket_no,mix,volume_yd3\n881204,4000P-57,9.0\n881205,4000P-57,nine\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert result.accepted_count == 1
        assert len(result.quarantined) == 1

    def test_blank_rows_are_skipped_not_quarantined(self) -> None:
        text = "ticket_no,mix\n881204,4000P-57\n,\n881205,4000P-57\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert result.accepted_count == 2
        assert result.is_clean


class CaseHeader:
    def test_a_file_missing_a_required_column_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="needs ticket_number"):
            run_ingest(profile(), "mix,volume_yd3\n4000P-57,9.0\n", "batches.csv")

    def test_a_profile_delimiter_is_honoured(self) -> None:
        semis = profile(delimiter=";")
        result = run_ingest(semis, "ticket_no;mix\n881204;4000P-57\n", "batches.csv")
        assert result.accepted_count == 1

    def test_skip_lines_is_honoured(self) -> None:
        titled = profile(skip_lines=1)
        text = "Northmoor plant\nticket_no,mix\n881204,4000P-57\n"
        result = run_ingest(titled, text, "batches.csv")
        assert result.accepted[0].line_number == 3

    def test_a_profile_date_format_is_honoured(self) -> None:
        american = profile(date_format="%m/%d/%Y %H:%M")
        text = "ticket_no,mix,batched\n881204,4000P-57,06/12/2024 07:42\n"
        result = run_ingest(american, text, "batches.csv")
        assert result.accepted[0].get("batched_at").month == 6


class CaseDuplicates:
    def test_a_repeated_row_inside_one_file(self) -> None:
        text = FILE + "881204,4000P-57,9.0,2024-06-12 07:42,DK\n"
        result = run_ingest(profile(), text, "batches.csv")
        assert result.accepted_count == 2
        assert result.duplicates == (4,)

    def test_a_re_run_is_all_duplicate(self) -> None:
        first = run_ingest(profile(), FILE, "batches.csv")
        again = run_ingest(
            profile(),
            FILE,
            "batches.csv",
            known_digests={row.digest for row in first.accepted},
        )
        assert again.is_all_duplicate
        assert again.outcome_of(2) is RowOutcome.DUPLICATE

    def test_a_changed_row_is_not_a_duplicate(self) -> None:
        first = run_ingest(profile(), FILE, "batches.csv")
        changed = FILE.replace("9.0", "9.5")
        again = run_ingest(
            profile(),
            changed,
            "batches.csv",
            known_digests={row.digest for row in first.accepted},
        )
        assert again.accepted_count == 1


class CaseValidators:
    def test_required_together_passes_a_full_set(self) -> None:
        check = required_together("ticket_number", "mix_code")
        assert check({"ticket_number": "881204", "mix_code": "4000P-57"}) == ()

    def test_required_together_passes_an_empty_set(self) -> None:
        assert required_together("a", "b")({}) == ()

    def test_required_together_catches_half_a_set(self) -> None:
        reasons = required_together("volume", "batched_at")({"volume": 9.0})
        assert "present without batched_at" in reasons[0]

    def test_one_of_passes_when_something_is_there(self) -> None:
        assert one_of("a", "b")({"b": 1}) == ()

    def test_one_of_catches_an_empty_set(self) -> None:
        assert "none of a, b" in one_of("a", "b")({})[0]

    def test_a_validator_quarantines_a_row(self) -> None:
        text = "ticket_no,mix,volume_yd3\n881204,4000P-57,9.0\n"
        result = run_ingest(profile(), text, "batches.csv", validators=(one_of("batched_at"),))
        assert "none of batched_at" in result.quarantined[0].reasons[0]

    def test_validators_do_not_run_on_a_row_that_already_failed(self) -> None:
        text = "ticket_no,mix,volume_yd3\n,4000P-57,nine\n"
        result = run_ingest(profile(), text, "batches.csv", validators=(one_of("batched_at"),))
        assert all("none of" not in reason for reason in result.quarantined[0].reasons)
