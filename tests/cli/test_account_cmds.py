from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


def add_account(runner: CliRunner, register: str, code: str = "ASH-01", **extra: str) -> object:
    args = [
        "account",
        "add",
        code,
        "Ashfield Paving",
        "--terms",
        "30",
        "--discount-days",
        "10",
        "--discount",
        "2",
        "--limit",
        "$25000",
        "--contact",
        "Dee Kelso",
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return run(runner, register, *args)


class CaseAccounts:
    def test_add(self, runner: CliRunner, register: str) -> None:
        result = add_account(runner, register)
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert "ASH-01" in result.output  # type: ignore[attr-defined]
        assert "2/10 net 30" in result.output  # type: ignore[attr-defined]

    def test_an_unknown_status(self, runner: CliRunner, register: str) -> None:
        result = add_account(runner, register, status="dubious")
        assert result.exit_code != 0  # type: ignore[attr-defined]

    def test_an_unreadable_limit(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner, register, "account", "add", "ASH-01", "Ashfield", "--limit", "lots"
        )
        assert result.exit_code != 0
        assert "as an amount" in result.output

    def test_list(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        result = run(runner, register, "account", "list")
        assert "ASH-01" in result.output
        assert "terms" in result.output.splitlines()[0]

    def test_list_only_open(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register, "ASH-01")
        add_account(runner, register, "ABB-02", status="closed")
        result = run(runner, register, "account", "list", "--open")
        assert "ASH-01" in result.output
        assert "ABB-02" not in result.output

    def test_show(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        result = run(runner, register, "account", "show", "ash 01", "--balance", "$10000")
        assert "credit left" in result.output
        assert "$15,000.00" in result.output

    def test_show_an_unknown_account(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "account", "show", "ASH-09").exit_code != 0


class CaseQuotes:
    def test_quote(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        result = run(runner, register, "account", "quote", "ASH-01", "4000P-57", "$118.50")
        assert result.exit_code == 0
        assert "$118.50" in result.output

    def test_it_shows_up_on_the_account(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        run(runner, register, "account", "quote", "ASH-01", "4000P-57", "$118.50")
        result = run(runner, register, "account", "show", "ASH-01")
        assert "4000P-57" in result.output

    def test_the_same_window_twice(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        run(runner, register, "account", "quote", "ASH-01", "4000P-57", "$118.50")
        result = run(runner, register, "account", "quote", "ASH-01", "4000P-57", "$120.00")
        assert result.exit_code != 0

    def test_quoting_an_unknown_account(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "account", "quote", "ASH-09", "4000P-57", "$118.50")
        assert result.exit_code != 0


class CaseCheck:
    def test_an_order_inside_the_limit(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        result = run(
            runner,
            register,
            "account",
            "check",
            "ASH-01",
            "--balance",
            "$1000",
            "--order",
            "$500",
        )
        assert "nothing stops this order" in result.output

    def test_an_order_past_the_limit(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register)
        result = run(
            runner,
            register,
            "account",
            "check",
            "ASH-01",
            "--balance",
            "$24000",
            "--order",
            "$5000",
        )
        assert result.exit_code != 0
        assert "credit is left" in result.output

    def test_an_account_on_hold(self, runner: CliRunner, register: str) -> None:
        add_account(runner, register, status="on hold")
        result = run(
            runner,
            register,
            "account",
            "check",
            "ASH-01",
            "--balance",
            "$0",
            "--order",
            "$500",
        )
        assert result.exit_code != 0
        assert "on_hold" in result.output


class CaseMargin:
    def test_it_compares_the_quote_with_the_cost(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        add_account(runner, register)
        run(runner, register, "account", "quote", "ASH-01", "4000P-57", "$118.50")
        for code, amount, per in (
            ("CEM-I", "142.00", "1 ton"),
            ("SCM-F", "88.00", "1 ton"),
            ("CA-57", "17.50", "1 ton"),
            ("FA-1", "14.25", "1 ton"),
            ("W-1", "0.01", "100 lb"),
            ("AD-AE", "0.09", "1 floz"),
            ("AD-WR", "0.06", "1 floz"),
        ):
            run(runner, register, "price", "set", code, amount, "--per", per)
        result = run(
            runner,
            register,
            "account",
            "margin",
            "ASH-01",
            "4000P-57",
            "--on",
            "2024-06-12",
        )
        assert result.exit_code == 0
        assert "margin" in result.output
        assert "fully priced" in result.output

    def test_an_unquoted_mixture(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        add_account(runner, register)
        result = run(runner, register, "account", "margin", "ASH-01", "4000P-57")
        assert result.exit_code != 0
