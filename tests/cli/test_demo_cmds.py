from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


class CaseSeed:
    def test_it_fills_an_empty_register(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "demo", "seed")
        assert result.exit_code == 0
        assert "materials" in result.output
        assert "4000P-57" in result.output

    def test_it_refuses_a_register_that_already_has_rows(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "demo", "seed")
        assert result.exit_code != 0
        assert "already holds" in result.output

    def test_force_seeds_anyway_and_the_second_pass_collides(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "demo", "seed", "--force")
        assert result.exit_code != 0
        assert "already on file" in result.output

    def test_the_register_is_usable_afterwards(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        assert "4000P-57" in run(runner, register, "mix", "list").output
        assert "PL-1" in run(runner, register, "plant", "list").output

    def test_the_worked_example_reports(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        audit = run(
            runner, register, "batch", "audit", "--from", "2024-06-12", "--to", "2024-06-12"
        )
        assert "881204" in audit.output
        strength = run(
            runner, register, "lab", "strength", "4000P-57", "--specified", "4000 psi"
        )
        assert "investigate" in strength.output

    def test_the_check_passes_on_the_seeded_mix(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "mix", "check", "4000P-57")
        assert result.exit_code == 0
        assert "no findings" in result.output


class CaseTour:
    def test_it_lists_commands(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "demo", "tour")
        assert result.exit_code == 0
        assert "slumpcone mix check 4000P-57" in result.output
        assert "report nonconformance" in result.output

    def test_every_line_starts_with_the_program_name(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(runner, register, "demo", "tour")
        lines = [line.strip() for line in result.output.splitlines()[2:] if line.strip()]
        assert all(line.startswith("slumpcone ") for line in lines)
