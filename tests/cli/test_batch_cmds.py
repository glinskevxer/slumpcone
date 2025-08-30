from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run
from tests.cli.test_mix_cmds import add_mix, stock_materials


def stock(runner: CliRunner, register: str, *, paper: bool = True) -> None:
    stock_materials(runner, register)
    run(
        runner,
        register,
        "material",
        "add",
        "AD-AE",
        "Air entrainer",
        "--class",
        "admixture",
        "--admixture-type",
        "air_entraining",
        "--sg",
        "1.01",
    )
    if paper:
        for code, kind in (
            ("CEM-I", "mill_certificate"),
            ("SCM-F", "mill_certificate"),
            ("CA-57", "source_approval"),
            ("CA-57", "gradation"),
            ("FA-1", "source_approval"),
            ("FA-1", "gradation"),
            ("AD-AE", "conformance_letter"),
        ):
            run(
                runner,
                register,
                "material",
                "certify",
                code,
                f"{code}-{kind[:4]}",
                "--kind",
                kind,
                "--issued",
                "2024-01-01",
                "--expires",
                "2024-12-31",
            )
    run(
        runner,
        register,
        "plant",
        "add",
        "PL-1",
        "Northmoor",
        "--max-load",
        "11 yd3",
    )
    run(
        runner,
        register,
        "plant",
        "scale",
        "PL-1",
        "SC-CEM",
        "Cement scale",
        "--capacity",
        "6000 lb",
        "--graduation",
        "1 lb",
        "--weighs",
        "cement,scm",
        "--calibrated",
        "2024-03-01",
    )
    run(
        runner,
        register,
        "plant",
        "scale",
        "PL-1",
        "SC-AGG",
        "Aggregate scale",
        "--capacity",
        "12000 lb",
        "--graduation",
        "2 lb",
        "--weighs",
        "coarse_aggregate,fine_aggregate",
        "--calibrated",
        "2024-03-01",
    )
    add_mix(runner, register)


class CasePlan:
    def test_a_batch_sheet(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "plan",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--on",
            "2024-06-12",
        )
        assert result.exit_code == 0
        assert "Batch sheet, 4000P-57 r1" in result.output
        assert "SC-CEM" in result.output
        assert "AD-AE" in result.output

    def test_moisture_moves_the_weights(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "plan",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--on",
            "2024-06-12",
            "--moisture",
            "CA-57:1.5:0.7",
            "--moisture",
            "FA-1:5.0:1.4",
        )
        assert "water cut from" in result.output

    def test_a_malformed_moisture(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "plan",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--moisture",
            "CA-57:1.5",
        )
        assert result.exit_code != 0
        assert "CODE:TOTAL:ABSORPTION" in result.output

    def test_a_moisture_that_is_not_a_number(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "plan",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--moisture",
            "CA-57:wet:0.7",
        )
        assert result.exit_code != 0
        assert "not a number" in result.output

    def test_a_batch_that_is_refused(self, runner: CliRunner, register: str) -> None:
        stock(runner, register, paper=False)
        result = run(
            runner,
            register,
            "batch",
            "plan",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--on",
            "2024-06-12",
        )
        assert result.exit_code != 0
        assert "BATCH_REFUSED" in result.output


class CaseCheck:
    def test_a_clean_check(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "check",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--on",
            "2024-06-12",
        )
        assert "nothing stops this batch" in result.output

    def test_a_check_with_reasons(self, runner: CliRunner, register: str) -> None:
        stock(runner, register, paper=False)
        result = run(
            runner,
            register,
            "batch",
            "check",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "9 yd3",
            "--on",
            "2024-06-12",
        )
        assert result.exit_code != 0
        assert "has no current" in result.output

    def test_an_oversize_load(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "check",
            "--plant",
            "PL-1",
            "--mix",
            "4000P-57",
            "--volume",
            "14 yd3",
            "--on",
            "2024-06-12",
        )
        assert "over the" in result.output


class CaseTicket:
    def write(self, runner: CliRunner, register: str, *extra: str) -> Result:
        return run(
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
            "Ashfield Paving",
            "--project",
            "Route 9 shoulder",
            *extra,
        )

    def test_it_writes_a_ticket(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = self.write(runner, register)
        assert result.exit_code == 0
        assert "ticket 881204" in result.output

    def test_a_recorded_weight_is_judged(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = self.write(runner, register, "--actual", "CEM-I:4400")
        assert "out high" in result.output

    def test_a_malformed_weight(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = self.write(runner, register, "--actual", "CEM-I")
        assert result.exit_code != 0
        assert "CODE:WEIGHT" in result.output

    def test_a_malformed_dose(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        result = self.write(runner, register, "--dose", "AD-AE")
        assert result.exit_code != 0
        assert "CODE:AMOUNT" in result.output

    def test_writing_the_same_number_twice(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        self.write(runner, register)
        result = self.write(runner, register)
        assert result.exit_code != 0
        assert "already on file" in result.output

    def test_show(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        self.write(runner, register)
        result = run(runner, register, "batch", "show", "881204")
        assert "Ticket 881204" in result.output
        assert "CEM-I" in result.output

    def test_show_an_unknown_ticket(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "batch", "show", "881299")
        assert result.exit_code != 0

    def test_audit(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        self.write(runner, register)
        result = run(
            runner, register, "batch", "audit", "--from", "2024-06-01", "--to", "2024-06-30"
        )
        assert "Ticket audit" in result.output
        assert "881204" in result.output

    def test_audit_by_plant(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        self.write(runner, register)
        result = run(
            runner,
            register,
            "batch",
            "audit",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
            "--plant",
            "PL-2",
        )
        assert "881204" not in result.output

    def test_day(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        self.write(runner, register)
        result = run(runner, register, "batch", "day", "--on", "2024-06-12")
        assert "tickets" in result.output
        assert "1" in result.output


class CasePrinting:
    def test_a_seeded_ticket_prints(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "batch", "print", "881204")
        assert result.exit_code == 0
        assert "Delivery ticket 881204" in result.output
        assert "complete under C94" in result.output

    def test_the_water_form_is_there(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "batch", "print", "881204")
        assert "initials" in result.output
        assert "receiver" in result.output

    def test_leaving_the_water_form_off_fails_the_check(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "batch", "print", "881204", "--no-water-line")
        assert result.exit_code != 0
        assert "no place left for it" in result.output

    def test_check_prints_no_ticket(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "batch", "print", "881204", "--check")
        assert "Delivery ticket" not in result.output
        assert "complete under C94" in result.output

    def test_the_optional_items_come_off_the_design(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "batch", "print", "881204")
        assert "cement content" in result.output

    def test_an_unknown_ticket(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        assert run(runner, register, "batch", "print", "999999").exit_code != 0
