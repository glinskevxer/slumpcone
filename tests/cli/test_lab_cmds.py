from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from slumpcone.cli.main import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def register(tmp_path: Path) -> str:
    return str(tmp_path / "r.sqlite3")


def run(runner: CliRunner, register: str, *args: str) -> Result:
    return runner.invoke(cli, ["--register", register, *args])


def open_set(runner: CliRunner, register: str, code: str = "S-4471", **extra: str) -> Result:
    args = [
        "lab",
        "set",
        code,
        "--mix",
        "4000P-57",
        "--sampled",
        "2024-06-12T09:20",
        "--size",
        "6x12",
        "--ticket",
        "881204",
        "--project",
        "Route 9 shoulder",
    ]
    for key, value in extra.items():
        args.extend([f"--{key}", value])
    return run(runner, register, *args)


def cast(runner: CliRunner, register: str, code: str, set_code: str = "S-4471") -> Result:
    return run(
        runner,
        register,
        "lab",
        "cylinder",
        code,
        "--set",
        set_code,
        "--ticket",
        "881204",
        "--cast",
        "2024-06-12T09:20",
        "--size",
        "6x12",
    )


def break_it(
    runner: CliRunner, register: str, code: str, load: str = "141000 lbf", **extra: str
) -> Result:
    args = [
        "lab",
        "break",
        code,
        "--tested",
        "2024-07-10T10:15",
        "--age",
        "28",
        "--d1",
        "6.00 in",
        "--d2",
        "6.00 in",
        "--length",
        "12.00 in",
        "--load",
        load,
    ]
    for key, value in extra.items():
        args.extend([f"--{key}", value])
    return run(runner, register, *args)


class CaseSets:
    def test_open(self, runner: CliRunner, register: str) -> None:
        result = open_set(runner, register)
        assert result.exit_code == 0
        assert "S-4471 opened against 4000P-57 r1" in result.output

    def test_opening_twice(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        result = open_set(runner, register)
        assert result.exit_code != 0
        assert "already on file" in result.output

    def test_an_unknown_size(self, runner: CliRunner, register: str) -> None:
        result = open_set(runner, register, size="3x6")
        assert result.exit_code != 0
        assert "specimen size" in result.output


class CaseCylinders:
    def test_cast_one(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        result = cast(runner, register, "C-4471-A")
        assert result.exit_code == 0
        assert "C-4471-A" in result.output
        assert "due 2024-07-10" in result.output

    def test_a_cylinder_needs_its_set(self, runner: CliRunner, register: str) -> None:
        result = cast(runner, register, "C-4471-A")
        assert result.exit_code != 0

    def test_the_same_cylinder_twice(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = cast(runner, register, "C-4471-A")
        assert result.exit_code != 0

    def test_pending(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = run(runner, register, "lab", "pending", "--on", "2024-07-11")
        assert "C-4471-A" in result.output

    def test_nothing_pending_yet(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = run(runner, register, "lab", "pending", "--on", "2024-06-20")
        assert "C-4471-A" not in result.output


class CaseBreaks:
    def test_record_one(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = break_it(runner, register, "C-4471-A")
        assert result.exit_code == 0
        assert "C-4471-A" in result.output
        assert "psi" in result.output

    def test_a_break_needs_its_cylinder(self, runner: CliRunner, register: str) -> None:
        result = break_it(runner, register, "C-4471-A")
        assert result.exit_code != 0

    def test_an_out_of_round_cylinder_is_called_out(
        self, runner: CliRunner, register: str
    ) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = run(
            runner,
            register,
            "lab",
            "break",
            "C-4471-A",
            "--tested",
            "2024-07-10T10:15",
            "--age",
            "28",
            "--d1",
            "6.20 in",
            "--d2",
            "6.00 in",
            "--length",
            "12 in",
            "--load",
            "141000 lbf",
        )
        assert "should not have been tested" in result.output

    def test_one_diameter_is_taken_as_round(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = run(
            runner,
            register,
            "lab",
            "break",
            "C-4471-A",
            "--tested",
            "2024-07-10T10:15",
            "--age",
            "28",
            "--d1",
            "6.00 in",
            "--load",
            "141000 lbf",
        )
        assert result.exit_code == 0

    def test_an_unknown_fracture(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        cast(runner, register, "C-4471-A")
        result = break_it(runner, register, "C-4471-A", fracture="crumbled")
        assert result.exit_code != 0


class CaseStrength:
    def stock(self, runner: CliRunner, register: str, set_code: str, load: str) -> None:
        open_set(runner, register, set_code)
        for letter in ("A", "B"):
            cast(runner, register, f"C-{set_code}-{letter}", set_code)
            break_it(runner, register, f"C-{set_code}-{letter}", load)

    def test_a_set_adds_up_to_a_test(self, runner: CliRunner, register: str) -> None:
        self.stock(runner, register, "S-4471", "141000 lbf")
        result = run(runner, register, "lab", "test", "S-4471")
        assert "result" in result.output
        assert "counts for acceptance" in result.output

    def test_a_set_with_no_breaks(self, runner: CliRunner, register: str) -> None:
        open_set(runner, register)
        result = run(runner, register, "lab", "test", "S-4471")
        assert result.exit_code != 0

    def test_the_strength_record(self, runner: CliRunner, register: str) -> None:
        for index, code in enumerate(("S-1", "S-2", "S-3")):
            self.stock(runner, register, code, f"{141000 + index * 1000} lbf")
        result = run(runner, register, "lab", "strength", "4000P-57", "--specified", "4000 psi")
        assert "Strength record for 4000P-57" in result.output
        assert "satisfactory" in result.output

    def test_a_record_with_nothing_in_it(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "lab", "strength", "4000P-57", "--specified", "4000 psi")
        assert "not_enough_tests" in result.output

    def test_by_project(self, runner: CliRunner, register: str) -> None:
        self.stock(runner, register, "S-4471", "141000 lbf")
        result = run(
            runner,
            register,
            "lab",
            "project-strength",
            "Route 9 shoulder",
            "--specified",
            "4000 psi",
        )
        assert "Strength record for Route 9 shoulder" in result.output
