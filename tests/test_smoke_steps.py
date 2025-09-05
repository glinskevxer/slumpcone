"""Every smoke step has to be a command that exists and works.

The steps used to live in a `run:` block in the workflow, where nothing could
reach them. Two of them were wrong for the whole build and its first execution
failed on line two. Driving the same tuple in process here means a command that
is renamed, or an option that moves, fails in the suite in a second rather than
on a runner four minutes in.

This is not a replacement for the CI smoke job, which installs the wheel into a
clean interpreter and is the only thing that catches a file the package forgot
to ship. It is the fast half of the same check.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from slumpcone.cli.main import cli
from slumpcone.tools.smoke import EXPECTED_NONZERO, SMOKE_STEPS, check_import


@pytest.fixture(scope="class")
def seeded_register(tmp_path_factory: pytest.TempPathFactory) -> str:
    """One register, seeded once, that the whole ordered sequence runs against."""
    path = str(tmp_path_factory.mktemp("smoke") / "r.sqlite3")
    runner = CliRunner()
    for step in (("register", "init"), ("demo", "seed")):
        result = runner.invoke(cli, ["--register", path, *step])
        assert result.exit_code == 0, result.output
    return path


class CaseEveryStepIsARealCommand:
    def test_the_sequence_is_not_empty(self) -> None:
        assert len(SMOKE_STEPS) > 15

    def test_it_starts_by_creating_the_register(self) -> None:
        # The order is load bearing: everything after reads what the seed wrote.
        assert ("register", "init") in SMOKE_STEPS
        assert SMOKE_STEPS.index(("register", "init")) < SMOKE_STEPS.index(("demo", "seed"))

    @pytest.mark.parametrize("step", [s for s in SMOKE_STEPS if s[0] != "--version"])
    def test_the_group_and_command_resolve(self, step: tuple[str, ...]) -> None:
        # Catches a renamed command without running anything.
        result = CliRunner().invoke(cli, [*step[: 2 if len(step) > 1 else 1], "--help"])
        assert result.exit_code == 0, f"{' '.join(step)} does not resolve: {result.output}"

    @pytest.mark.parametrize("step", SMOKE_STEPS)
    def test_it_runs_clean(self, step: tuple[str, ...], seeded_register: str) -> None:
        if step in (("register", "init"), ("demo", "seed")):
            pytest.skip("done by the fixture")
        result = CliRunner().invoke(cli, ["--register", seeded_register, *step])
        assert result.exit_code == 0, f"{' '.join(step)} -> {result.exit_code}\n{result.output}"

    @pytest.mark.parametrize(("step", "expected"), list(EXPECTED_NONZERO.items()))
    def test_the_deliberate_failures_fail_deliberately(
        self, step: tuple[str, ...], expected: int, seeded_register: str
    ) -> None:
        # The demo plant carries a failed probe on purpose, so the doctor must
        # come back non-zero. A zero here would mean the doctor stopped looking.
        result = CliRunner().invoke(cli, ["--register", seeded_register, *step])
        assert result.exit_code == expected, result.output


class CaseTheTwoBugsThisWouldHaveCaught:
    def test_the_profiles_attribute_is_named_profiles(self) -> None:
        from slumpcone.ingest import profiles

        assert hasattr(profiles, "PROFILES")
        assert not hasattr(profiles, "BUILT_IN"), "the smoke script asked for BUILT_IN"

    def test_lab_strength_takes_the_mix_positionally(self, seeded_register: str) -> None:
        good = CliRunner().invoke(
            cli,
            [
                "--register",
                seeded_register,
                "lab",
                "strength",
                "4000P-57",
                "--specified",
                "4000 psi",
            ],
        )
        assert good.exit_code == 0, good.output
        bad = CliRunner().invoke(
            cli, ["--register", seeded_register, "lab", "strength", "--mix", "4000P-57"]
        )
        assert bad.exit_code != 0, "the old smoke spelling should not work"

    def test_the_import_check_passes(self) -> None:
        assert check_import() == 0

    def test_the_import_check_sees_the_migrations(self) -> None:
        from slumpcone.store.migrations import load_migrations

        # The wheel has to carry the .sql files; this is what proves it locally.
        assert len(load_migrations()) >= 27
