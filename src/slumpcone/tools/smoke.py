"""The end to end sequence, as data rather than as shell in a YAML file.

This exists because the smoke steps were a `run:` block in the workflow, and a
`run:` block is the one part of a repository that nothing can test. It sat there
for the whole build carrying two commands that do not exist -- an attribute
`profiles.BUILT_IN` that was never called that, and `lab strength --mix CODE`
when the command takes the mixture as a positional argument and requires
`--specified`. Neither could have been caught, because the smoke job only runs
once every other job passes, and until the pins were fixed they never did. Its
very first execution failed on line two.

So the sequence lives here, once, as a tuple of argv lists. The workflow calls
this module against the installed wheel, which is the real check: a clean
interpreter, nothing from the source tree on the path, only what the package
shipped. And `tests/test_smoke_steps.py` drives the same tuple in process, so a
command that stops existing fails in the suite in a second rather than in CI in
four minutes.

The steps are ordered and stateful on purpose. `register init` has to precede
`demo seed`, and everything after reads what the seed wrote, so this is also the
only place the whole surface is exercised against one register in one order.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

DEMO_DAY = "2024-06-12"
DEMO_MIX = "4000P-57"
DEMO_PLANT = "PL-1"

# Every step is argv after the program name. Keep the order: it is a story.
SMOKE_STEPS: tuple[tuple[str, ...], ...] = (
    ("--version",),
    ("register", "init"),
    ("demo", "seed"),
    ("register", "info"),
    ("register", "verify"),
    ("register", "plans"),
    ("register", "versions", "--one-line"),
    ("mix", "check", DEMO_MIX),
    ("batch", "audit", "--from", DEMO_DAY, "--to", DEMO_DAY),
    ("batch", "print", "881204"),
    ("lab", "strength", DEMO_MIX, "--specified", "4000 psi"),
    ("report", "production", "--from", DEMO_DAY, "--to", DEMO_DAY),
    ("report", "compliance", "--on", DEMO_DAY),
    ("report", "day", "--on", DEMO_DAY),
    ("report", "utilisation", "--from", DEMO_DAY, "--to", DEMO_DAY),
    ("carbon", "mix", DEMO_MIX),
    ("crew", "gaps", "--on", DEMO_DAY),
    ("probe", "list", "--plant", DEMO_PLANT, "--on", DEMO_DAY),
    ("reclaim", "yard", "--on", DEMO_DAY),
    ("dispatch", "profiles"),
    ("audit", "verify"),
)

# Steps that are expected to leave non-zero because the demo plant deliberately
# carries a failing probe and a card about to run out. Running them still
# matters: the exit code is the assertion.
EXPECTED_NONZERO: dict[tuple[str, ...], int] = {
    ("register", "doctor", "--on", DEMO_DAY): 1,
}


def check_import() -> int:
    """Prove the package shipped what it declares, not just that it imports."""
    from slumpcone.ingest import profiles
    from slumpcone.store.migrations import load_migrations

    assert profiles.PROFILES, "no mapping profiles shipped"
    assert load_migrations(), "no migration scripts shipped -- check the wheel artifacts"
    print(f"profiles={len(profiles.PROFILES)} migrations={len(load_migrations())}")
    return 0


def run_step(program: Sequence[str], step: Sequence[str]) -> tuple[int, str]:
    """Run one step and hand back its code and combined output."""
    done = subprocess.run([*program, *step], capture_output=True, text=True, check=False)
    return done.returncode, (done.stdout + done.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Drive the whole sequence against an installed slumpcone."""
    args = list(sys.argv[1:] if argv is None else argv)
    program = [args[0]] if args else [sys.executable, "-m", "slumpcone"]
    failures = 0

    print(f"--- import check ({Path(sys.executable).name})")
    check_import()

    for step in SMOKE_STEPS:
        code, out = run_step(program, step)
        mark = "ok  " if code == 0 else "FAIL"
        print(f"{mark} slumpcone {' '.join(step)}")
        if code != 0:
            failures += 1
            print("\n".join("       " + line for line in out.splitlines()[:12]))

    for step, expected in EXPECTED_NONZERO.items():
        code, out = run_step(program, step)
        mark = "ok  " if code == expected else "FAIL"
        print(f"{mark} slumpcone {' '.join(step)}  (expected exit {expected}, got {code})")
        if code != expected:
            failures += 1

    total = len(SMOKE_STEPS) + len(EXPECTED_NONZERO)
    print(f"\n{total - failures} of {total} step(s) as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
