from __future__ import annotations

import pytest
from click.testing import CliRunner

from slumpcone.cli.common import ACTOR_ENV, UNATTRIBUTED
from slumpcone.cli.main import cli
from tests.cli.support import run


def as_actor(runner: CliRunner, register: str, who: str, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(cli, ["--register", register, "--actor", who, *args])


def a_card(runner: CliRunner, register: str, *, actor: str | None = None) -> None:
    run(runner, register, "crew", "add", "T-1", "R. Okafor")
    args = [
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
    ]
    if actor is None:
        run(runner, register, *args)
    else:
        as_actor(runner, register, actor, *args)


class CaseNaming:
    def test_the_actor_reaches_the_log(self, runner: CliRunner, register: str) -> None:
        a_card(runner, register, actor="j.mercer")
        result = run(runner, register, "audit", "log")
        assert "j.mercer" in result.output

    def test_nobody_named_reads_as_unattributed(self, runner: CliRunner, register: str) -> None:
        a_card(runner, register)
        assert UNATTRIBUTED in run(runner, register, "audit", "log").output

    def test_an_empty_actor_falls_back(self, runner: CliRunner, register: str) -> None:
        a_card(runner, register, actor="   ")
        assert UNATTRIBUTED in run(runner, register, "audit", "log").output

    def test_the_environment_names_the_actor(
        self, runner: CliRunner, register: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ACTOR_ENV, "k.abara")
        a_card(runner, register)
        assert "k.abara" in run(runner, register, "audit", "log").output

    def test_the_option_beats_the_environment(
        self, runner: CliRunner, register: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ACTOR_ENV, "k.abara")
        a_card(runner, register, actor="j.mercer")
        output = run(runner, register, "audit", "log").output
        assert "j.mercer" in output
        assert "k.abara" not in output


class CaseWhatIsLogged:
    def test_filing_a_card(self, runner: CliRunner, register: str) -> None:
        a_card(runner, register, actor="j.mercer")
        result = run(runner, register, "audit", "log")
        assert "crew.card" in result.output
        assert "T-1" in result.output

    def test_a_probe_check(self, runner: CliRunner, register: str) -> None:
        as_actor(
            runner,
            register,
            "j.mercer",
            "probe",
            "check",
            "MP-1",
            "--plant",
            "PL-1",
            "--probe-read",
            "4.5",
            "--oven",
            "4.3",
            "--on",
            "2024-06-12",
        )
        assert "probe.check" in run(runner, register, "audit", "log").output

    def test_disposing_of_a_returned_load(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
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
        )
        as_actor(
            runner,
            register,
            "j.mercer",
            "reclaim",
            "dispose",
            "881204",
            "--on",
            "2024-06-12",
        )
        assert "reclaim.dispose" in run(runner, register, "audit", "log").output

    def test_a_read_command_logs_nothing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        before = run(runner, register, "audit", "log").output
        run(runner, register, "crew", "list")
        assert run(runner, register, "audit", "log").output == before

    def test_a_refused_write_logs_nothing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "crew", "add", "T-1", "R. Okafor")
        before = run(runner, register, "audit", "log").output
        as_actor(
            runner,
            register,
            "j.mercer",
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
        assert run(runner, register, "audit", "log").output == before

    def test_the_chain_stays_intact(self, runner: CliRunner, register: str) -> None:
        a_card(runner, register, actor="j.mercer")
        as_actor(
            runner,
            register,
            "k.abara",
            "probe",
            "check",
            "MP-1",
            "--plant",
            "PL-1",
            "--probe-read",
            "4.5",
            "--oven",
            "4.3",
            "--on",
            "2024-06-12",
        )
        result = run(runner, register, "audit", "verify")
        assert result.exit_code == 0

    def test_two_actors_are_told_apart(self, runner: CliRunner, register: str) -> None:
        a_card(runner, register, actor="j.mercer")
        as_actor(
            runner,
            register,
            "k.abara",
            "probe",
            "check",
            "MP-1",
            "--plant",
            "PL-1",
            "--probe-read",
            "4.5",
            "--oven",
            "4.3",
            "--on",
            "2024-06-12",
        )
        mine = run(runner, register, "audit", "log", "--actor", "j.mercer")
        assert "crew.card" in mine.output
        assert "probe.check" not in mine.output


def test_the_option_shows_in_help(runner: CliRunner, register: str) -> None:
    assert "--actor" in run(runner, register, "--help").output
