from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run

FIRST = "label=first,uw=145,air=5.0,slump=4.0,retained=42,g=2.68,vol=0.25,coarse=15.225"
SECOND = "label=second,uw=144.6,air=5.4,slump=4.2,retained=43,g=2.68,vol=0.25,coarse=15.60"
WIDE = "label=second,uw=139,air=9.0,slump=6.0,retained=60,g=2.68,vol=0.25,coarse=20.0"


def record(  # type: ignore[no-untyped-def]
    runner: CliRunner,
    register: str,
    mixer: str = "MX-1",
    second: str = SECOND,
    *extra: str,
):
    return run(
        runner,
        register,
        "mixer",
        "uniformity",
        mixer,
        "--on",
        "2024-06-12",
        "--sample",
        FIRST,
        "--sample",
        second,
        "--plant",
        "PL-1",
        *extra,
    )


class CaseRecord:
    def test_it_files_and_judges(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register)
        assert result.exit_code == 0
        assert "MX-1" in result.output
        assert "uniform" in result.output

    def test_the_comparison_table_prints(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register)
        assert "air free unit weight" in result.output
        assert "share of average" in result.output

    def test_a_bad_mixer_says_so(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "MX-2", WIDE)
        assert "not uniform" in result.output
        assert "over" in result.output

    def test_the_strength_row_appears_when_given(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(
            runner,
            register,
            "mixer",
            "uniformity",
            "MX-1",
            "--on",
            "2024-06-12",
            "--sample",
            FIRST + ",psi=3200",
            "--sample",
            SECOND + ",psi=3300",
        )
        assert "seven day strength" in result.output

    def test_one_sample_is_not_a_test(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "mixer",
            "uniformity",
            "MX-1",
            "--on",
            "2024-06-12",
            "--sample",
            FIRST,
        )
        assert result.exit_code != 0
        assert "UNIFORMITY_NEEDS_TWO_SAMPLES" in result.output

    def test_three_samples_is_not_a_test_either(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "mixer",
            "uniformity",
            "MX-1",
            "--on",
            "2024-06-12",
            "--sample",
            FIRST,
            "--sample",
            SECOND,
            "--sample",
            WIDE,
        )
        assert result.exit_code != 0
        assert "UNIFORMITY_NEEDS_TWO_SAMPLES" in result.output

    def test_the_same_mixer_twice_in_a_day(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        assert record(runner, register).exit_code != 0


class CaseSampleParsing:
    def test_a_missing_reading(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "MX-1", "label=second,uw=144.6")
        assert result.exit_code != 0
        assert "UNIFORMITY_SAMPLE_INCOMPLETE" in result.output
        assert "air" in result.output

    def test_a_key_nobody_knows(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "MX-1", SECOND + ",temp=72")
        assert result.exit_code != 0
        assert "UNIFORMITY_SAMPLE_UNKNOWN_KEY" in result.output

    def test_a_chunk_with_no_equals(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "MX-1", SECOND + ",nonsense")
        assert result.exit_code != 0
        assert "UNIFORMITY_SAMPLE_UNREADABLE" in result.output

    def test_a_reading_that_is_not_a_number(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register, "MX-1", SECOND.replace("air=5.4", "air=high"))
        assert result.exit_code != 0
        assert "UNIFORMITY_SAMPLE_UNREADABLE" in result.output

    def test_trailing_commas_and_spaces_are_fine(
        self, runner: CliRunner, register: str
    ) -> None:
        assert record(runner, register, "MX-1", " " + SECOND + " , ").exit_code == 0

    def test_the_key_listing(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mixer", "keys")
        assert "retained" in result.output
        assert "required" in result.output
        assert "no" in result.output


class CaseReading:
    def test_show(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(runner, register, "mixer", "show", "MX-1", "--on", "2024-06-12")
        assert "inside the limit" in result.output
        assert "first and second" in result.output

    def test_show_an_unknown_test(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mixer", "show", "MX-1", "--on", "2024-06-12")
        assert result.exit_code != 0

    def test_history(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(runner, register, "mixer", "history", "MX-1")
        assert "1 test(s)" in result.output

    def test_history_of_a_mixer_never_tested(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mixer", "history", "MX-9")
        assert "0 test(s)" in result.output

    def test_list(self, runner: CliRunner, register: str) -> None:
        record(runner, register, "MX-1")
        record(runner, register, "MX-2", WIDE)
        result = run(
            runner, register, "mixer", "list", "--from", "2024-06-12", "--to", "2024-06-12"
        )
        assert "2 test(s)" in result.output

    def test_list_only_the_failing(self, runner: CliRunner, register: str) -> None:
        record(runner, register, "MX-1")
        record(runner, register, "MX-2", WIDE)
        result = run(
            runner,
            register,
            "mixer",
            "list",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
            "--failing",
        )
        assert "1 test(s)" in result.output
        assert "MX-2" in result.output

    def test_list_by_plant(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(
            runner,
            register,
            "mixer",
            "list",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
            "--plant",
            "PL-9",
        )
        assert "0 test(s)" in result.output


class CaseDue:
    def test_a_mixer_never_tested_is_due(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mixer", "due", "MX-1", "--on", "2024-06-12")
        assert "never" in result.output
        assert "1 of 1 due" in result.output

    def test_a_mixer_tested_today_is_current(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(runner, register, "mixer", "due", "MX-1", "--on", "2024-06-12")
        assert "current" in result.output
        assert "0 of 1 due" in result.output

    def test_a_shorter_interval_pulls_it_forward(
        self, runner: CliRunner, register: str
    ) -> None:
        record(runner, register)
        result = run(
            runner, register, "mixer", "due", "MX-1", "--on", "2024-09-12", "--every", "30"
        )
        assert "1 of 1 due" in result.output

    def test_nothing_asked_about(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mixer", "due", "--on", "2024-06-12")
        assert "0 of 0 due" in result.output


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "mixer" in run(runner, register, "--help").output
