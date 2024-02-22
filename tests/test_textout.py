from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.textout import (
    Align,
    Column,
    bullet_list,
    heading,
    indent,
    render_pairs,
    render_table,
)


class CaseAlign:
    def test_left(self) -> None:
        assert Align.LEFT.pad("ab", 5) == "ab   "

    def test_right(self) -> None:
        assert Align.RIGHT.pad("ab", 5) == "   ab"

    def test_center(self) -> None:
        assert Align.CENTER.pad("ab", 6) == "  ab  "

    def test_a_cell_wider_than_the_column_is_left_alone(self) -> None:
        assert Align.RIGHT.pad("abcdef", 3) == "abcdef"


class CaseColumn:
    def test_a_negative_width_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            Column("x", min_width=-1)


class CaseRenderTable:
    columns = (
        Column("material"),
        Column("weight", Align.RIGHT),
    )

    def test_headings_and_rule(self) -> None:
        text = render_table(self.columns, [["CEM-I", 564]])
        lines = text.splitlines()
        assert lines[0] == "material  weight"
        assert lines[1] == "--------  ------"
        assert lines[2] == "CEM-I        564"

    def test_the_rule_can_be_left_off(self) -> None:
        text = render_table(self.columns, [["CEM-I", 564]], rule=False)
        assert len(text.splitlines()) == 2

    def test_columns_widen_to_the_widest_cell(self) -> None:
        text = render_table(self.columns, [["a-very-long-material-code", 1]])
        assert text.splitlines()[0].startswith("material                 ")

    def test_minimum_width_is_honoured(self) -> None:
        text = render_table((Column("x", min_width=8),), [["a"]], rule=False)
        assert text.splitlines()[0] == "x"
        assert text.splitlines()[1] == "a"

    def test_no_rows_still_prints_the_heading(self) -> None:
        assert render_table(self.columns, []).splitlines()[0] == "material  weight"

    def test_a_short_row_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="row 0 has 1 cells"):
            render_table(self.columns, [["CEM-I"]])

    def test_no_columns_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one column"):
            render_table((), [])

    def test_floats_print_to_two_places(self) -> None:
        text = render_table((Column("v"),), [[0.4551]], rule=False)
        assert text.splitlines()[1] == "0.46"

    def test_none_prints_as_a_dash(self) -> None:
        text = render_table((Column("v"),), [[None]], rule=False)
        assert text.splitlines()[1] == "-"

    def test_booleans_print_as_words(self) -> None:
        text = render_table((Column("v"),), [[True], [False]], rule=False)
        assert text.splitlines()[1:] == ["yes", "no"]

    def test_trailing_space_is_stripped(self) -> None:
        text = render_table(self.columns, [["CEM-I", 1]])
        assert all(line == line.rstrip() for line in text.splitlines())


class CaseRenderPairs:
    def test_labels_are_padded_to_a_common_width(self) -> None:
        text = render_pairs([("mix", "4000P-57"), ("cementitious", 564)])
        assert text.splitlines()[0] == "mix         : 4000P-57"
        assert text.splitlines()[1] == "cementitious: 564"

    def test_the_separator_is_adjustable(self) -> None:
        text = render_pairs([("a", 1)], separator=" = ")
        assert text == "a = 1"

    def test_nothing_at_all(self) -> None:
        assert render_pairs([]) == ""


class CaseDecoration:
    def test_heading(self) -> None:
        assert heading("Batch") == "Batch\n====="

    def test_heading_underline_is_adjustable(self) -> None:
        assert heading("Batch", underline="-") == "Batch\n-----"

    def test_a_multi_character_underline_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="single character"):
            heading("Batch", underline="==")

    def test_indent(self) -> None:
        assert indent("a\nb") == "  a\n  b"

    def test_indent_leaves_blank_lines_blank(self) -> None:
        assert indent("a\n\nb") == "  a\n\n  b"

    def test_bullet_list(self) -> None:
        assert bullet_list(["one", "two"]) == "- one\n- two"

    def test_bullet_list_hangs_wrapped_lines(self) -> None:
        assert bullet_list(["one\nmore"]) == "- one\n  more"

    def test_bullet_marker_is_adjustable(self) -> None:
        assert bullet_list(["one"], marker="*") == "* one"
