from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run

DAY = "2024-06-12"


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed", "--no-yard")


def certify(
    runner: CliRunner,
    register: str,
    *,
    code: str = "TECH-7",
    grade: str = "field grade I",
    issued: str = "2022-06-01",
    expires: str = "2027-06-01",
) -> None:
    run(runner, register, "crew", "add", code, "R. Okafor")
    run(
        runner,
        register,
        "crew",
        "card",
        code,
        "--grade",
        grade,
        "--number",
        f"ACI-{code}",
        "--issued",
        issued,
        "--expires",
        expires,
    )


class CaseAudit:
    def test_with_nobody_on_file_every_result_is_a_finding(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        # Every one is a records problem, so it reports and still exits clean.
        assert result.exit_code == 0
        assert "would not stand" in result.output
        assert "not on file" in result.output

    def test_a_certified_technician_makes_them_stand(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        certify(runner, register)
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        assert result.exit_code == 0
        assert "every one stands" in result.output

    def test_the_wrong_certification_needs_a_retest(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        certify(runner, register, grade="strength testing")
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        assert result.exit_code != 0
        assert "no card for this test" in result.output
        assert "cannot be made to stand by filing" in result.output

    def test_a_card_that_lapsed_before_the_day(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        certify(runner, register, issued="2018-01-01", expires="2023-01-01")
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        assert "had lapsed on the day" in result.output

    def test_a_card_issued_after_the_day(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        certify(runner, register, issued="2025-01-01", expires="2030-01-01")
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        assert "had lapsed on the day" in result.output

    def test_a_records_problem_does_not_fail_the_command(
        self, runner: CliRunner, register: str
    ) -> None:
        # Nobody on file at all is a records problem, so the command reports it
        # and does not claim a retest is needed.
        seeded(runner, register)
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        assert "records" in result.output
        assert "cannot be made to stand by filing" not in result.output


class CaseFiltering:
    def test_only_the_retests(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        certify(runner, register, grade="strength testing")
        result = run(
            runner, register, "report", "witness", "--from", DAY, "--to", DAY, "--retests"
        )
        assert "no card for this test" in result.output

    def test_one_ticket(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        certify(runner, register)
        result = run(runner, register, "report", "witness", "--ticket", "881204")
        assert result.exit_code == 0
        assert "result(s) checked" in result.output

    def test_a_ticket_with_no_tests(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "report", "witness", "--ticket", "999999")
        assert "0 result(s) checked" in result.output

    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "report",
            "witness",
            "--from",
            "2024-07-01",
            "--to",
            "2024-07-31",
        )
        assert result.exit_code == 0
        assert "every one stands" in result.output

    def test_the_problem_tally_prints(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        certify(runner, register)
        result = run(runner, register, "report", "witness", "--from", DAY, "--to", DAY)
        assert "no technician written on the test" in result.output
