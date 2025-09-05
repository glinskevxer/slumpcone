"""The declared dev pins have to be the tools actually running.

This exists because they were not, for a hundred and eighty commits, and nothing
could have noticed. `check.sh` invokes ruff, mypy and pytest out of the
virtualenv directly; it never installs `.[dev]`. So the pins in `pyproject.toml`
were written once at the start and then described nothing. CI was the first
thing that ever read them, and it installed ruff 0.2.1 against a tree formatted
by 0.9.6 (150 import-sorting errors), mypy 1.8.0 against code that type checks
under 1.15.0 (one error), and no pytest-cov at all, so `--cov` was an
unrecognised argument.

The lesson is the project's own: a verification step that does not name exactly
what ships is not a verification step. These tests make the declaration and the
running tool the same claim, so the next drift fails here rather than on a
runner.

They compare against what is installed in the environment running the suite. On
a machine where the dev extra was installed properly that is a tautology, which
is the point: the tautology is the thing that was false.
"""

from __future__ import annotations

import importlib.metadata
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Tools whose version changes what "passes" means. A drift in any of these
# silently changes the verdict of the gate rather than breaking it loudly.
GATEKEEPERS = ("pytest", "pytest-cov", "coverage", "ruff", "mypy")


def declared() -> dict[str, str]:
    """The dev extra, as {distribution: exact version}."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pins: dict[str, str] = {}
    for entry in project["optional-dependencies"]["dev"]:
        match = re.fullmatch(r"([A-Za-z0-9._-]+)==([0-9][0-9A-Za-z.+-]*)", entry.strip())
        assert match, f"dev pin {entry!r} is not an exact ==pin"
        pins[match.group(1).lower()] = match.group(2)
    return pins


def installed(distribution: str) -> str | None:
    """What is actually importable, or nothing if it is not there."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


class CaseTheDeclarationIsExact:
    def test_every_dev_dependency_is_pinned_exactly(self) -> None:
        # A range here is how CI ends up on a different tool from the developer.
        assert declared()

    def test_the_build_backend_is_pinned_too(self) -> None:
        raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(r'requires = \["hatchling==[0-9]', raw)

    def test_the_runtime_dependency_is_pinned(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        for entry in project["dependencies"]:
            assert "==" in entry, f"{entry} is not an exact pin"


class CaseEveryGatekeeperIsDeclared:
    @pytest.mark.parametrize("tool", GATEKEEPERS)
    def test_it_appears_in_the_dev_extra(self, tool: str) -> None:
        # pytest-cov and coverage were the two missing ones, which is why
        # --cov was an unrecognised argument on the runner.
        assert tool in declared(), f"{tool} decides whether the gate passes and is not declared"

    @pytest.mark.parametrize("tool", GATEKEEPERS)
    def test_it_is_actually_installed(self, tool: str) -> None:
        assert installed(tool) is not None, f"{tool} is declared but not installed"


class CaseTheDeclarationMatchesReality:
    @pytest.mark.parametrize("tool", GATEKEEPERS)
    def test_the_pin_is_the_version_running(self, tool: str) -> None:
        pinned = declared().get(tool)
        running = installed(tool)
        if pinned is None or running is None:
            pytest.skip(f"{tool} not both declared and installed")
        assert running == pinned, (
            f"{tool} is pinned at {pinned} and {running} is running. "
            "Update the pin or the environment; do not let them disagree."
        )

    def test_nothing_is_declared_that_is_not_installed(self) -> None:
        missing = [name for name in declared() if installed(name) is None]
        assert missing == [], f"declared but absent: {missing}"


class CaseTheVersionsAreTheEarly2025Stack:
    """The project was built against early 2025 releases on purpose."""

    def test_python_floor(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        assert project["requires-python"] == ">=3.12"

    @pytest.mark.parametrize(
        ("tool", "expected"),
        [
            ("pytest", "8.3.4"),
            ("pytest-cov", "6.0.0"),
            ("coverage", "7.6.12"),
            ("ruff", "0.9.6"),
            ("mypy", "1.15.0"),
        ],
    )
    def test_the_pin_has_not_wandered(self, tool: str, expected: str) -> None:
        # Stated twice on purpose. A bump should be a deliberate edit in two
        # places, not something a resolver does on a runner.
        assert declared()[tool] == expected
