from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from slumpcone.cli.completion import (
    BY_PARAMETER,
    attach,
    complete_account,
    complete_mix,
    complete_plant,
    complete_technician,
    complete_truck,
    register_path,
)
from slumpcone.cli.main import cli
from tests.cli.support import run


class Recorder:
    """A stand in for a click context carrying a register path."""

    def __init__(self, path: str | None, parent: object | None = None) -> None:
        self.params = {"register_path": path} if path is not None else {}
        self.parent = parent


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")


def offered(completer: object, register: str, incomplete: str = "") -> list[str]:
    ctx = Recorder(register)
    return [item.value for item in completer(ctx, None, incomplete)]  # type: ignore[operator]


class CaseFindingTheRegister:
    def test_it_reads_the_option_off_the_context(self) -> None:
        assert register_path(Recorder("here.sqlite3")) == Path("here.sqlite3")  # type: ignore[arg-type]

    def test_it_walks_up_to_the_root(self) -> None:
        root = Recorder("here.sqlite3")
        child = Recorder(None, root)
        assert register_path(child) == Path("here.sqlite3")  # type: ignore[arg-type]

    def test_the_environment_fills_in(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SLUMPCONE_REGISTER", "env.sqlite3")
        assert register_path(None) == Path("env.sqlite3")

    def test_the_default_is_last(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SLUMPCONE_REGISTER", raising=False)
        assert register_path(None).name == "slumpcone.sqlite3"


class CaseCompleting:
    def test_mix_codes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert "4000P-57" in offered(complete_mix, register)

    def test_a_prefix_narrows(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert offered(complete_mix, register, "4000") == ["4000P-57"]

    def test_a_prefix_that_matches_nothing(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert offered(complete_mix, register, "ZZZ") == []

    def test_the_prefix_is_matched_without_regard_to_case(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        assert offered(complete_mix, register, "4000p") == ["4000P-57"]

    def test_plant_codes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert "PL-1" in offered(complete_plant, register)

    def test_truck_codes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert "TR-114" in offered(complete_truck, register)

    def test_account_codes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert "ASH-01" in offered(complete_account, register)

    def test_technician_codes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert "TECH-7" in offered(complete_technician, register)

    def test_the_answers_are_sorted(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        found = offered(complete_technician, register)
        assert found == sorted(found)


class CaseItNeverRaises:
    def test_a_register_that_is_not_there(self, tmp_path: Path) -> None:
        assert offered(complete_mix, str(tmp_path / "nope.sqlite3")) == []

    def test_a_directory_where_a_register_should_be(self, tmp_path: Path) -> None:
        assert offered(complete_mix, str(tmp_path)) == []

    def test_a_file_that_is_not_a_register(self, tmp_path: Path) -> None:
        junk = tmp_path / "junk.sqlite3"
        junk.write_text("not a database at all")
        assert offered(complete_mix, str(junk)) == []

    def test_an_empty_register_offers_nothing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "register", "init")
        assert offered(complete_mix, register) == []


class CaseWiring:
    def test_the_table_covers_the_codes_that_matter(self) -> None:
        assert set(BY_PARAMETER) >= {"mix_code", "plant_code", "material_code"}

    def test_the_real_command_line_got_completers(self) -> None:
        found = 0
        for group in cli.commands.values():
            if not isinstance(group, click.Group):
                continue
            for command in group.commands.values():
                for parameter in command.params:
                    if parameter._custom_shell_complete is not None:
                        found += 1
        assert found > 20

    def test_a_real_mix_code_argument_carries_one(self) -> None:
        carbon = cli.commands["carbon"]
        assert isinstance(carbon, click.Group)
        parameter = next(one for one in carbon.commands["mix"].params if one.name == "mix_code")
        assert parameter._custom_shell_complete is complete_mix

    def test_attaching_twice_adds_nothing_the_second_time(self) -> None:
        @click.group("toy")
        def toy() -> None:
            """A toy."""

        @toy.group("thing")
        def thing() -> None:
            """Things."""

        @thing.command("show")
        @click.argument("mix_code")
        def show(mix_code: str) -> None:
            """Show."""

        assert attach(toy) == 1
        assert attach(toy) == 0

    def test_a_parameter_with_its_own_completer_is_left_alone(self) -> None:
        def mine(ctx: object, param: object, incomplete: str) -> list[object]:
            return []

        @click.group("toy")
        def toy() -> None:
            """A toy."""

        @toy.command("show")
        @click.argument("mix_code", shell_complete=mine)
        def show(mix_code: str) -> None:
            """Show."""

        assert attach(toy) == 0
