from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run

DAY = "2024-06-12"


class CaseDoctor:
    def test_an_empty_register_is_well(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "register", "doctor", "--on", DAY)
        assert result.exit_code == 0
        assert "check(s) run" in result.output

    def test_the_demo_plant_has_a_bad_probe(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "register", "doctor", "--on", DAY)
        assert result.exit_code != 0
        assert "MP-2" in result.output
        assert "stop work" in result.output

    def test_it_warns_about_the_card(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "register", "doctor", "--on", DAY)
        assert "ACI-2044" in result.output

    def test_notes_are_hidden_by_default(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "register", "doctor", "--on", DAY)
        assert "no technicians on file" not in result.output

    def test_all_shows_them(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "register", "doctor", "--on", DAY, "--all")
        assert "no technicians on file" in result.output

    def test_fixing_the_probe_makes_it_well(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        run(
            runner,
            register,
            "probe",
            "check",
            "MP-2",
            "--plant",
            "PL-1",
            "--probe-read",
            "4.5",
            "--oven",
            "4.45",
            "--on",
            DAY,
        )
        result = run(runner, register, "register", "doctor", "--on", DAY)
        assert result.exit_code == 0
        assert "0 failure(s)" in result.output

    def test_it_still_warns_after_the_fix(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        run(
            runner,
            register,
            "probe",
            "check",
            "MP-2",
            "--plant",
            "PL-1",
            "--probe-read",
            "4.5",
            "--oven",
            "4.45",
            "--on",
            DAY,
        )
        result = run(runner, register, "register", "doctor", "--on", DAY)
        assert "warning(s)" in result.output
