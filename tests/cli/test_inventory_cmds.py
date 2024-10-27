from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from slumpcone.cli.main import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def register(tmp_path: Path) -> str:
    return str(tmp_path / "r.sqlite3")


def run(runner: CliRunner, register: str, *args: str) -> Result:
    return runner.invoke(cli, ["--register", register, *args])


def stock_yard(runner: CliRunner, register: str) -> None:
    run(runner, register, "plant", "add", "PL-1", "Northmoor")
    run(
        runner,
        register,
        "plant",
        "silo",
        "PL-1",
        "SI-1",
        "Cement silo one",
        "--material",
        "CEM-I",
        "--capacity",
        "200000 lb",
        "--level",
        "120000 lb",
        "--low",
        "30000 lb",
    )


def receive(runner: CliRunner, register: str, *extra: str) -> Result:
    return run(
        runner,
        register,
        "inventory",
        "receive",
        "RCV-2211",
        "--plant",
        "PL-1",
        "--silo",
        "SI-1",
        "--material",
        "CEM-I",
        "--quantity",
        "48000 lb",
        "--at",
        "2024-06-11T05:40",
        "--supplier",
        "Ashfield Cement",
        "--certificate",
        "MC-2024-0412",
        *extra,
    )


class CaseReceive:
    def test_it_raises_the_level(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        result = receive(runner, register)
        assert result.exit_code == 0
        assert "RCV-2211" in result.output
        assert "168000 lb" in result.output

    def test_the_wrong_material_is_refused(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "receive",
            "RCV-1",
            "--plant",
            "PL-1",
            "--silo",
            "SI-1",
            "--material",
            "SCM-F",
            "--quantity",
            "48000 lb",
            "--at",
            "2024-06-11T05:40",
        )
        assert result.exit_code != 0
        assert "holds CEM-I" in result.output

    def test_a_missing_certificate_is_a_note_not_a_refusal(
        self, runner: CliRunner, register: str
    ) -> None:
        stock_yard(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "receive",
            "RCV-1",
            "--plant",
            "PL-1",
            "--silo",
            "SI-1",
            "--material",
            "CEM-I",
            "--quantity",
            "48000 lb",
            "--at",
            "2024-06-11T05:40",
        )
        assert result.exit_code == 0
        assert "no certificate reference" in result.output

    def test_no_headroom_is_refused(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        result = receive(runner, register, "--quantity", "150000 lb")
        assert result.exit_code != 0
        assert "headroom" in result.output

    def test_a_duplicate_reference(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = receive(runner, register)
        assert result.exit_code != 0


class CaseDraw:
    def test_it_lowers_the_level(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "draw",
            "--plant",
            "PL-1",
            "--silo",
            "SI-1",
            "--quantity",
            "20000 lb",
            "--at",
            "2024-06-12T07:42",
            "--reference",
            "881204",
        )
        assert result.exit_code == 0
        assert "100000 lb" in result.output

    def test_drawing_more_than_there_is(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "draw",
            "--plant",
            "PL-1",
            "--silo",
            "SI-1",
            "--quantity",
            "200000 lb",
        )
        assert result.exit_code != 0
        assert "SILO_SHORT" in result.output

    def test_an_unknown_silo(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "draw",
            "--plant",
            "PL-1",
            "--silo",
            "SI-9",
            "--quantity",
            "100 lb",
        )
        assert result.exit_code != 0


class CaseReconcile:
    def test_a_correction_is_recorded(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "reconcile",
            "--plant",
            "PL-1",
            "--silo",
            "SI-1",
            "--measured",
            "40000 lb",
            "--at",
            "2024-06-12T18:00",
        )
        assert result.exit_code == 0
        assert "correction" in result.output
        assert "recorded" in result.output

    def test_agreement_records_nothing(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "reconcile",
            "--plant",
            "PL-1",
            "--silo",
            "SI-1",
            "--measured",
            "48000 lb",
            "--at",
            "2024-06-12T18:00",
        )
        assert "none" in result.output


class CaseListings:
    def test_the_ledger(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "ledger",
            "--plant",
            "PL-1",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "Ledger at PL-1" in result.output
        assert "receipt" in result.output

    def test_the_ledger_for_one_silo(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "ledger",
            "--plant",
            "PL-1",
            "--silo",
            "si 9",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "RCV-2211" not in result.output

    def test_the_report(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "report",
            "--plant",
            "PL-1",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "Inventory at PL-1" in result.output
        assert "SI-1" in result.output

    def test_the_receipts_listing(self, runner: CliRunner, register: str) -> None:
        stock_yard(runner, register)
        receive(runner, register)
        result = run(
            runner,
            register,
            "inventory",
            "receipts",
            "--plant",
            "PL-1",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "RCV-2211" in result.output
        assert "MC-2024-0412" in result.output
