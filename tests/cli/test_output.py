from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from slumpcone.cli.output import listing, page, plural
from slumpcone.textout import Align, Column

COLUMNS = (Column("code"), Column("rows", Align.RIGHT))
ROWS = [["PL-1", 4], ["PL-2", 9]]


def printed(work: object) -> str:
    """Run something that prints and hand back what it printed."""

    @click.command()
    def command() -> None:
        work()  # type: ignore[operator]

    return CliRunner().invoke(command).output


class CasePlural:
    def test_one(self) -> None:
        assert plural(1, "tank") == "1 tank(s)"

    def test_none(self) -> None:
        assert plural(0, "tank") == "0 tank(s)"

    def test_a_noun_with_a_space(self) -> None:
        assert plural(3, "probe check") == "3 probe check(s)"


class CaseListing:
    def test_it_prints_the_table(self) -> None:
        text = printed(lambda: listing(COLUMNS, ROWS, "plant"))
        assert "PL-1" in text
        assert "code" in text

    def test_it_counts_the_rows(self) -> None:
        assert "2 plant(s)" in printed(lambda: listing(COLUMNS, ROWS, "plant"))

    def test_an_empty_listing_still_says_zero(self) -> None:
        text = printed(lambda: listing(COLUMNS, [], "plant"))
        assert "0 plant(s)" in text

    def test_an_empty_listing_still_prints_the_header(self) -> None:
        # A table that was never filled and one that came back empty look the
        # same without this.
        assert "code" in printed(lambda: listing(COLUMNS, [], "plant"))

    def test_a_title_is_optional(self) -> None:
        assert "Plants" not in printed(lambda: listing(COLUMNS, ROWS, "plant"))

    def test_a_title_prints_when_given(self) -> None:
        text = printed(lambda: listing(COLUMNS, ROWS, "plant", title="Plants"))
        assert "Plants" in text

    def test_the_count_comes_last(self) -> None:
        text = printed(lambda: listing(COLUMNS, ROWS, "plant"))
        assert text.strip().splitlines()[-1] == "2 plant(s)"


class CasePage:
    def test_the_heading(self) -> None:
        text = printed(lambda: page("Probe MP-1", [("checks", 3)]))
        assert "Probe MP-1" in text

    def test_the_pairs(self) -> None:
        text = printed(lambda: page("Probe MP-1", [("checks", 3)]))
        assert "checks" in text
        assert "3" in text

    def test_a_page_with_no_table(self) -> None:
        text = printed(lambda: page("Probe MP-1", [("checks", 3)]))
        assert "code" not in text

    def test_a_page_with_a_table(self) -> None:
        text = printed(lambda: page("Probe MP-1", [("checks", 3)], COLUMNS, ROWS))
        assert "PL-1" in text

    def test_an_empty_table_is_left_off_entirely(self) -> None:
        # A header with nothing under it reads as a bug, so a page with no rows
        # prints no table at all. A listing, which exists to be a count, does
        # the opposite.
        text = printed(lambda: page("Probe MP-1", [("checks", 0)], COLUMNS, []))
        assert "code" not in text

    def test_columns_without_rows_are_left_off(self) -> None:
        text = printed(lambda: page("Probe MP-1", [("checks", 0)], COLUMNS, None))
        assert "code" not in text

    def test_there_is_a_blank_line_before_the_table(self) -> None:
        text = printed(lambda: page("Probe MP-1", [("checks", 3)], COLUMNS, ROWS))
        lines = text.splitlines()
        assert "" in lines[2:]

    def test_no_pairs_at_all(self) -> None:
        assert "Probe MP-1" in printed(lambda: page("Probe MP-1", []))


@pytest.mark.parametrize("count", [0, 1, 2, 17])
def test_every_count_reads_the_same_way(count: int) -> None:
    rows = [["X", index] for index in range(count)]
    assert f"{count} thing(s)" in printed(lambda: listing(COLUMNS, rows, "thing"))
