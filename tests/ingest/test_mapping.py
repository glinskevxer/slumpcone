from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.ingest.mapping import FieldKind, FieldSpec, MappingProfile
from slumpcone.ingest.source import SourceRow, read_delimited

HEADER = ("ticket_no", "mix", "batch_wt_lb", "extra_column")


def profile(**overrides: object) -> MappingProfile:
    fields: dict[str, object] = {
        "code": "MARCOTTE-V4",
        "name": "Marcotte batch recorder, version 4",
        "fields": (
            FieldSpec("ticket_number", ("ticket_no", "ticket"), required=True),
            FieldSpec("mix_code", ("mix", "mix_code"), required=True),
            FieldSpec(
                "batch_weight",
                ("batch_wt_lb",),
                kind=FieldKind.QUANTITY,
                unit="lb",
            ),
            FieldSpec("plant_code", ("plant",), default="PL-1"),
        ),
    }
    fields.update(overrides)
    return MappingProfile(**fields)  # type: ignore[arg-type]


class CaseFieldKind:
    def test_only_a_quantity_needs_a_unit(self) -> None:
        assert FieldKind.QUANTITY.needs_a_unit
        assert not FieldKind.NUMBER.needs_a_unit
        assert not FieldKind.TEXT.needs_a_unit

    def test_prints_its_own_value(self) -> None:
        assert str(FieldKind.DATETIME) == "datetime"


class CaseFieldSpec:
    def test_names_are_folded(self) -> None:
        spec = FieldSpec("Ticket Number", ("Ticket No.", "TICKET"))
        assert spec.name == "ticket_number"
        assert spec.columns == ("ticket_no", "ticket")

    def test_a_field_needs_a_name(self) -> None:
        with pytest.raises(ValidationError, match="needs a name"):
            FieldSpec("  ", ("a",))

    def test_a_field_needs_a_column(self) -> None:
        with pytest.raises(ValidationError, match="no source columns"):
            FieldSpec("ticket", ())

    def test_a_quantity_needs_a_unit(self) -> None:
        with pytest.raises(ValidationError, match="needs a unit"):
            FieldSpec("weight", ("wt",), kind=FieldKind.QUANTITY)

    def test_a_required_field_cannot_have_a_default(self) -> None:
        with pytest.raises(ValidationError, match="a default makes no sense"):
            FieldSpec("ticket", ("t",), required=True, default="x")

    def test_column_in(self) -> None:
        spec = FieldSpec("ticket_number", ("ticket_no", "ticket"))
        assert spec.column_in(HEADER) == "ticket_no"
        assert spec.column_in(("mix",)) is None

    def test_the_first_candidate_present_wins(self) -> None:
        spec = FieldSpec("ticket_number", ("ticket", "ticket_no"))
        assert spec.column_in(("ticket_no", "ticket")) == "ticket"


class CaseProfile:
    def test_the_code_and_name_are_normalised(self) -> None:
        built = profile(code=" marcotte v4 ", name="  Marcotte   recorder ")
        assert built.code == "MARCOTTE-V4"
        assert built.name == "Marcotte recorder"

    def test_a_profile_needs_fields(self) -> None:
        with pytest.raises(ValidationError, match="at least one field"):
            profile(fields=())

    def test_a_repeated_field_is_refused(self) -> None:
        one = FieldSpec("ticket_number", ("ticket",))
        with pytest.raises(ValidationError, match="mapped twice"):
            profile(fields=(one, one))

    def test_a_negative_skip_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            profile(skip_lines=-1)

    def test_field_names_and_required_names(self) -> None:
        assert profile().field_names == (
            "ticket_number",
            "mix_code",
            "batch_weight",
            "plant_code",
        )
        assert profile().required_names == ("ticket_number", "mix_code")

    def test_field_by_name(self) -> None:
        assert profile().field("Batch Weight").unit == "lb"

    def test_an_unknown_field_is_named(self) -> None:
        with pytest.raises(ValidationError, match="not in this profile"):
            profile().field("nothing")

    def test_describe(self) -> None:
        assert profile().describe() == (
            "MARCOTTE-V4  Marcotte batch recorder, version 4  4 fields, 2 required"
        )


class CaseResolution:
    def test_resolve_finds_the_columns_that_are_there(self) -> None:
        resolved = profile().resolve(HEADER)
        assert resolved == {
            "ticket_number": "ticket_no",
            "mix_code": "mix",
            "batch_weight": "batch_wt_lb",
        }

    def test_missing_required(self) -> None:
        assert profile().missing_required(HEADER) == ()
        assert profile().missing_required(("mix",)) == ("ticket_number",)

    def test_check_header_refuses_a_file_it_cannot_read(self) -> None:
        with pytest.raises(ValidationError, match="needs ticket_number"):
            profile().check_header(("mix",))

    def test_check_header_passes_a_readable_one(self) -> None:
        profile().check_header(HEADER)

    def test_unmapped_columns_are_reported_not_refused(self) -> None:
        assert profile().unmapped_columns(HEADER) == ("extra_column",)

    def test_a_file_with_only_extra_columns(self) -> None:
        assert profile().unmapped_columns(("a", "b")) == ("a", "b")


class CaseRawValues:
    def test_it_keys_by_canonical_name(self) -> None:
        header, rows = read_delimited(
            "Ticket No.,Mix,Batch Wt. (lb),Extra Column\n881204,4000P-57,4230,junk\n"
        )
        values = profile().raw_values(rows[0], header)
        assert values["ticket_number"] == "881204"
        assert values["mix_code"] == "4000P-57"
        assert values["batch_weight"] == "4230"

    def test_a_default_fills_a_missing_column(self) -> None:
        header, rows = read_delimited("ticket_no,mix\n881204,4000P-57\n")
        values = profile().raw_values(rows[0], header)
        assert values["plant_code"] == "PL-1"

    def test_a_default_fills_a_blank_value(self) -> None:
        header, rows = read_delimited("ticket_no,mix,plant\n881204,4000P-57,\n")
        values = profile().raw_values(rows[0], header)
        assert values["plant_code"] == "PL-1"

    def test_a_field_with_no_column_and_no_default_is_left_out(self) -> None:
        header, rows = read_delimited("ticket_no,mix\n881204,4000P-57\n")
        assert "batch_weight" not in profile().raw_values(rows[0], header)

    def test_a_row_built_by_hand(self) -> None:
        row = SourceRow(2, {"ticket_no": "881204", "mix": "4000P-57"})
        values = profile().raw_values(row, ("ticket_no", "mix"))
        assert values["ticket_number"] == "881204"
