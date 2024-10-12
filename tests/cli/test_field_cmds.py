from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from slumpcone.cli.main import cli
from tests.cli.test_batch_cmds import stock


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def register(tmp_path: Path) -> str:
    return str(tmp_path / "r.sqlite3")


def run(runner: CliRunner, register: str, *args: str) -> Result:
    return runner.invoke(cli, ["--register", register, *args])


def write_ticket(runner: CliRunner, register: str) -> None:
    run(
        runner,
        register,
        "batch",
        "ticket",
        "881204",
        "--plant",
        "PL-1",
        "--mix",
        "4000P-57",
        "--volume",
        "9 yd3",
        "--at",
        "2024-06-12T07:42",
        "--truck",
        "TR-114",
        "--purchaser",
        "Ashfield",
        "--project",
        "Route 9",
    )


class CaseRecord:
    def test_one_sample_can_be_four_records(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "4.5 in",
            "--air",
            "6.2",
            "--temp",
            "78",
            "--unit-weight",
            "142.6",
            "--technician",
            "DK",
        )
        assert result.exit_code == 0
        assert len(result.output.strip().splitlines()) == 4

    def test_a_volumetric_air_method(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--air",
            "6.2",
            "--air-method",
            "volumetric",
        )
        assert "air_volumetric" in result.output

    def test_no_readings_at_all(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "field", "record", "881204")
        assert result.exit_code != 0
        assert "at least one reading" in result.output

    def test_an_impossible_slump(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "15 in",
        )
        assert result.exit_code != 0
        assert "collapsed cone" in result.output

    def test_the_same_test_twice(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "4.5 in",
        )
        result = run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "4.5 in",
        )
        assert result.exit_code != 0
        assert "already on file" in result.output


class CaseList:
    def test_it_lists_the_tests(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "4.5 in",
            "--air",
            "6.2",
        )
        result = run(runner, register, "field", "list", "881204")
        assert "slump" in result.output
        assert "4.50 in" in result.output

    def test_an_untested_load(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "field", "list", "881299")
        assert "method" in result.output


class CaseJudge:
    def test_an_accepted_load(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "4.0 in",
            "--air",
            "6.2",
        )
        result = run(runner, register, "field", "judge", "881204")
        assert "accepted" in result.output

    def test_a_rejected_load(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:05",
            "--slump",
            "7.5 in",
        )
        run(
            runner,
            register,
            "field",
            "record",
            "881204",
            "--at",
            "2024-06-12T08:12",
            "--slump",
            "7.2 in",
            "--retest",
        )
        result = run(runner, register, "field", "judge", "881204")
        assert "rejected" in result.output

    def test_judging_an_unknown_ticket(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "field", "judge", "881299")
        assert result.exit_code != 0


class CaseSample:
    def test_a_good_sample(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "field",
            "sample",
            "881204",
            "--load",
            "9 yd3",
            "--discharged",
            "3 yd3",
            "--portions",
            "2",
            "--span",
            "6",
            "--delay",
            "3",
        )
        assert "acceptance sample" in result.output
        assert "yes" in result.output

    def test_a_sample_off_the_head(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "field",
            "sample",
            "881204",
            "--load",
            "9 yd3",
            "--discharged",
            "0.1 yd3",
        )
        assert "does not count" in result.output

    def test_the_moulding_limit_is_looser(self, runner: CliRunner, register: str) -> None:
        args = (
            "field",
            "sample",
            "881204",
            "--load",
            "9 yd3",
            "--discharged",
            "3 yd3",
            "--delay",
            "8",
        )
        assert "no" in run(runner, register, *args).output
        assert "yes" in run(runner, register, *args, "--for-specimens").output


class CaseOutstanding:
    def test_it_lists_the_outcomes(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        result = run(
            runner,
            register,
            "field",
            "outstanding",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "881204" in result.output
        assert "not_tested" in result.output

    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "field",
            "outstanding",
            "--from",
            "2024-07-01",
            "--to",
            "2024-07-31",
        )
        assert "ticket" in result.output
