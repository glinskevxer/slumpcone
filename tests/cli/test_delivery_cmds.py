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


def add_truck(runner: CliRunner, register: str) -> Result:
    return run(
        runner,
        register,
        "delivery",
        "truck",
        "TR-114",
        "--drum",
        "11 yd3",
        "--fleet",
        "Northmoor",
        "--uniformity",
        "2024-02-01",
    )


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


def record(runner: CliRunner, register: str, *extra: str) -> Result:
    return run(
        runner,
        register,
        "delivery",
        "record",
        "881204",
        "--truck",
        "TR-114",
        "--batched",
        "2024-06-12T07:42",
        "--left",
        "2024-06-12T07:48",
        "--arrived",
        "2024-06-12T08:10",
        "--start",
        "2024-06-12T08:17",
        "--finish",
        "2024-06-12T08:34",
        "--rev-arrival",
        "140",
        "--rev-discharge",
        "210",
        *extra,
    )


class CaseTrucks:
    def test_add(self, runner: CliRunner, register: str) -> None:
        result = add_truck(runner, register)
        assert result.exit_code == 0
        assert "TR-114" in result.output
        assert "mixing 6.93 yd3" in result.output

    def test_list(self, runner: CliRunner, register: str) -> None:
        add_truck(runner, register)
        result = run(runner, register, "delivery", "trucks")
        assert "TR-114" in result.output
        assert "agitating" in result.output

    def test_a_truck_with_no_uniformity_test(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "delivery", "truck", "TR-9", "--drum", "10 yd3")
        result = run(runner, register, "delivery", "trucks")
        assert "TR-9" in result.output

    def test_a_bad_drum_volume(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "delivery", "truck", "TR-9", "--drum", "10 lb")
        assert result.exit_code != 0
        assert "drum volume is a volume" in result.output


class CaseRecord:
    def test_it_records_a_delivery(self, runner: CliRunner, register: str) -> None:
        result = record(runner, register)
        assert result.exit_code == 0
        assert "881204" in result.output
        assert "52 min" in result.output

    def test_stages_out_of_order_are_refused(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "delivery",
            "record",
            "881204",
            "--truck",
            "TR-114",
            "--batched",
            "2024-06-12T07:42",
            "--left",
            "2024-06-12T07:30",
        )
        assert result.exit_code != 0
        assert "is before" in result.output

    def test_updating_keeps_the_water(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        record(runner, register)
        run(
            runner,
            register,
            "delivery",
            "water",
            "881204",
            "--amount",
            "2 gal",
            "--at",
            "2024-06-12T08:15",
        )
        record(runner, register, "--returned", "0.5 yd3")
        result = run(
            runner, register, "delivery", "list", "--from", "2024-06-01", "--to", "2024-06-30"
        )
        assert "2.0 gal" in result.output
        assert "0.50 yd3" in result.output


class CaseWater:
    def test_a_small_addition(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        record(runner, register)
        result = run(
            runner,
            register,
            "delivery",
            "water",
            "881204",
            "--amount",
            "1 gal",
            "--at",
            "2024-06-12T08:15",
        )
        assert result.exit_code == 0
        assert "added by purchaser" in result.output

    def test_a_large_addition_voids_the_warranty(
        self, runner: CliRunner, register: str
    ) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        record(runner, register)
        result = run(
            runner,
            register,
            "delivery",
            "water",
            "881204",
            "--amount",
            "20 gal",
            "--at",
            "2024-06-12T08:15",
        )
        assert "warranty void" in result.output

    def test_the_producer_does_not_void_it(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        record(runner, register)
        result = run(
            runner,
            register,
            "delivery",
            "water",
            "881204",
            "--amount",
            "20 gal",
            "--at",
            "2024-06-12T08:15",
            "--by",
            "producer",
        )
        assert "warranty void" not in result.output

    def test_water_on_an_unknown_delivery(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "delivery",
            "water",
            "881299",
            "--amount",
            "1 gal",
            "--at",
            "2024-06-12T08:15",
        )
        assert result.exit_code != 0


class CaseHaul:
    def test_a_good_haul(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(runner, register, "delivery", "haul", "881204")
        assert "inside" in result.output
        assert "90 min, 300 revolutions" in result.output

    def test_a_late_haul(self, runner: CliRunner, register: str) -> None:
        record(runner, register, "--finish", "2024-06-12T09:42")
        result = run(runner, register, "delivery", "haul", "881204")
        assert "minutes after batching" in result.output

    def test_a_retarder_forgives_it(self, runner: CliRunner, register: str) -> None:
        record(runner, register, "--finish", "2024-06-12T09:42")
        result = run(runner, register, "delivery", "haul", "881204", "--retarder")
        assert "inside" in result.output

    def test_hot_weather_tightens_it(self, runner: CliRunner, register: str) -> None:
        record(runner, register, "--finish", "2024-06-12T09:00")
        result = run(runner, register, "delivery", "haul", "881204", "--temp", "95")
        assert "60 min" in result.output
        assert "minutes after batching" in result.output

    def test_an_unfinished_load_cannot_be_judged(
        self, runner: CliRunner, register: str
    ) -> None:
        run(
            runner,
            register,
            "delivery",
            "record",
            "881204",
            "--truck",
            "TR-114",
            "--batched",
            "2024-06-12T07:42",
        )
        result = run(runner, register, "delivery", "haul", "881204")
        assert result.exit_code != 0
        assert "has not finished" in result.output


class CaseList:
    def test_a_window(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(
            runner, register, "delivery", "list", "--from", "2024-06-01", "--to", "2024-06-30"
        )
        assert "881204" in result.output

    def test_unfinished_only(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        run(
            runner,
            register,
            "delivery",
            "record",
            "881205",
            "--truck",
            "TR-114",
            "--batched",
            "2024-06-12T09:00",
        )
        result = run(
            runner,
            register,
            "delivery",
            "list",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
            "--unfinished",
        )
        assert "881205" in result.output
        assert "881204" not in result.output

    def test_by_truck(self, runner: CliRunner, register: str) -> None:
        record(runner, register)
        result = run(
            runner,
            register,
            "delivery",
            "list",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
            "--truck",
            "TR-999",
        )
        assert "881204" not in result.output
