from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


def fit(runner: CliRunner, register: str, name: str = "summer") -> object:
    return run(
        runner,
        register,
        "maturity",
        "fit",
        "4000P-57",
        "--name",
        name,
        "--point",
        "240:2200",
        "--point",
        "480:3300",
        "--point",
        "960:4300",
        "--point",
        "1920:5100",
        "--on",
        "2024-05-01",
    )


def log(runner: CliRunner, register: str, hours: int = 48, temp: float = 68.0) -> None:
    for step in range(0, hours + 1, 12):
        run(
            runner,
            register,
            "maturity",
            "log",
            "SN-1",
            "--placement",
            "Bay 4 slab",
            "--at",
            f"2024-06-{12 + step // 24:02d}T{8 + step % 24:02d}:00",
            "--temp",
            str(temp),
        )


class CaseFit:
    def test_it_files_a_curve(self, runner: CliRunner, register: str) -> None:
        result = fit(runner, register)
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert "ln(M)" in result.output  # type: ignore[attr-defined]

    def test_too_few_points(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "maturity",
            "fit",
            "4000P-57",
            "--name",
            "summer",
            "--point",
            "240:2200",
        )
        assert result.exit_code != 0
        assert "at least three ages" in result.output

    def test_a_malformed_point(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "maturity",
            "fit",
            "4000P-57",
            "--name",
            "summer",
            "--point",
            "240",
        )
        assert result.exit_code != 0
        assert "MATURITY:STRENGTH" in result.output

    def test_a_maturity_that_is_not_a_number(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "maturity",
            "fit",
            "4000P-57",
            "--name",
            "summer",
            "--point",
            "early:2200",
        )
        assert result.exit_code != 0
        assert "not a maturity" in result.output

    def test_the_same_name_twice(self, runner: CliRunner, register: str) -> None:
        fit(runner, register)
        assert fit(runner, register).exit_code != 0  # type: ignore[attr-defined]

    def test_curves(self, runner: CliRunner, register: str) -> None:
        fit(runner, register, "summer")
        fit(runner, register, "winter")
        result = run(runner, register, "maturity", "curves", "4000P-57")
        assert "summer" in result.output
        assert "winter" in result.output
        assert "fit" in result.output.splitlines()[0]


class CaseLogging:
    def test_one_reading(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "maturity",
            "log",
            "SN-1",
            "--placement",
            "Bay 4 slab",
            "--at",
            "2024-06-12T08:00",
            "--temp",
            "68",
        )
        assert result.exit_code == 0
        assert "SN-1" in result.output

    def test_the_same_moment_twice(self, runner: CliRunner, register: str) -> None:
        args = (
            "maturity",
            "log",
            "SN-1",
            "--placement",
            "Bay 4 slab",
            "--at",
            "2024-06-12T08:00",
            "--temp",
            "68",
        )
        run(runner, register, *args)
        assert run(runner, register, *args).exit_code != 0

    def test_a_history(self, runner: CliRunner, register: str) -> None:
        log(runner, register)
        result = run(runner, register, "maturity", "history", "SN-1")
        assert "temperature time factor" in result.output
        assert "equivalent age" in result.output

    def test_a_sensor_with_one_reading(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "maturity",
            "log",
            "SN-1",
            "--placement",
            "Bay 4 slab",
            "--at",
            "2024-06-12T08:00",
            "--temp",
            "68",
        )
        result = run(runner, register, "maturity", "history", "SN-1")
        assert result.exit_code != 0
        assert "fewer than two readings" in result.output


class CaseEstimate:
    def test_it_reads_a_strength(self, runner: CliRunner, register: str) -> None:
        fit(runner, register)
        log(runner, register)
        result = run(
            runner,
            register,
            "maturity",
            "estimate",
            "4000P-57",
            "--name",
            "summer",
            "--sensor",
            "SN-1",
        )
        assert result.exit_code == 0
        assert "gives" in result.output

    def test_a_history_past_the_curve_is_an_error(
        self, runner: CliRunner, register: str
    ) -> None:
        fit(runner, register)
        log(runner, register, hours=48, temp=110.0)
        result = run(
            runner,
            register,
            "maturity",
            "estimate",
            "4000P-57",
            "--name",
            "summer",
            "--sensor",
            "SN-1",
        )
        assert result.exit_code != 0
        assert "past the range" in result.output

    def test_an_unknown_curve(self, runner: CliRunner, register: str) -> None:
        log(runner, register)
        result = run(
            runner,
            register,
            "maturity",
            "estimate",
            "4000P-57",
            "--name",
            "winter",
            "--sensor",
            "SN-1",
        )
        assert result.exit_code != 0

    def test_a_sensor_with_no_readings(self, runner: CliRunner, register: str) -> None:
        fit(runner, register)
        result = run(
            runner,
            register,
            "maturity",
            "estimate",
            "4000P-57",
            "--name",
            "summer",
            "--sensor",
            "SN-9",
        )
        assert result.exit_code != 0
        assert "fewer than two readings" in result.output
