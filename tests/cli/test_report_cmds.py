from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run
from tests.cli.test_batch_cmds import stock


def write_ticket(
    runner: CliRunner, register: str, number: str = "881204", **extra: str
) -> None:
    args = [
        "batch",
        "ticket",
        number,
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
    ]
    for key, value in extra.items():
        args.extend([f"--{key}", value])
    run(runner, register, *args)


class CaseProduction:
    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "report",
            "production",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "Production, 2024-06-01 to 2024-06-30" in result.output
        assert "loads" in result.output

    def test_with_tickets(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        result = run(
            runner,
            register,
            "report",
            "production",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "4000P-57" in result.output
        assert "By day" in result.output


class CaseNonConformance:
    def test_a_clean_window(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
        result = run(
            runner,
            register,
            "report",
            "nonconformance",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "Non conformance" in result.output
        assert "major" in result.output

    def test_a_ticket_with_a_finding(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register, actual="CEM-I:4400")
        result = run(
            runner,
            register,
            "report",
            "nonconformance",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "BATCH_WEIGHT_OUT_OF_TOLERANCE" in result.output

    def test_a_rejected_load_shows_up(self, runner: CliRunner, register: str) -> None:
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
        result = run(
            runner,
            register,
            "report",
            "nonconformance",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "LOAD_REJECTED" in result.output

    def test_a_late_haul_shows_up(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        write_ticket(runner, register)
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
            "--finish",
            "2024-06-12T09:42",
            "--rev-discharge",
            "210",
        )
        result = run(
            runner,
            register,
            "report",
            "nonconformance",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "DISCHARGE_LATE" in result.output


class CaseCompliance:
    def test_an_empty_register(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "report", "compliance", "--on", "2024-06-12")
        assert "Compliance calendar" in result.output

    def test_with_a_plant_and_paper(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner, register, "report", "compliance", "--on", "2024-06-12", "--within", "120"
        )
        assert "scale calibration" in result.output

    def test_the_horizon_is_honoured(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner, register, "report", "compliance", "--on", "2024-06-12", "--within", "5"
        )
        assert "to 5 days" in result.output


class CaseYield:
    def test_no_unit_weight_tests(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "report",
            "yield",
            "4000P-57",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "Yield for 4000P-57" in result.output
        assert "loads" in result.output

    def test_with_a_unit_weight_test(self, runner: CliRunner, register: str) -> None:
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
            "--unit-weight",
            "142.6",
        )
        result = run(
            runner,
            register,
            "report",
            "yield",
            "4000P-57",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "881204" in result.output
        assert "rel yield" in result.output

    def test_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "report",
            "yield",
            "4000P-58",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert result.exit_code != 0


class CaseFleet:
    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "report",
            "fleet",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert result.exit_code == 0
        assert "Fleet" in result.output

    def test_with_deliveries(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(
            runner,
            register,
            "report",
            "fleet",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "TR-114" in result.output
        assert "avg turn" in result.output
        assert "Where the time went" in result.output

    def test_the_shift_and_cycle_change_the_utilisation(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        long_shift = run(
            runner,
            register,
            "report",
            "fleet",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
            "--shift",
            "1200",
        )
        short_shift = run(
            runner,
            register,
            "report",
            "fleet",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
            "--shift",
            "300",
        )
        assert long_shift.output != short_shift.output


class CaseFrequency:
    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "report",
            "frequency",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert result.exit_code == 0
        assert "Sampling frequency" in result.output

    def test_with_production(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(
            runner,
            register,
            "report",
            "frequency",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "4000P-57" in result.output
        assert "governed by" in result.output

    def test_a_surface_area_can_raise_the_requirement(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        plain = run(
            runner,
            register,
            "report",
            "frequency",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        with_area = run(
            runner,
            register,
            "report",
            "frequency",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
            "--area",
            "60000 ft2",
        )
        assert "surface area" in with_area.output
        assert "surface area" not in plain.output
