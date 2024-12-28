from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from slumpcone.cli.main import cli
from tests.cli.test_mix_cmds import add_mix, stock_materials


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def register(tmp_path: Path) -> str:
    return str(tmp_path / "r.sqlite3")


def run(runner: CliRunner, register: str, *args: str) -> Result:
    return runner.invoke(cli, ["--register", register, *args])


def set_prices(runner: CliRunner, register: str) -> None:
    for code, amount, per in (
        ("CEM-I", "142.00", "1 ton"),
        ("SCM-F", "88.00", "1 ton"),
        ("CA-57", "17.50", "1 ton"),
        ("FA-1", "14.25", "1 ton"),
        ("W-1", "0.01", "100 lb"),
        ("AD-AE", "0.09", "1 floz"),
    ):
        run(runner, register, "price", "set", code, amount, "--per", per)


class CaseSet:
    def test_it_files_a_price(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "price", "set", "CEM-I", "142.00", "--per", "1 ton")
        assert result.exit_code == 0
        assert "$142.00" in result.output

    def test_a_dollar_sign_is_accepted(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "price", "set", "CEM-I", "$142.00", "--per", "1 ton")
        assert result.exit_code == 0

    def test_an_unreadable_amount(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "price", "set", "CEM-I", "cheap", "--per", "1 ton")
        assert result.exit_code != 0
        assert "as an amount" in result.output

    def test_a_window(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "price",
            "set",
            "CEM-I",
            "142.00",
            "--per",
            "1 ton",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "from 2024-06-01" in result.output

    def test_the_same_window_twice(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "price", "set", "CEM-I", "142.00", "--per", "1 ton")
        result = run(runner, register, "price", "set", "CEM-I", "151.00", "--per", "1 ton")
        assert result.exit_code != 0
        assert "already on file" in result.output

    def test_close_previous(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "price",
            "set",
            "CEM-I",
            "142.00",
            "--per",
            "1 ton",
            "--from",
            "2024-01-01",
        )
        result = run(
            runner,
            register,
            "price",
            "set",
            "CEM-I",
            "151.00",
            "--per",
            "1 ton",
            "--from",
            "2024-06-01",
            "--close-previous",
        )
        assert result.exit_code == 0
        assert "closed 1 open price window" in result.output


class CaseListings:
    def test_list(self, runner: CliRunner, register: str) -> None:
        set_prices(runner, register)
        result = run(runner, register, "price", "list", "--on", "2024-06-12")
        assert "CEM-I" in result.output
        assert "$142.00" in result.output

    def test_a_price_not_yet_in_force(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "price",
            "set",
            "CEM-I",
            "142.00",
            "--per",
            "1 ton",
            "--from",
            "2025-01-01",
        )
        result = run(runner, register, "price", "list", "--on", "2024-06-12")
        assert "no price in force" in result.output

    def test_history(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "price",
            "set",
            "CEM-I",
            "142.00",
            "--per",
            "1 ton",
            "--from",
            "2024-01-01",
        )
        run(
            runner,
            register,
            "price",
            "set",
            "CEM-I",
            "151.00",
            "--per",
            "1 ton",
            "--from",
            "2024-06-01",
        )
        result = run(runner, register, "price", "history", "CEM-I")
        assert "$142.00" in result.output
        assert "$151.00" in result.output

    def test_history_of_an_unpriced_material(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "price", "history", "CEM-I")
        assert result.exit_code != 0
        assert "no price on file" in result.output


class CaseCost:
    def test_it_costs_a_mixture(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        add_mix(runner, register)
        set_prices(runner, register)
        result = run(runner, register, "price", "cost", "4000P-57", "--on", "2024-06-12")
        assert result.exit_code == 0
        assert "Cost of 4000P-57 r1" in result.output
        assert "per unit" in result.output

    def test_an_unpriced_material_is_reported(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        add_mix(runner, register)
        run(runner, register, "price", "set", "CEM-I", "142.00", "--per", "1 ton")
        result = run(runner, register, "price", "cost", "4000P-57", "--on", "2024-06-12")
        assert "no price for" in result.output

    def test_with_a_sale_price(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        add_mix(runner, register)
        set_prices(runner, register)
        result = run(
            runner,
            register,
            "price",
            "cost",
            "4000P-57",
            "--on",
            "2024-06-12",
            "--sale",
            "$118.00",
        )
        assert "margin" in result.output

    def test_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "price", "cost", "4000P-58")
        assert result.exit_code != 0


class CaseCompare:
    def test_two_mixtures(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        add_mix(runner, register)
        run(
            runner,
            register,
            "mix",
            "add",
            "3000W-67",
            "Wall mix",
            "--strength",
            "3000 psi",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
            "--charge",
            "CEM-I:cement:470",
            "--charge",
            "CA-57:coarse_aggregate:1780",
            "--charge",
            "FA-1:fine_aggregate:1300",
            "--charge",
            "W-1:water:250",
        )
        set_prices(runner, register)
        result = run(
            runner,
            register,
            "price",
            "compare",
            "4000P-57",
            "3000W-67",
            "--on",
            "2024-06-12",
        )
        assert "4000P-57 r1" in result.output
        assert "3000W-67 r1" in result.output
        assert "fully priced" in result.output

    def test_an_unknown_mix_in_the_list(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "price", "compare", "4000P-58")
        assert result.exit_code != 0
