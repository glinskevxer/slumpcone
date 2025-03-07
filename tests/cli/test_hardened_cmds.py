from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


def add_beam(
    runner: CliRunner, register: str, code: str = "B-1", fracture: str = "9 in"
) -> object:
    return run(
        runner,
        register,
        "beam",
        "break",
        code,
        "--set",
        "S-4471",
        "--mix",
        "4000P-57",
        "--tested",
        "2024-07-10T10:15",
        "--load",
        "6200 lbf",
        "--fracture-at",
        fracture,
    )


def add_core(
    runner: CliRunner, register: str, code: str = "C-1", load: str = "45000 lbf"
) -> object:
    return run(
        runner,
        register,
        "core",
        "take",
        code,
        "--location",
        "Bay 4 slab",
        "--specified",
        "4000 psi",
        "--taken",
        "2024-08-01T09:00",
        "--length",
        "8 in",
        "--load",
        load,
    )


class CaseBeams:
    def test_record_one(self, runner: CliRunner, register: str) -> None:
        result = add_beam(runner, register)
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert "B-1" in result.output  # type: ignore[attr-defined]
        assert "middle third" in result.output  # type: ignore[attr-defined]

    def test_a_discarded_beam(self, runner: CliRunner, register: str) -> None:
        result = add_beam(runner, register, "B-2", "4 in")
        assert "discarded" in result.output  # type: ignore[attr-defined]

    def test_the_same_beam_twice(self, runner: CliRunner, register: str) -> None:
        add_beam(runner, register)
        result = add_beam(runner, register)
        assert result.exit_code != 0  # type: ignore[attr-defined]

    def test_the_set_average(self, runner: CliRunner, register: str) -> None:
        add_beam(runner, register, "B-1")
        add_beam(runner, register, "B-2", "8 in")
        result = run(runner, register, "beam", "set", "S-4471")
        assert "modulus of rupture" in result.output
        assert "equivalent compressive" in result.output

    def test_a_set_with_no_beams(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "beam", "set", "S-9999")
        assert result.exit_code != 0
        assert "no beams on file" in result.output

    def test_a_set_where_every_beam_was_discarded(
        self, runner: CliRunner, register: str
    ) -> None:
        add_beam(runner, register, "B-1", "4 in")
        result = run(runner, register, "beam", "set", "S-4471")
        assert result.exit_code != 0
        assert "well outside" in result.output


class CaseEstimate:
    def test_compressive_to_rupture(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "beam", "estimate", "--compressive", "4000 psi")
        assert "modulus of rupture" in result.output

    def test_rupture_to_compressive(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "beam", "estimate", "--rupture", "600 psi")
        assert "compressive strength" in result.output

    def test_both_at_once(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "beam",
            "estimate",
            "--compressive",
            "4000 psi",
            "--rupture",
            "600 psi",
        )
        assert result.exit_code != 0
        assert "exactly one" in result.output

    def test_neither(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "beam", "estimate").exit_code != 0

    def test_the_factor_moves_the_answer(self, runner: CliRunner, register: str) -> None:
        low = run(
            runner,
            register,
            "beam",
            "estimate",
            "--compressive",
            "4000 psi",
            "--factor",
            "7",
        )
        high = run(
            runner,
            register,
            "beam",
            "estimate",
            "--compressive",
            "4000 psi",
            "--factor",
            "9",
        )
        assert low.output != high.output


class CaseCores:
    def test_record_one(self, runner: CliRunner, register: str) -> None:
        result = add_core(runner, register)
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert "C-1" in result.output  # type: ignore[attr-defined]

    def test_a_judged_location(self, runner: CliRunner, register: str) -> None:
        for index in range(3):
            add_core(runner, register, f"C-{index}", "46000 lbf")
        result = run(runner, register, "core", "judge", "Bay 4 slab")
        assert result.exit_code == 0
        assert "adequate" in result.output

    def test_a_location_that_fails(self, runner: CliRunner, register: str) -> None:
        for index in range(3):
            add_core(runner, register, f"C-{index}", "30000 lbf")
        result = run(runner, register, "core", "judge", "Bay 4 slab")
        assert result.exit_code != 0
        assert "not shown to be adequate" in result.output

    def test_too_few_cores(self, runner: CliRunner, register: str) -> None:
        add_core(runner, register)
        result = run(runner, register, "core", "judge", "Bay 4 slab")
        assert result.exit_code != 0
        assert "of 3 cores" in result.output

    def test_an_uncored_location(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "core", "judge", "Bay 9").exit_code != 0

    def test_locations(self, runner: CliRunner, register: str) -> None:
        add_core(runner, register)
        result = run(runner, register, "core", "locations")
        assert "Bay 4 slab" in result.output
        assert "adequate" in result.output

    def test_no_locations_at_all(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "core", "locations")
        assert "location" in result.output
