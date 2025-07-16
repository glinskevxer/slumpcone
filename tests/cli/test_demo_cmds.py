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


class CaseTheYard:
    def test_the_seed_fills_the_rest_of_the_plant(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(runner, register, "demo", "seed")
        assert "technicians" in result.output
        assert "probe checks" in result.output
        assert "wash tanks" in result.output

    def test_the_crew_is_there(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        assert "2 technician(s)" in run(runner, register, "crew", "list").output

    def test_between_them_they_cover_every_test(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "crew", "gaps", "--on", "2024-06-12")
        assert "0 of 9 test(s) uncovered" in result.output

    def test_one_card_runs_out_in_july(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "crew", "expiring", "--on", "2024-06-12", "--days", "30")
        assert "ACI-2044" in result.output

    def test_the_probes_are_there_and_one_is_bad(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "probe", "list", "--plant", "PL-1", "--on", "2024-06-12")
        assert "2 probe(s)" in result.output
        assert "do not batch off: MP-2" in result.output

    def test_one_wash_tank_is_over_the_limit(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(
            runner, register, "reclaim", "tanks", "--plant", "PL-1", "--on", "2024-06-12"
        )
        assert "2 tank(s)" in result.output
        assert "over the limit" in result.output

    def test_a_load_is_sitting_on_the_yard(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "reclaim", "yard", "--on", "2024-06-12")
        assert "1 load(s) on the yard" in result.output

    def test_the_account_is_quoted(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "account", "show", "ASH-01")
        assert "ASH-01" in result.output

    def test_the_carbon_factors_are_loaded(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "carbon", "mix", "4000P-57")
        assert "per m3" in result.output

    def test_the_haul_profile_is_there(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "dispatch", "profiles")
        assert "P-2024-118" in result.output
        assert "not yet fitted" in result.output

    def test_no_yard_leaves_only_the_concrete(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "demo", "seed", "--no-yard")
        assert "technicians" not in result.output
        assert "tickets" in result.output

    def test_no_yard_files_nobody(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed", "--no-yard")
        assert "0 technician(s)" in run(runner, register, "crew", "list").output

    def test_no_yard_still_files_the_days_work(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed", "--no-yard")
        result = run(
            runner,
            register,
            "report",
            "production",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
        )
        assert "36.0" in result.output
