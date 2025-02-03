"""Fixtures every command line test needs.

The same three definitions were at the top of a dozen modules: a runner, a
throwaway register path, and a helper that puts ``--register`` in front of the
arguments. Repeated, they had already drifted -- two of them named the register
file differently, so a test that leaked state between them would have been
invisible.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from slumpcone.cli.main import cli


@pytest.fixture()
def runner() -> CliRunner:
    """A click runner, one per test."""
    return CliRunner()


@pytest.fixture()
def register(tmp_path: Path) -> str:
    """A register path in this test's own temporary directory."""
    return str(tmp_path / "r.sqlite3")


@pytest.fixture()
def invoke(runner: CliRunner, register: str) -> Callable[..., Result]:
    """Run the command line against this test's register."""

    def call(*args: str) -> Result:
        return runner.invoke(cli, ["--register", register, *args])

    return call
