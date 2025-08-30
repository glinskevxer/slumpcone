from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from slumpcone.cli.common import ACTOR_ENV, REGISTER_ENV
from slumpcone.cli.main import cli
from tests.cli.support import run

GOOD = """
[register]
path = "plant.sqlite3"

[defaults]
plant = "PL-1"
actor = "j.mercer"
"""

ODD = """
[defaults]
actor = "j.mercer"
wobble = "yes"
"""


@pytest.fixture()
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with nothing in it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(REGISTER_ENV, raising=False)
    monkeypatch.delenv(ACTOR_ENV, raising=False)
    return tmp_path


class CaseReadingIt:
    def test_nothing_on_disk(self, runner: CliRunner, here: Path) -> None:
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "none found" in result.output

    def test_the_file_is_found(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["config", "show"])
        assert "slumpcone.toml" in result.output
        assert "j.mercer" in result.output

    def test_the_register_comes_from_the_file(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["config", "show"])
        assert "plant.sqlite3" in result.output

    def test_the_option_beats_the_file(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["--register", "other.sqlite3", "config", "show"])
        assert "other.sqlite3" in result.output

    def test_the_environment_beats_the_file(
        self, runner: CliRunner, here: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        monkeypatch.setenv(REGISTER_ENV, "env.sqlite3")
        result = runner.invoke(cli, ["config", "show"])
        assert "env.sqlite3" in result.output

    def test_the_actor_comes_from_the_file(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["config", "show"])
        line = [row for row in result.output.splitlines() if "actor in use" in row][0]
        assert line.endswith("j.mercer")

    def test_the_actor_option_still_wins(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["--actor", "k.abara", "config", "show"])
        assert "k.abara" in result.output

    def test_the_path_command(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code == 0
        assert "slumpcone.toml" in result.output

    def test_the_path_command_with_no_file(self, runner: CliRunner, here: Path) -> None:
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code != 0
        assert "no slumpcone.toml" in result.output


class CaseKeysNobodyKnows:
    def test_show_warns_and_fails(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(ODD)
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code != 0
        assert "defaults.wobble" in result.output

    def test_the_warning_goes_to_stderr_on_every_command(
        self, runner: CliRunner, here: Path
    ) -> None:
        (here / "slumpcone.toml").write_text(ODD)
        result = runner.invoke(cli, ["config", "path"], catch_exceptions=False)
        assert "does not know" in result.output

    def test_quiet_stops_the_warning(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(ODD)
        result = runner.invoke(cli, ["--quiet", "config", "path"])
        assert "does not know" not in result.output

    def test_check_lists_them(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(ODD)
        result = runner.invoke(cli, ["config", "check"])
        assert result.exit_code != 0
        assert "unknown: defaults.wobble" in result.output

    def test_check_passes_on_a_good_file(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text(GOOD)
        result = runner.invoke(cli, ["config", "check"])
        assert result.exit_code == 0
        assert "every key" in result.output

    def test_a_broken_file_does_not_stop_a_command(self, runner: CliRunner, here: Path) -> None:
        (here / "slumpcone.toml").write_text("this is not toml at all [[[")
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "built in defaults" in result.output


class CaseWritingIt:
    def test_it_writes_a_file(self, runner: CliRunner, here: Path) -> None:
        result = runner.invoke(cli, ["config", "init"])
        assert result.exit_code == 0
        assert (here / "slumpcone.toml").exists()

    def test_the_file_reads_back(self, runner: CliRunner, here: Path) -> None:
        runner.invoke(cli, ["config", "init", "--plant", "PL-1"])
        result = runner.invoke(cli, ["config", "check"])
        assert result.exit_code == 0

    def test_the_plant_lands_in_it(self, runner: CliRunner, here: Path) -> None:
        runner.invoke(cli, ["config", "init", "--plant", "PL-1"])
        assert 'plant = "PL-1"' in (here / "slumpcone.toml").read_text()

    def test_the_actor_lands_in_it(self, runner: CliRunner, here: Path) -> None:
        runner.invoke(cli, ["config", "init", "--actor", "j.mercer"])
        assert 'actor = "j.mercer"' in (here / "slumpcone.toml").read_text()

    def test_it_will_not_overwrite(self, runner: CliRunner, here: Path) -> None:
        runner.invoke(cli, ["config", "init"])
        result = runner.invoke(cli, ["config", "init"])
        assert result.exit_code != 0
        assert "already there" in result.output

    def test_force_writes_over(self, runner: CliRunner, here: Path) -> None:
        runner.invoke(cli, ["config", "init"])
        assert runner.invoke(cli, ["config", "init", "--force"]).exit_code == 0

    def test_it_can_be_written_elsewhere(self, runner: CliRunner, here: Path) -> None:
        runner.invoke(cli, ["config", "init", "--out", "other.toml"])
        assert (here / "other.toml").exists()


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "config" in run(runner, register, "--help").output
