from __future__ import annotations

import pytest
from click.testing import CliRunner

from slumpcone.errors import (
    ConflictError,
    ExitCode,
    NotFoundError,
    RuleViolationError,
    SlumpconeError,
    UnitError,
    ValidationError,
    exit_code_for,
)
from tests.cli.support import run


class CaseTheMapping:
    def test_a_missing_record(self) -> None:
        assert exit_code_for(NotFoundError("mix design", "X")) is ExitCode.NOT_FOUND

    def test_a_collision(self) -> None:
        assert exit_code_for(ConflictError("mix design", "X")) is ExitCode.CONFLICT

    def test_a_bad_value(self) -> None:
        assert exit_code_for(ValidationError("no")) is ExitCode.INVALID

    def test_a_unit_mistake_reads_as_a_bad_value(self) -> None:
        assert exit_code_for(UnitError("no")) is ExitCode.INVALID

    def test_a_rule_refusing(self) -> None:
        assert exit_code_for(RuleViolationError("X_Y", "no")) is ExitCode.REFUSED

    def test_anything_else_deliberate(self) -> None:
        assert exit_code_for(SlumpconeError("no")) is ExitCode.REFUSED

    def test_something_that_is_not_ours(self) -> None:
        assert exit_code_for(ValueError("no")) is ExitCode.REFUSED

    def test_the_three_codes_that_were_already_taken(self) -> None:
        assert int(ExitCode.OK) == 0
        assert int(ExitCode.REFUSED) == 1
        assert int(ExitCode.USAGE) == 2

    def test_the_rest_start_above_them(self) -> None:
        rest = [ExitCode.NOT_FOUND, ExitCode.CONFLICT, ExitCode.INVALID, ExitCode.STORE]
        assert all(int(one) > 2 for one in rest)

    def test_every_code_is_distinct(self) -> None:
        values = [int(one) for one in ExitCode]
        assert len(set(values)) == len(values)

    def test_a_code_reads_as_words(self) -> None:
        assert str(ExitCode.NOT_FOUND) == "not found"


class CaseAtTheTerminal:
    def test_success(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "register", "init").exit_code == ExitCode.OK

    def test_a_record_that_is_not_there(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mix", "show", "NOPE")
        assert result.exit_code == ExitCode.NOT_FOUND

    def test_a_collision(self, runner: CliRunner, register: str) -> None:
        args = [
            "reclaim",
            "returned",
            "881204",
            "--mix",
            "4000P-57",
            "--volume",
            "3 yd3",
            "--age",
            "45",
            "--on",
            "2024-06-12",
        ]
        run(runner, register, *args)
        assert run(runner, register, *args).exit_code == ExitCode.CONFLICT

    def test_a_rule_refusing(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "bleed",
            "record",
            "881204",
            "--on",
            "2024-06-12",
            "--sample",
            "5000 lb",
            "--batch",
            "4000 lb",
            "--water",
            "260 lb",
        )
        assert result.exit_code == ExitCode.REFUSED

    def test_a_bad_value(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "mix",
            "add",
            "X",
            "A mix",
            "--strength",
            "4000 furlongs",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
            "--charge",
            "CEM-I:cement:500 lb/yd3",
        )
        assert result.exit_code == ExitCode.INVALID

    def test_a_usage_mistake(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "mix", "show").exit_code == ExitCode.USAGE

    def test_an_unknown_command(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "levitate").exit_code == ExitCode.USAGE

    def test_the_message_still_reads(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mix", "show", "NOPE")
        assert "no mix design on file" in result.output
        assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("register", "info"), ExitCode.OK),
        (("mix", "show", "NOPE"), ExitCode.NOT_FOUND),
        (("probe", "show", "MP-9", "--plant", "PL-1"), ExitCode.OK),
        (("crew", "show", "T-9"), ExitCode.NOT_FOUND),
        (("account", "show", "NOPE"), ExitCode.NOT_FOUND),
    ],
)
def test_a_few_commands_end_to_end(
    runner: CliRunner, register: str, args: tuple[str, ...], expected: ExitCode
) -> None:
    run(runner, register, "register", "init")
    assert run(runner, register, *args).exit_code == expected
