from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")


def more_sets(runner: CliRunner, register: str, count: int = 8) -> None:
    """Break enough sets that a chart has something to draw."""
    for index in range(count):
        code = f"S-90{index}"
        run(
            runner,
            register,
            "lab",
            "set",
            code,
            "--mix",
            "4000P-57",
            "--sampled",
            f"2024-07-{index + 1:02d}T09:20",
            "--size",
            "6x12",
        )
        for letter in ("A", "B"):
            specimen = f"C-{code}-{letter}"
            run(
                runner,
                register,
                "lab",
                "cylinder",
                specimen,
                "--set",
                code,
                "--ticket",
                "881204",
                "--cast",
                f"2024-07-{index + 1:02d}T09:20",
                "--size",
                "6x12",
            )
            load = 141000 + index * 500
            run(
                runner,
                register,
                "lab",
                "break",
                specimen,
                "--tested",
                f"2024-08-{index + 1:02d}T10:15",
                "--age",
                "28",
                "--d1",
                "6.00 in",
                "--d2",
                "6.00 in",
                "--length",
                "12.00 in",
                "--load",
                f"{load} lbf",
            )


class CaseRead:
    def test_it_reads_both_variations(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "control", "read", "4000P-57")
        assert result.exit_code == 0
        assert "overall grade" in result.output
        assert "within test grade" in result.output
        assert "look at" in result.output

    def test_a_short_record_says_so(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "control", "read", "4000P-57")
        assert "too few tests" in result.output

    def test_a_longer_record_does_not(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        more_sets(runner, register)
        result = run(runner, register, "control", "read", "4000P-57")
        assert "too few tests" not in result.output

    def test_a_mix_with_no_tests(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "control", "read", "4000P-57")
        assert result.exit_code != 0
        assert "at least two tests" in result.output


class CaseCharts:
    def test_all_three(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        more_sets(runner, register)
        result = run(
            runner, register, "control", "charts", "4000P-57", "--specified", "4000 psi"
        )
        assert result.exit_code == 0
        assert "Individual tests" in result.output
        assert "Moving average of three" in result.output
        assert "Moving range" in result.output

    def test_one_chart(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        more_sets(runner, register)
        result = run(runner, register, "control", "chart", "4000P-57")
        assert "Individual tests" in result.output

    def test_the_average_chart(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        more_sets(runner, register)
        result = run(
            runner,
            register,
            "control",
            "chart",
            "4000P-57",
            "--kind",
            "average",
            "--specified",
            "4000 psi",
        )
        assert "Moving average" in result.output

    def test_the_range_chart(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        more_sets(runner, register)
        result = run(runner, register, "control", "chart", "4000P-57", "--kind", "range")
        assert "Moving range" in result.output

    def test_a_point_outside_the_limits_is_an_error(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "control",
            "chart",
            "4000P-57",
            "--kind",
            "average",
            "--specified",
            "4800 psi",
        )
        assert result.exit_code != 0
        assert "outside the limits" in result.output

    def test_an_unknown_chart_kind(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "control", "chart", "4000P-57", "--kind", "spiral")
        assert result.exit_code != 0
