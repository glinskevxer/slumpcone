from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.ingest.source import (
    SourceRow,
    normalize_header,
    read_delimited,
    rows_with_values,
    sniff_delimiter,
)

PLAIN = "ticket,mix,volume\n881204,4000P-57,9.0\n881205,4000P-57,7.5\n"


class CaseNormalizeHeader:
    @pytest.mark.parametrize(
        ("written", "folded"),
        [
            ("Ticket", "ticket"),
            ("Batch Wt. (lb)", "batch_wt_lb"),
            ("  MIX CODE  ", "mix_code"),
            ("batch_wt_lb", "batch_wt_lb"),
            ("﻿ticket", "ticket"),
            ("W/CM", "w_cm"),
        ],
    )
    def test_folding(self, written: str, folded: str) -> None:
        assert normalize_header(written) == folded

    def test_an_empty_heading_folds_to_nothing(self) -> None:
        assert normalize_header("   ") == ""


class CaseSniff:
    def test_a_comma_file(self) -> None:
        assert sniff_delimiter(PLAIN) == ","

    def test_a_semicolon_file(self) -> None:
        assert sniff_delimiter("a;b;c\n1;2;3\n") == ";"

    def test_a_tab_file(self) -> None:
        assert sniff_delimiter("a\tb\tc\n1\t2\t3\n") == "\t"

    def test_commas_inside_quotes_do_not_win(self) -> None:
        text = 'name;address\n"Ashfield";"12 High St, Ashfield"\n'
        assert sniff_delimiter(text) == ";"

    def test_leading_blank_lines_are_skipped(self) -> None:
        assert sniff_delimiter("\n\na;b\n1;2\n") == ";"

    def test_a_file_with_no_delimiter_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no delimiter"):
            sniff_delimiter("just one column\nand one value\n")


class CaseRead:
    def test_a_plain_file(self) -> None:
        header, rows = read_delimited(PLAIN)
        assert header == ("ticket", "mix", "volume")
        assert len(rows) == 2
        assert rows[0].get("ticket") == "881204"

    def test_line_numbers_point_at_the_file(self) -> None:
        _, rows = read_delimited(PLAIN)
        assert [row.line_number for row in rows] == [2, 3]

    def test_a_byte_order_mark_is_stripped(self) -> None:
        header, _ = read_delimited("﻿" + PLAIN)
        assert header[0] == "ticket"

    def test_headings_are_folded(self) -> None:
        header, rows = read_delimited("Ticket No.,Batch Wt. (lb)\n881204,4230\n")
        assert header == ("ticket_no", "batch_wt_lb")
        assert rows[0].get("Batch Wt. (lb)") == "4230"

    def test_an_explicit_delimiter_wins(self) -> None:
        header, _ = read_delimited("a;b\n1;2\n", delimiter=";")
        assert header == ("a", "b")

    def test_skip_lines_drops_a_title_block(self) -> None:
        text = "Northmoor plant\n2024-06-12\nticket,mix\n881204,4000P-57\n"
        header, rows = read_delimited(text, skip_lines=2)
        assert header == ("ticket", "mix")
        assert rows[0].line_number == 4

    def test_leading_blank_lines_do_not_shift_the_numbering(self) -> None:
        header, rows = read_delimited("\n\nticket,mix\n881204,4000P-57\n")
        assert header == ("ticket", "mix")
        assert rows[0].line_number == 4

    def test_a_negative_skip_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            read_delimited(PLAIN, skip_lines=-1)

    def test_an_empty_file_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no rows"):
            read_delimited("")

    def test_a_file_that_is_all_blank_lines_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no rows"):
            read_delimited("\n\n\n")

    def test_a_header_of_only_separators_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="header row is empty"):
            read_delimited(",,,\n1,2,3\n")


class CaseRaggedRows:
    def test_a_short_row_records_what_is_missing(self) -> None:
        _, rows = read_delimited("ticket,mix,volume\n881204,4000P-57\n")
        assert rows[0].missing == ("volume",)
        assert rows[0].is_ragged
        assert rows[0].get("volume") == ""

    def test_a_long_row_records_the_extra_fields(self) -> None:
        _, rows = read_delimited("ticket,mix\n881204,4000P-57,junk\n")
        assert rows[0].extra == ("junk",)
        assert rows[0].is_ragged

    def test_a_tidy_row_is_not_ragged(self) -> None:
        _, rows = read_delimited(PLAIN)
        assert not rows[0].is_ragged

    def test_an_unnamed_column_is_dropped(self) -> None:
        _, rows = read_delimited("ticket,,volume\n881204,junk,9.0\n")
        assert set(rows[0].values) == {"ticket", "volume"}


class CaseRowHelpers:
    def test_get_and_has(self) -> None:
        row = SourceRow(2, {"ticket": "881204", "mix": "   "})
        assert row.get("Ticket") == "881204"
        assert row.get("nothing", "-") == "-"
        assert row.has("ticket")
        assert not row.has("mix")
        assert not row.has("nothing")

    def test_blank_rows(self) -> None:
        assert SourceRow(2, {"a": "", "b": "  "}).is_blank
        assert not SourceRow(2, {"a": "1"}).is_blank

    def test_describe(self) -> None:
        assert SourceRow(7, {}).describe() == "line 7"

    def test_rows_with_values_drops_the_blanks(self) -> None:
        _, rows = read_delimited("ticket,mix\n881204,4000P-57\n,\n881205,4000P-57\n")
        assert len(rows) == 3
        assert len(rows_with_values(rows)) == 2
