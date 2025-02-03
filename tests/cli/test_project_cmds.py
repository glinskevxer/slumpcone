from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run
from tests.cli.test_batch_cmds import stock


def add_project(runner: CliRunner, register: str) -> Result:
    return run(
        runner,
        register,
        "project",
        "add",
        "P-2024-118",
        "Route 9 shoulder widening",
        "--owner",
        "County highways",
        "--start",
        "2024-05-01",
        "--finish",
        "2024-11-30",
    )


def add_class(runner: CliRunner, register: str, **extra: str) -> Result:
    args = [
        "project",
        "class",
        "P-2024-118",
        "SLAB",
        "--strength",
        "4000 psi",
        "--exposure",
        "F2 S1",
        "--nms",
        "1 in",
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return run(runner, register, *args)


class CaseProjects:
    def test_add(self, runner: CliRunner, register: str) -> None:
        result = add_project(runner, register)
        assert result.exit_code == 0
        assert "P-2024-118" in result.output

    def test_list(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        result = run(runner, register, "project", "list", "--on", "2024-06-12")
        assert "P-2024-118" in result.output
        assert "yes" in result.output

    def test_a_closed_project(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        result = run(runner, register, "project", "list", "--on", "2025-06-12")
        assert "no" in result.output

    def test_show(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        add_class(runner, register)
        result = run(runner, register, "project", "show", "P-2024-118", "--on", "2024-06-12")
        assert "SLAB" in result.output
        assert "County highways" in result.output

    def test_show_an_unknown_project(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "project", "show", "P-9").exit_code != 0

    def test_adding_again_keeps_the_classes(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        add_class(runner, register)
        add_project(runner, register)
        assert "SLAB" in run(runner, register, "project", "show", "P-2024-118").output


class CaseClasses:
    def test_add(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        result = add_class(runner, register)
        assert result.exit_code == 0
        assert "SLAB" in result.output
        assert "w/cm max 0.45" in result.output

    def test_a_class_on_an_unknown_project(self, runner: CliRunner, register: str) -> None:
        assert add_class(runner, register).exit_code != 0

    def test_replacing_a_class(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        add_class(runner, register)
        add_class(runner, register, strength="4500 psi")
        result = run(runner, register, "project", "show", "P-2024-118")
        assert "4500 psi" in result.output
        assert "4000 psi" not in result.output


class CaseSubmittals:
    def stock_all(self, runner: CliRunner, register: str) -> None:
        stock(runner, register)
        add_project(runner, register)
        add_class(runner, register)

    def test_submit(self, runner: CliRunner, register: str) -> None:
        self.stock_all(runner, register)
        result = run(
            runner,
            register,
            "project",
            "submit",
            "SUB-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--mix",
            "4000P-57",
            "--on",
            "2024-04-02",
            "--required-average",
            "5200 psi",
        )
        assert result.exit_code == 0
        assert "SUB-1" in result.output

    def test_a_submittal_that_does_not_satisfy_the_class(
        self, runner: CliRunner, register: str
    ) -> None:
        self.stock_all(runner, register)
        add_class(runner, register, min_cementitious="900 lb")
        result = run(
            runner,
            register,
            "project",
            "submit",
            "SUB-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--mix",
            "4000P-57",
            "--on",
            "2024-04-02",
        )
        assert "cementitious content" in result.output

    def test_approve(self, runner: CliRunner, register: str) -> None:
        self.stock_all(runner, register)
        run(
            runner,
            register,
            "project",
            "submit",
            "SUB-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--mix",
            "4000P-57",
            "--on",
            "2024-04-02",
        )
        result = run(
            runner,
            register,
            "project",
            "approve",
            "SUB-1",
            "--on",
            "2024-04-10",
            "--reviewer",
            "County engineer",
        )
        assert "approved" in result.output

    def test_reject(self, runner: CliRunner, register: str) -> None:
        self.stock_all(runner, register)
        run(
            runner,
            register,
            "project",
            "submit",
            "SUB-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--mix",
            "4000P-57",
            "--on",
            "2024-04-02",
        )
        result = run(
            runner, register, "project", "approve", "SUB-1", "--on", "2024-04-10", "--reject"
        )
        assert "rejected" in result.output

    def test_deciding_twice(self, runner: CliRunner, register: str) -> None:
        self.stock_all(runner, register)
        run(
            runner,
            register,
            "project",
            "submit",
            "SUB-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--mix",
            "4000P-57",
            "--on",
            "2024-04-02",
        )
        run(runner, register, "project", "approve", "SUB-1", "--on", "2024-04-10")
        result = run(runner, register, "project", "approve", "SUB-1", "--on", "2024-05-10")
        assert result.exit_code != 0
        assert "SUBMITTAL_SETTLED" in result.output

    def test_approved_listing(self, runner: CliRunner, register: str) -> None:
        self.stock_all(runner, register)
        run(
            runner,
            register,
            "project",
            "submit",
            "SUB-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--mix",
            "4000P-57",
            "--on",
            "2024-04-02",
        )
        run(runner, register, "project", "approve", "SUB-1", "--on", "2024-04-10")
        result = run(
            runner,
            register,
            "project",
            "approved",
            "P-2024-118",
            "SLAB",
            "--on",
            "2024-06-12",
        )
        assert "SUB-1" in result.output


class CaseOrders:
    def test_book_one(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        result = run(
            runner,
            register,
            "project",
            "order",
            "ORD-9912",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--volume",
            "60 yd3",
            "--on",
            "2024-06-12",
            "--mix",
            "4000P-57",
            "--rate",
            "24 yd3",
            "--placement",
            "Route 9",
        )
        assert result.exit_code == 0
        assert "ORD-9912" in result.output

    def test_a_bad_volume(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        result = run(
            runner,
            register,
            "project",
            "order",
            "ORD-1",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--volume",
            "60 lb",
            "--on",
            "2024-06-12",
        )
        assert result.exit_code != 0

    def test_the_board(self, runner: CliRunner, register: str) -> None:
        add_project(runner, register)
        run(
            runner,
            register,
            "project",
            "order",
            "ORD-9912",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--volume",
            "60 yd3",
            "--on",
            "2024-06-12",
            "--mix",
            "4000P-57",
            "--placement",
            "Route 9",
        )
        result = run(runner, register, "project", "board", "--on", "2024-06-12")
        assert "Dispatch board, 2024-06-12" in result.output
        assert "ORD-9912" in result.output

    def test_an_empty_board(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "project", "board", "--on", "2024-06-12")
        assert "order" in result.output
