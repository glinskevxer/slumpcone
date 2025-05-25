from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run

DAY = "2024-06-12"


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")


class CaseDay:
    def test_the_page_prints(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "day", "--on", DAY)
        assert result.exit_code == 0
        assert "Plant day" in result.output
        assert "loads tested" in result.output

    def test_a_quiet_day_reads_clear(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "day", "--on", "2024-07-04")
        assert "clear" in result.output

    def test_the_findings_can_be_capped(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        full = run(runner, register, "report", "day", "--on", DAY)
        capped = run(runner, register, "report", "day", "--on", DAY, "--findings", "1")
        assert len(capped.output) < len(full.output)

    def test_by_plant(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "day", "--on", DAY, "--plant", "PL-9")
        assert "clear" in result.output


class CaseWeek:
    def test_a_line_per_day(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "week", "--from", DAY, "--to", "2024-06-14")
        assert result.exit_code == 0
        assert "2024-06-12" in result.output
        assert "2024-06-14" in result.output

    def test_it_counts_the_days_needing_attention(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "week", "--from", DAY, "--to", "2024-06-14")
        assert "day(s) needing attention" in result.output

    def test_a_window_that_runs_backwards(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "week", "--from", "2024-06-14", "--to", DAY)
        assert result.exit_code != 0
        assert "ends before it starts" in result.output

    def test_a_single_day_window(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "week", "--from", DAY, "--to", DAY)
        assert result.output.count("2024-06-12") >= 1


class CaseUtilisation:
    def test_it_prints_the_fleet(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "utilisation", "--from", DAY, "--to", DAY)
        assert result.exit_code == 0
        assert "yd3/h" in result.output
        assert "truck(s)" in result.output

    def test_the_record_count_is_shown(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "utilisation", "--from", DAY, "--to", DAY)
        # Four complete records is above the thin threshold, so the count
        # itself prints rather than the word.
        assert "records" in result.output
        assert "thin" not in result.output

    def test_the_worst_waiter_is_called_out(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "utilisation", "--from", DAY, "--to", DAY)
        assert "most time standing" in result.output

    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "report",
            "utilisation",
            "--from",
            "2024-07-01",
            "--to",
            "2024-07-31",
        )
        assert "0 truck(s)" in result.output
        assert "most time standing" not in result.output


class CaseCusum:
    def test_a_mix_with_too_few_tests(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "cusum", "4000P-57")
        assert result.exit_code != 0
        assert "CUSUM_" in result.output

    def test_a_handed_in_deviation_gets_further(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "report",
            "cusum",
            "4000P-57",
            "--target",
            "4600 psi",
            "--deviation",
            "400 psi",
        )
        assert "Cusum" in result.output or "CUSUM_" in result.output

    def test_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert run(runner, register, "report", "cusum", "NOPE").exit_code != 0
