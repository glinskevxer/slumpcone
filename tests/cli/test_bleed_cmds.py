from __future__ import annotations

import pytest
from click.testing import CliRunner

from tests.cli.support import run


def record(runner: CliRunner, register: str, ticket: str = "881204", *extra: str):  # type: ignore[no-untyped-def]
    return run(
        runner,
        register,
        "bleed",
        "record",
        ticket,
        "--on",
        "2024-06-12",
        "--sample",
        "60 lb",
        "--batch",
        "4000 lb",
        "--water",
        "260 lb",
        "--area",
        "100 in2",
        "--draw",
        "10:0.05",
        "--draw",
        "30:0.04",
        "--draw",
        "60:0.02",
        *extra,
    )


class CaseRecord:
    def test_it_files_the_test(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register)
        assert result.exit_code == 0
        assert "881204" in result.output

    def test_the_share_is_printed(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register)
        assert "of its mixing water" in result.output

    def test_a_test_with_no_draws(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "record",
            "881204",
            "--on",
            "2024-06-12",
            "--sample",
            "60 lb",
            "--batch",
            "4000 lb",
            "--water",
            "260 lb",
        )
        assert result.exit_code == 0

    def test_an_unreadable_draw(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "881204", "--draw", "later")
        assert result.exit_code != 0
        assert "BLEED_DRAW_UNREADABLE" in result.output

    def test_a_draw_with_a_bad_number(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "881204", "--draw", "ten:0.05")
        assert result.exit_code != 0
        assert "BLEED_DRAW_UNREADABLE" in result.output

    def test_the_same_day_twice(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = record(runner, register)
        assert result.exit_code != 0
        assert "already on file" in result.output

    def test_replace(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        assert record(runner, register, "881204", "--replace").exit_code == 0

    def test_a_sample_bigger_than_the_batch(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "record",
            "881204",
            "--on",
            "2024-06-12",
            "--sample",
            "5000 lb",
            "--batch",
            "4000 lb",
            "--water",
            "260 lb",
        )
        assert result.exit_code != 0
        assert "BLEED_SAMPLE_OVER_BATCH" in result.output


class CaseShow:
    def test_the_figures(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(runner, register, "bleed", "show", "881204", "--on", "2024-06-12")
        assert "share of mixing water" in result.output
        assert "depth" in result.output
        assert "rate" in result.output

    def test_the_draws_are_listed(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(runner, register, "bleed", "show", "881204", "--on", "2024-06-12")
        assert "minutes" in result.output
        assert "0.050" in result.output

    def test_a_later_rate_window(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(
            runner,
            register,
            "bleed",
            "show",
            "881204",
            "--on",
            "2024-06-12",
            "--after",
            "10",
        )
        assert result.exit_code == 0

    def test_a_window_with_nothing_in_it(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(
            runner,
            register,
            "bleed",
            "show",
            "881204",
            "--on",
            "2024-06-12",
            "--after",
            "500",
        )
        assert result.exit_code != 0
        assert "BLEED_RATE_NO_WINDOW" in result.output

    def test_a_test_with_no_draws_prints_no_table(
        self, runner: CliRunner, register: str
    ) -> None:
        run(
            runner,
            register,
            "bleed",
            "record",
            "881204",
            "--on",
            "2024-06-12",
            "--sample",
            "60 lb",
            "--batch",
            "4000 lb",
            "--water",
            "260 lb",
        )
        result = run(runner, register, "bleed", "show", "881204", "--on", "2024-06-12")
        assert "minutes" not in result.output

    def test_an_unknown_test(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "bleed", "show", "881204", "--on", "2024-06-12")
        assert result.exit_code != 0


class CaseList:
    def test_it_lists_the_window(self, runner: CliRunner, register: str) -> None:
        record(runner, register, "881204")
        record(runner, register, "881205")
        result = run(
            runner, register, "bleed", "list", "--from", "2024-06-12", "--to", "2024-06-12"
        )
        assert "881204" in result.output
        assert "881205" in result.output

    def test_the_heaviest_is_called_out(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(
            runner, register, "bleed", "list", "--from", "2024-06-12", "--to", "2024-06-12"
        )
        assert "heaviest" in result.output

    def test_an_empty_window_calls_out_nobody(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner, register, "bleed", "list", "--from", "2024-07-01", "--to", "2024-07-31"
        )
        assert "heaviest" not in result.output


class CaseColumn:
    def test_it_files_a_result(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "column",
            "881204",
            "--on",
            "2024-06-12",
            "--top",
            "2.9 lb",
            "--bottom",
            "3.1 lb",
        )
        assert result.exit_code == 0
        assert "uniform" in result.output or "settled" in result.output

    def test_the_visual_index_prints_its_note(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "column",
            "881204",
            "--on",
            "2024-06-12",
            "--top",
            "2.9 lb",
            "--bottom",
            "3.1 lb",
            "--visual",
            "2",
        )
        assert "visual stability 2" in result.output
        assert "mortar halo" in result.output

    def test_an_index_out_of_range(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "column",
            "881204",
            "--on",
            "2024-06-12",
            "--top",
            "2.9 lb",
            "--bottom",
            "3.1 lb",
            "--visual",
            "7",
        )
        assert result.exit_code != 0

    def test_an_empty_column(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "column",
            "881204",
            "--on",
            "2024-06-12",
            "--top",
            "0 lb",
            "--bottom",
            "0 lb",
        )
        assert result.exit_code != 0
        assert "SEGREGATION_NO_AGGREGATE" in result.output

    def test_the_listing(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "bleed",
            "column",
            "881204",
            "--on",
            "2024-06-12",
            "--top",
            "2.9 lb",
            "--bottom",
            "3.1 lb",
        )
        run(
            runner,
            register,
            "bleed",
            "column",
            "881205",
            "--on",
            "2024-06-12",
            "--top",
            "2.0 lb",
            "--bottom",
            "4.0 lb",
        )
        result = run(
            runner,
            register,
            "bleed",
            "columns",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
        )
        assert "2 result(s)" in result.output
        assert "over the cap" in result.output

    def test_only_the_failing(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "bleed",
            "column",
            "881204",
            "--on",
            "2024-06-12",
            "--top",
            "2.9 lb",
            "--bottom",
            "3.1 lb",
        )
        run(
            runner,
            register,
            "bleed",
            "column",
            "881205",
            "--on",
            "2024-06-12",
            "--top",
            "2.0 lb",
            "--bottom",
            "4.0 lb",
        )
        result = run(
            runner,
            register,
            "bleed",
            "columns",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
            "--failing",
        )
        assert "1 result(s)" in result.output
        assert "881204" not in result.output


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "bleed" in run(runner, register, "--help").output


@pytest.mark.parametrize("draw", ["10:0.05", " 10 : 0.05 "])
def test_a_draw_tolerates_spaces(runner: CliRunner, register: str, draw: str) -> None:
    result = run(
        runner,
        register,
        "bleed",
        "record",
        "881204",
        "--on",
        "2024-06-12",
        "--sample",
        "60 lb",
        "--batch",
        "4000 lb",
        "--water",
        "260 lb",
        "--draw",
        draw,
    )
    assert result.exit_code == 0
