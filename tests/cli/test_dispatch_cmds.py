from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run
from tests.cli.test_project_cmds import add_class, add_project


def booked(
    runner: CliRunner,
    register: str,
    number: str = "ORD-1",
    *,
    volume: str = "90 yd3",
    rate: str | None = "30 yd3",
    on: str = "2024-06-12",
) -> None:
    run(runner, register, "demo", "seed", "--no-yard")
    add_project(runner, register)
    add_class(runner, register)
    args = [
        "project",
        "order",
        number,
        "--project",
        "P-2024-118",
        "--class",
        "SLAB",
        "--volume",
        volume,
        "--on",
        on,
    ]
    if rate is not None:
        args.extend(["--rate", rate])
    run(runner, register, *args)


class CaseSchedule:
    def test_it_lays_the_pour_out(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert result.exit_code == 0
        assert "10" in result.output
        assert "spacing" in result.output

    def test_the_first_load_arrives_at_seven(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert "07:00" in result.output

    def test_the_first_batch_is_earlier_than_the_arrival(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert "06:30" in result.output

    def test_a_longer_haul_moves_the_batch_time_back(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "schedule", "ORD-1", "--out", "45")
        assert "06:05" in result.output

    def test_a_long_haul_flags_the_discharge_limit(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(
            runner, register, "dispatch", "schedule", "ORD-1", "--out", "60", "--site", "40"
        )
        assert "at risk" in result.output

    def test_a_short_haul_clears_it(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert "clears" in result.output

    def test_a_short_last_load_is_marked(self, runner: CliRunner, register: str) -> None:
        booked(runner, register, volume="85 yd3")
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert "short" in result.output

    def test_an_order_with_no_rate(self, runner: CliRunner, register: str) -> None:
        booked(runner, register, rate=None)
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert result.exit_code != 0
        assert "carries no placing rate" in result.output

    def test_a_rate_on_the_command_line_fills_it_in(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register, rate=None)
        result = run(runner, register, "dispatch", "schedule", "ORD-1", "--rate", "30 yd3")
        assert result.exit_code == 0

    def test_an_explicit_start(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(
            runner, register, "dispatch", "schedule", "ORD-1", "--start", "2024-06-12T05:30"
        )
        assert "05:30" in result.output

    def test_an_unknown_order(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        assert run(runner, register, "dispatch", "schedule", "ORD-9").exit_code != 0


class CaseBoard:
    def test_four_trucks_hold_it(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "board",
            "ORD-1",
            "--truck",
            "TR-1",
            "--truck",
            "TR-2",
            "--truck",
            "TR-3",
            "--truck",
            "TR-4",
        )
        assert "on schedule" in result.output
        assert "4 of 4 truck(s) needed" in result.output

    def test_two_trucks_run_late(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "board",
            "ORD-1",
            "--truck",
            "TR-1",
            "--truck",
            "TR-2",
        )
        assert "late by up to" in result.output

    def test_refusing_to_slip_leaves_loads_unassigned(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "board",
            "ORD-1",
            "--truck",
            "TR-1",
            "--no-slip",
        )
        assert "unassigned: load" in result.output

    def test_it_falls_back_to_the_fleet_on_file(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "board", "ORD-1")
        assert result.exit_code == 0
        assert "truck(s) needed" in result.output

    def test_the_assignment_table_names_every_load(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "board",
            "ORD-1",
            "--truck",
            "TR-1",
            "--truck",
            "TR-2",
            "--truck",
            "TR-3",
            "--truck",
            "TR-4",
        )
        assert "scheduled" in result.output
        assert "slip" in result.output


class CaseAt:
    def test_it_says_what_each_truck_is_doing(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "at",
            "ORD-1",
            "2024-06-12T07:05",
            "--truck",
            "TR-1",
            "--truck",
            "TR-2",
            "--truck",
            "TR-3",
            "--truck",
            "TR-4",
        )
        assert result.exit_code == 0
        assert "carrying" in result.output

    def test_early_in_the_pour_somebody_is_on_site(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "at",
            "ORD-1",
            "2024-06-12T07:05",
            "--truck",
            "TR-1",
            "--truck",
            "TR-2",
            "--truck",
            "TR-3",
            "--truck",
            "TR-4",
        )
        assert "on site" in result.output

    def test_long_after_it_is_over_nobody_is_carrying(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "at",
            "ORD-1",
            "2024-06-12T20:00",
            "--truck",
            "TR-1",
            "--truck",
            "TR-2",
        )
        assert "0 of 2 carrying" in result.output


class CaseDay:
    def test_one_pour(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "day", "--on", "2024-06-12")
        assert "1 pour(s), 0 overlap(s)" in result.output

    def test_two_pours_at_the_same_time_collide(self, runner: CliRunner, register: str) -> None:
        booked(runner, register, "ORD-1")
        run(
            runner,
            register,
            "project",
            "order",
            "ORD-2",
            "--project",
            "P-2024-118",
            "--class",
            "SLAB",
            "--volume",
            "45 yd3",
            "--on",
            "2024-06-12",
            "--rate",
            "30 yd3",
        )
        result = run(runner, register, "dispatch", "day", "--on", "2024-06-12")
        assert "2 pour(s), 1 overlap(s)" in result.output
        assert "want the plant at the same time" in result.output

    def test_a_day_with_nothing_booked(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "day", "--on", "2024-07-04")
        assert "0 pour(s), 0 overlap(s)" in result.output


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "dispatch" in run(runner, register, "--help").output
