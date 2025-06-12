from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run

DAY = "2024-06-12"


def crewed(runner: CliRunner, register: str) -> None:
    run(runner, register, "crew", "add", "T-1", "R. Okafor", "--employer", "Ashfield")
    run(
        runner,
        register,
        "crew",
        "card",
        "T-1",
        "--grade",
        "field grade I",
        "--number",
        "ACI-1001",
        "--issued",
        "2022-06-01",
        "--expires",
        "2027-06-01",
    )


class CaseAdding:
    def test_it_files_somebody(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "crew", "add", "T-1", "R. Okafor")
        assert result.exit_code == 0
        assert "T-1 R. Okafor" in result.output

    def test_adding_again_keeps_the_cards(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "add", "T-1", "R. Okafor Jr")
        assert "1 card(s)" in result.output

    def test_a_card_lands(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "show", "T-1", "--on", DAY)
        assert "ACI-1001" in result.output
        assert "current" in result.output

    def test_a_grade_nobody_knows(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        result = run(
            runner,
            register,
            "crew",
            "card",
            "T-1",
            "--grade",
            "wizard",
            "--number",
            "ACI-1",
            "--issued",
            "2022-06-01",
            "--expires",
            "2027-06-01",
        )
        assert result.exit_code != 0
        assert "CERTIFICATION_UNKNOWN_GRADE" in result.output

    def test_the_refusal_lists_the_grades(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        result = run(
            runner,
            register,
            "crew",
            "card",
            "T-1",
            "--grade",
            "wizard",
            "--number",
            "ACI-1",
            "--issued",
            "2022-06-01",
            "--expires",
            "2027-06-01",
        )
        assert "field grade I" in result.output

    def test_the_grade_can_be_given_by_name(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        result = run(
            runner,
            register,
            "crew",
            "card",
            "T-1",
            "--grade",
            "LAB_LEVEL_2",
            "--number",
            "ACI-1",
            "--issued",
            "2022-06-01",
            "--expires",
            "2027-06-01",
        )
        assert result.exit_code == 0

    def test_an_expiry_before_the_issue(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        result = run(
            runner,
            register,
            "crew",
            "card",
            "T-1",
            "--grade",
            "field grade I",
            "--number",
            "ACI-1",
            "--issued",
            "2027-06-01",
            "--expires",
            "2022-06-01",
        )
        assert result.exit_code != 0
        assert "CERTIFICATION_EXPIRES_BEFORE_ISSUE" in result.output

    def test_a_card_for_somebody_not_on_file(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "crew",
            "card",
            "T-9",
            "--grade",
            "field grade I",
            "--number",
            "ACI-1",
            "--issued",
            "2022-06-01",
            "--expires",
            "2027-06-01",
        )
        assert result.exit_code != 0


class CaseReading:
    def test_show_says_what_they_may_run(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "show", "T-1", "--on", DAY)
        assert "may run today" in result.output
        assert "slump" in result.output

    def test_a_lapsed_card_allows_nothing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        run(
            runner,
            register,
            "crew",
            "card",
            "T-1",
            "--grade",
            "field grade I",
            "--number",
            "ACI-1",
            "--issued",
            "2018-06-01",
            "--expires",
            "2023-06-01",
        )
        result = run(runner, register, "crew", "show", "T-1", "--on", DAY)
        assert "nothing" in result.output
        assert "lapsed" in result.output

    def test_show_an_unknown_technician(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "crew", "show", "T-9").exit_code != 0

    def test_the_listing(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "list", "--on", DAY)
        assert "T-1" in result.output
        assert "1 technician(s)" in result.output

    def test_an_empty_listing(self, runner: CliRunner, register: str) -> None:
        assert "0 technician(s)" in run(runner, register, "crew", "list").output

    def test_dropping_somebody(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        assert "dropped" in run(runner, register, "crew", "drop", "T-1").output
        assert "0 technician(s)" in run(runner, register, "crew", "list").output

    def test_dropping_somebody_not_on_file(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "crew", "drop", "T-9").exit_code != 0


class CaseRoster:
    def test_who_may_run_a_slump(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "roster", "slump", "--on", DAY)
        assert "T-1 R. Okafor" in result.output
        assert "1 certified" in result.output

    def test_nobody_may_break_cylinders(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "roster", "breaking_cylinders", "--on", DAY)
        assert "0 certified" in result.output
        assert "nobody on file" in result.output

    def test_a_test_nobody_knows(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "crew", "roster", "levitation")
        assert result.exit_code != 0
        assert "CERTIFICATION_UNKNOWN_TEST" in result.output

    def test_spaces_are_accepted_for_underscores(
        self, runner: CliRunner, register: str
    ) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "roster", "unit weight", "--on", DAY)
        assert result.exit_code == 0

    def test_the_gaps(self, runner: CliRunner, register: str) -> None:
        crewed(runner, register)
        result = run(runner, register, "crew", "gaps", "--on", DAY)
        assert "breaking cylinders" in result.output
        assert "uncovered" in result.output

    def test_an_empty_register_has_every_gap(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "crew", "gaps", "--on", DAY)
        assert "9 of 9 test(s) uncovered" in result.output


class CaseExpiry:
    def stocked(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        run(
            runner,
            register,
            "crew",
            "card",
            "T-1",
            "--grade",
            "field grade I",
            "--number",
            "ACI-1",
            "--issued",
            "2019-01-01",
            "--expires",
            "2023-01-01",
        )
        run(runner, register, "crew", "add", "T-2", "M. Lindqvist")
        run(
            runner,
            register,
            "crew",
            "card",
            "T-2",
            "--grade",
            "strength testing",
            "--number",
            "ACI-2",
            "--issued",
            "2019-07-01",
            "--expires",
            "2024-07-01",
        )

    def test_what_is_running_out(self, runner: CliRunner, register: str) -> None:
        self.stocked(runner, register)
        result = run(runner, register, "crew", "expiring", "--on", DAY, "--days", "60")
        assert "ACI-2" in result.output
        assert "1 card(s) expiring" in result.output

    def test_the_holder_is_named(self, runner: CliRunner, register: str) -> None:
        self.stocked(runner, register)
        result = run(runner, register, "crew", "expiring", "--on", DAY, "--days", "60")
        assert "M. Lindqvist" in result.output

    def test_what_has_already_run_out(self, runner: CliRunner, register: str) -> None:
        self.stocked(runner, register)
        result = run(runner, register, "crew", "expiring", "--on", DAY, "--lapsed")
        assert "ACI-1" in result.output
        assert "1 card(s) lapsed" in result.output

    def test_a_short_window_finds_nothing(self, runner: CliRunner, register: str) -> None:
        self.stocked(runner, register)
        result = run(runner, register, "crew", "expiring", "--on", DAY, "--days", "3")
        assert "0 card(s) expiring" in result.output


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "crew" in run(runner, register, "--help").output
