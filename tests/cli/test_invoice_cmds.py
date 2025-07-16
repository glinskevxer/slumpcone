from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


def stocked(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")
    run(
        runner,
        register,
        "account",
        "add",
        "ASH-01",
        "Ashfield Paving",
        "--terms",
        "30",
        "--discount-days",
        "10",
        "--discount",
        "2",
        "--limit",
        "$25000",
    )
    run(runner, register, "account", "quote", "ASH-01", "4000P-57", "$118.50")


def draft(runner: CliRunner, register: str, number: str = "INV-2211", *extra: str) -> object:
    return run(
        runner,
        register,
        "invoice",
        "draft",
        number,
        "--account",
        "ASH-01",
        "--from",
        "2024-06-12",
        "--to",
        "2024-06-12",
        *extra,
    )


class CaseDraft:
    def test_it_picks_up_the_days_tickets(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        result = draft(runner, register)
        assert result.exit_code == 0  # type: ignore[attr-defined]
        assert "INV-2211" in result.output  # type: ignore[attr-defined]

    def test_the_lines_are_the_tickets(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(runner, register, "invoice", "show", "INV-2211")
        assert "881204" in result.output
        assert "4000P-57" in result.output

    def test_charges_land_by_default(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(runner, register, "invoice", "show", "INV-2211")
        assert "fuel" in result.output

    def test_charges_can_be_left_off(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register, "INV-2211", "--no-charges")
        result = run(runner, register, "invoice", "show", "INV-2211")
        assert "fuel" not in result.output

    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        result = run(
            runner,
            register,
            "invoice",
            "draft",
            "INV-1",
            "--account",
            "ASH-01",
            "--from",
            "2024-07-01",
            "--to",
            "2024-07-31",
        )
        assert result.exit_code != 0
        assert "no tickets in that window" in result.output

    def test_an_unquoted_account(self, runner: CliRunner, register: str) -> None:
        # The demo quotes ASH-01, so this needs an account nobody has priced.
        run(runner, register, "demo", "seed")
        run(runner, register, "account", "add", "ROY-02", "Royd Groundworks")
        result = run(
            runner,
            register,
            "invoice",
            "draft",
            "INV-2211",
            "--account",
            "ROY-02",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
        )
        assert result.exit_code != 0
        assert "no ticket in this run" in result.output

    def test_tax(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register, "INV-2211", "--tax", "6")
        result = run(runner, register, "invoice", "show", "INV-2211")
        assert "tax" in result.output


class CaseLifecycle:
    def test_issue(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(runner, register, "invoice", "issue", "INV-2211")
        assert result.exit_code == 0
        assert "issued" in result.output

    def test_issuing_twice(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        run(runner, register, "invoice", "issue", "INV-2211")
        result = run(runner, register, "invoice", "issue", "INV-2211")
        assert result.exit_code != 0
        assert "INVOICE_ALREADY_ISSUED" in result.output

    def test_a_part_payment(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        run(runner, register, "invoice", "issue", "INV-2211")
        result = run(
            runner,
            register,
            "invoice",
            "pay",
            "INV-2211",
            "--amount",
            "$500",
            "--on",
            "2024-06-20",
            "--reference",
            "CHK-1",
        )
        assert "part_paid" in result.output
        assert "prompt payment discount" in result.output

    def test_paying_a_draft(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(
            runner,
            register,
            "invoice",
            "pay",
            "INV-2211",
            "--amount",
            "$500",
            "--on",
            "2024-06-20",
        )
        assert result.exit_code != 0
        assert "INVOICE_NOT_ISSUED" in result.output

    def test_void(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        run(runner, register, "invoice", "issue", "INV-2211")
        result = run(runner, register, "invoice", "void", "INV-2211")
        assert "void" in result.output

    def test_voiding_one_that_took_money(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        run(runner, register, "invoice", "issue", "INV-2211")
        run(
            runner,
            register,
            "invoice",
            "pay",
            "INV-2211",
            "--amount",
            "$500",
            "--on",
            "2024-06-20",
        )
        result = run(runner, register, "invoice", "void", "INV-2211")
        assert result.exit_code != 0
        assert "INVOICE_HAS_PAYMENTS" in result.output


class CaseListings:
    def test_list(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(runner, register, "invoice", "list", "--on", "2024-07-01")
        assert "INV-2211" in result.output

    def test_owed_leaves_out_the_draft(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(runner, register, "invoice", "list", "--owed")
        assert "INV-2211" not in result.output

    def test_by_account(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(runner, register, "invoice", "list", "--account", "ASH-01")
        assert "INV-2211" in result.output

    def test_aging(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        run(runner, register, "invoice", "issue", "INV-2211")
        result = run(runner, register, "invoice", "aging", "--on", "2024-08-20")
        assert "overdue" in result.output
        assert "31 to 60" in result.output

    def test_unbilled(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        result = run(
            runner,
            register,
            "invoice",
            "unbilled",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
        )
        assert "4 ticket(s)" in result.output

    def test_nothing_unbilled_after_drafting(self, runner: CliRunner, register: str) -> None:
        stocked(runner, register)
        draft(runner, register)
        result = run(
            runner,
            register,
            "invoice",
            "unbilled",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
        )
        assert "0 ticket(s)" in result.output

    def test_showing_an_unknown_invoice(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "invoice", "show", "INV-9").exit_code != 0
