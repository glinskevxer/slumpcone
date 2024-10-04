from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from slumpcone.cli.common import CliContext, parse_day, parse_moment
from slumpcone.cli.main import cli
from slumpcone.store.migrations import load_migrations


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class CaseContext:
    def test_it_opens_a_register(self, tmp_path: Path) -> None:
        context = CliContext(tmp_path / "register.sqlite3")
        with context.register() as register:
            assert register.health().is_current

    def test_quiet_suppresses_progress(self, tmp_path: Path, capsys: object) -> None:
        CliContext(tmp_path / "r.sqlite3", quiet=True).say("hello")
        CliContext(tmp_path / "r.sqlite3").say("world")
        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert "hello" not in captured.out
        assert "world" in captured.out


class CaseParsing:
    def test_parse_day(self) -> None:
        assert parse_day("2024-06-12") == date(2024, 6, 12)

    def test_a_bad_day_is_a_usage_error(self) -> None:
        with pytest.raises(Exception, match="YYYY-MM-DD"):
            parse_day("12/06/2024")

    def test_parse_moment(self) -> None:
        assert parse_moment("2024-06-12T07:42").hour == 7

    def test_a_bare_date_becomes_midnight(self) -> None:
        assert parse_moment("2024-06-12").hour == 0

    def test_a_bad_moment_is_a_usage_error(self) -> None:
        with pytest.raises(Exception, match="YYYY-MM-DD"):
            parse_moment("never")


class CaseTopLevel:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Ready-mix concrete" in result.output
        assert "register" in result.output

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "slumpcone" in result.output

    def test_the_short_help_flag(self, runner: CliRunner) -> None:
        assert runner.invoke(cli, ["-h"]).exit_code == 0


class CaseRegisterGroup:
    def invoke(self, runner: CliRunner, tmp_path: Path, *args: str) -> object:
        return runner.invoke(cli, ["--register", str(tmp_path / "r.sqlite3"), *args])

    def test_init_creates_the_file(self, runner: CliRunner, tmp_path: Path) -> None:
        result = self.invoke(runner, tmp_path, "register", "init")
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert (tmp_path / "r.sqlite3").exists()
        assert "schema version" in result.output  # type: ignore[attr-defined]

    def test_check_passes_on_a_fresh_register(self, runner: CliRunner, tmp_path: Path) -> None:
        self.invoke(runner, tmp_path, "register", "init")
        result = self.invoke(runner, tmp_path, "register", "check")
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert f"schema {len(load_migrations())} is current" in result.output  # type: ignore[attr-defined]

    def test_info_lists_the_tables(self, runner: CliRunner, tmp_path: Path) -> None:
        result = self.invoke(runner, tmp_path, "register", "info")
        assert "material" in result.output  # type: ignore[attr-defined]
        assert "rows" in result.output  # type: ignore[attr-defined]

    def test_the_environment_variable_is_used(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "from-env.sqlite3"
        monkeypatch.setenv("SLUMPCONE_REGISTER", str(target))
        result = runner.invoke(cli, ["register", "init"])
        assert result.exit_code == 0
        assert target.exists()

    def test_the_option_beats_the_environment(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SLUMPCONE_REGISTER", str(tmp_path / "from-env.sqlite3"))
        chosen = tmp_path / "chosen.sqlite3"
        runner.invoke(cli, ["--register", str(chosen), "register", "init"])
        assert chosen.exists()
        assert not (tmp_path / "from-env.sqlite3").exists()

    def test_a_broken_register_is_reported_as_one_line(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        self.invoke(runner, tmp_path, "register", "init")
        import sqlite3

        connection = sqlite3.connect(str(tmp_path / "r.sqlite3"))
        connection.execute("UPDATE schema_migration SET checksum = 'x' WHERE version = 1")
        connection.commit()
        connection.close()
        result = self.invoke(runner, tmp_path, "register", "check")
        assert result.exit_code != 0  # type: ignore[attr-defined]
        assert "edited since" in result.output  # type: ignore[attr-defined]
        assert "Traceback" not in result.output  # type: ignore[attr-defined]
