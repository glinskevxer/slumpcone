from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run


def add_plant(runner: CliRunner, register: str, code: str = "PL-1") -> Result:
    return run(
        runner,
        register,
        "plant",
        "add",
        code,
        "Northmoor batch plant",
        "--max-load",
        "11 yd3",
        "--certified-to",
        "2025-01-31",
        "--location",
        "Ashfield",
    )


def add_scale(runner: CliRunner, register: str) -> Result:
    return run(
        runner,
        register,
        "plant",
        "scale",
        "PL-1",
        "SC-CEM",
        "Cement scale",
        "--capacity",
        "6000 lb",
        "--graduation",
        "1 lb",
        "--weighs",
        "cement,scm",
        "--calibrated",
        "2024-03-01",
    )


def add_silo(runner: CliRunner, register: str) -> Result:
    return run(
        runner,
        register,
        "plant",
        "silo",
        "PL-1",
        "SI-1",
        "Cement silo one",
        "--material",
        "CEM-I",
        "--capacity",
        "200000 lb",
        "--level",
        "120000 lb",
        "--low",
        "30000 lb",
    )


class CasePlant:
    def test_add(self, runner: CliRunner, register: str) -> None:
        result = add_plant(runner, register)
        assert result.exit_code == 0
        assert "PL-1" in result.output
        assert "at Ashfield" in result.output

    def test_an_unknown_unit_system(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "plant", "add", "PL-1", "X", "--system", "cgs")
        assert result.exit_code != 0
        assert "unit system" in result.output

    def test_list(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        result = run(runner, register, "plant", "list", "--on", "2024-06-12")
        assert "PL-1" in result.output
        assert "operable" in result.output

    def test_show(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        result = run(runner, register, "plant", "show", "pl 1", "--on", "2024-06-12")
        assert "Northmoor batch plant" in result.output
        assert "max load" in result.output
        assert "operable" in result.output

    def test_show_an_unknown_plant(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "plant", "show", "PL-9")
        assert result.exit_code != 0
        assert "no plant on file" in result.output

    def test_adding_again_keeps_the_scales(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        add_scale(runner, register)
        add_plant(runner, register)
        result = run(runner, register, "plant", "show", "PL-1")
        assert "SC-CEM" in result.output


class CaseScale:
    def test_add(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        result = add_scale(runner, register)
        assert result.exit_code == 0
        assert "SC-CEM" in result.output
        assert "6000 lb capacity" in result.output

    def test_it_shows_up_on_the_plant(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        add_scale(runner, register)
        result = run(runner, register, "plant", "show", "PL-1", "--on", "2024-06-12")
        assert "Scales" in result.output
        assert "SC-CEM" in result.output

    def test_adding_the_same_code_replaces_it(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        add_scale(runner, register)
        add_scale(runner, register)
        result = run(runner, register, "plant", "show", "PL-1")
        assert "1 scales" in result.output

    def test_an_overdue_scale_blocks_the_plant(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        add_scale(runner, register)
        result = run(runner, register, "plant", "show", "PL-1", "--on", "2025-06-12")
        assert "operable" in result.output
        assert "calibration lapsed" in result.output

    def test_an_unknown_material_class(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        result = run(
            runner,
            register,
            "plant",
            "scale",
            "PL-1",
            "SC-X",
            "X",
            "--capacity",
            "6000 lb",
            "--graduation",
            "1 lb",
            "--weighs",
            "gravel-ish",
            "--calibrated",
            "2024-03-01",
        )
        assert result.exit_code != 0


class CaseSilo:
    def test_add(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        result = add_silo(runner, register)
        assert result.exit_code == 0
        assert "SI-1" in result.output
        assert "CEM-I" in result.output

    def test_list(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        add_silo(runner, register)
        result = run(runner, register, "plant", "silos", "PL-1")
        assert "SI-1" in result.output
        assert "working" in result.output

    def test_a_silo_on_an_unknown_plant(self, runner: CliRunner, register: str) -> None:
        result = add_silo(runner, register)
        assert result.exit_code != 0

    def test_an_over_full_silo_is_refused(self, runner: CliRunner, register: str) -> None:
        add_plant(runner, register)
        result = run(
            runner,
            register,
            "plant",
            "silo",
            "PL-1",
            "SI-1",
            "Silo",
            "--material",
            "CEM-I",
            "--capacity",
            "100 lb",
            "--level",
            "200 lb",
        )
        assert result.exit_code != 0
        assert "above the" in result.output
