from __future__ import annotations

from pathlib import Path

import pytest

from slumpcone import __version__
from slumpcone.register import Register
from slumpcone.store.migrations import load_migrations
from slumpcone.versions import Versions, collect


class CaseCollecting:
    def test_without_a_register(self) -> None:
        found = collect()
        assert found.package == __version__
        assert found.python
        assert found.sqlite
        assert found.migrations_known == len(load_migrations())

    def test_no_register_lines_when_there_is_none(self) -> None:
        labels = [label for label, _ in collect().as_pairs()]
        assert "register" not in labels

    def test_a_register_that_is_not_there_yet(self, tmp_path: Path) -> None:
        found = collect(tmp_path / "nope.sqlite3")
        assert found.register_version is None
        assert found.register_is_current is None
        assert found.register_standing == "no register read"

    def test_the_path_still_shows(self, tmp_path: Path) -> None:
        found = collect(tmp_path / "nope.sqlite3")
        labels = dict(found.as_pairs())
        assert "register" in labels
        assert labels["register schema"] == "not created yet"

    def test_a_real_register_reads_current(self, tmp_path: Path) -> None:
        path = tmp_path / "r.sqlite3"
        Register.open(path).close()
        found = collect(path)
        assert found.register_version == len(load_migrations())
        assert found.register_is_current
        assert found.register_standing == "current"

    def test_a_file_that_is_not_a_register(self, tmp_path: Path) -> None:
        junk = tmp_path / "junk.sqlite3"
        junk.write_text("not a database")
        found = collect(junk)
        assert found.register_version is None
        assert found.register_standing == "no register read"


class CaseStanding:
    def build(self, known: int, on_disk: int | None) -> Versions:
        return Versions("1.0.0", "3.12.0", "3.45.0", "Linux x86_64", known, "r", on_disk)

    def test_the_same_number_is_current(self) -> None:
        assert self.build(27, 27).register_standing == "current"

    def test_an_older_register_says_how_far_behind(self) -> None:
        assert "3 migration(s) behind" in self.build(27, 24).register_standing

    def test_a_newer_register_says_so(self) -> None:
        assert "newer build" in self.build(27, 30).register_standing

    def test_behind_and_ahead_are_told_apart(self) -> None:
        assert not self.build(27, 24).register_is_current
        assert not self.build(27, 30).register_is_current

    def test_one_behind_reads_singular_enough(self) -> None:
        assert "1 migration(s)" in self.build(27, 26).register_standing


class CaseDescribing:
    def test_one_line_has_the_four_numbers(self) -> None:
        text = collect().describe()
        assert __version__ in text
        assert "python" in text
        assert "sqlite" in text
        assert "schema" in text

    def test_the_pairs_start_with_the_package(self) -> None:
        assert collect().as_pairs()[0][0] == "slumpcone"


@pytest.mark.parametrize("one_line", [True, False])
def test_the_command(tmp_path: Path, one_line: bool) -> None:
    from click.testing import CliRunner

    from slumpcone.cli.main import cli

    path = tmp_path / "r.sqlite3"
    Register.open(path).close()
    args = ["--register", str(path), "register", "versions"]
    if one_line:
        args.append("--one-line")
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0
    assert __version__ in result.output
