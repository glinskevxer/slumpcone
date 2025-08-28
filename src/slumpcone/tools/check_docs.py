"""Refusing a build whose command reference has drifted from the commands.

The reference is generated, which means it can be regenerated, which means
nobody will. Somebody adds an option, the file on disk keeps saying what the
command used to take, and the next person to read it is a technician who does
not know it is stale.

So this regenerates it in memory and compares. It never writes: a check that
fixes what it finds passes on a machine and fails in CI, or worse, passes in CI
by rewriting a file nobody committed. It prints what changed and exits non zero,
and the fix is one command that the message names.

The diff is unified and trimmed to the first few hunks, because the useful
information is which command moved, not the whole file.
"""

from __future__ import annotations

import difflib
import sys
from collections.abc import Sequence
from pathlib import Path

from slumpcone.cli.main import cli
from slumpcone.tools.command_reference import render_reference

REFERENCE = Path("docs/commands.md")
REGENERATE = "slumpcone register reference --out docs/commands.md"

# How many diff lines are worth printing before the point is made.
DIFF_LINES = 60


def expected_reference() -> str:
    """What the file should say, generated from the commands."""
    return render_reference(cli)


def difference(on_disk: str, expected: str) -> tuple[str, ...]:
    """The unified diff, or nothing if the two agree."""
    if on_disk == expected:
        return ()
    return tuple(
        difflib.unified_diff(
            on_disk.splitlines(),
            expected.splitlines(),
            fromfile="docs/commands.md",
            tofile="generated",
            lineterm="",
        )
    )


def check(path: Path = REFERENCE) -> tuple[int, tuple[str, ...]]:
    """Compare the file on disk against the commands.

    Returns the exit code and the lines to print. A missing file is a failure
    rather than a reason to write one.
    """
    expected = expected_reference()
    if not path.exists():
        return (1, (f"{path} is not there. Run: {REGENERATE}",))
    lines = difference(path.read_text(encoding="utf-8"), expected)
    if not lines:
        return (0, (f"{path} matches the commands",))
    shown = list(lines[:DIFF_LINES])
    if len(lines) > DIFF_LINES:
        shown.append(f"... and {len(lines) - DIFF_LINES} more line(s)")
    shown.append("")
    shown.append(f"the reference has drifted. Run: {REGENERATE}")
    return (1, tuple(shown))


def main(argv: Sequence[str] | None = None) -> int:
    """Print the verdict and give back an exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else REFERENCE
    code, lines = check(path)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
