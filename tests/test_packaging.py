from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from slumpcone import __version__

ROOT = Path(__file__).resolve().parents[1]


def pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class CaseVersion:
    def test_the_two_versions_agree(self) -> None:
        project = pyproject()["project"]
        assert isinstance(project, dict)
        assert project["version"] == __version__

    def test_it_is_a_release_version(self) -> None:
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_the_changelog_carries_it(self) -> None:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert f"## {__version__}" in text


class CaseWhatShips:
    def test_the_typing_marker_is_there(self) -> None:
        assert (ROOT / "src" / "slumpcone" / "py.typed").exists()

    def test_the_schema_scripts_are_declared(self) -> None:
        raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "store/schema/*.sql" in raw

    def test_the_marker_is_declared(self) -> None:
        raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "py.typed" in raw

    def test_every_migration_is_a_sql_file(self) -> None:
        schema = ROOT / "src" / "slumpcone" / "store" / "schema"
        assert all(path.suffix == ".sql" for path in schema.iterdir())

    def test_the_console_script_points_at_main(self) -> None:
        project = pyproject()["project"]
        assert isinstance(project, dict)
        scripts = project["scripts"]
        assert isinstance(scripts, dict)
        assert scripts["slumpcone"] == "slumpcone.cli.main:main"


class CaseRunningItAsAModule:
    def test_the_version_prints(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "slumpcone", "--version"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode == 0
        assert __version__ in result.stdout

    def test_the_help_prints(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "slumpcone", "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode == 0
        assert "Ready-mix concrete" in result.stdout

    def test_an_unknown_command_is_a_usage_error(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "slumpcone", "levitate"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode == 2


@pytest.mark.parametrize("field", ["name", "version", "description", "requires-python"])
def test_the_metadata_is_filled_in(field: str) -> None:
    project = pyproject()["project"]
    assert isinstance(project, dict)
    assert project.get(field)
