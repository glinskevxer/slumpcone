"""The one helper the command line tests all call.

It is a module rather than a fixture because half the tests call it from a
helper of their own, and a fixture cannot be reached from there without
threading it through every signature.
"""

from __future__ import annotations

from click.testing import CliRunner, Result

from slumpcone.cli.main import cli


def run(runner: CliRunner, register: str, *args: str) -> Result:
    """Run the command line against a register path."""
    return runner.invoke(cli, ["--register", register, *args])
