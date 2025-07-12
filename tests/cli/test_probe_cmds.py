from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run

TODAY = "2024-06-12"
OLD = "2024-04-01"


def do_check(
    runner: CliRunner,
    register: str,
    probe: str = "MP-1",
    *,
    read: str = "4.5",
    oven: str = "4.3",
    on: str = TODAY,
    extra: tuple[str, ...] = (),
) -> Result:
    return run(
        runner,
        register,
        "probe",
        "check",
        probe,
        "--plant",
        "PL-1",
        "--probe-read",
        read,
        "--oven",
        oven,
        "--on",
        on,
        *extra,
    )


class CaseChecks:
    def test_one_lands(self, runner: CliRunner, register: str) -> None:
        result = do_check(runner, register)
        assert result.exit_code == 0
        assert "0.20 points high" in result.output

    def test_a_probe_reading_low(self, runner: CliRunner, register: str) -> None:
        result = do_check(runner, register, read="4.0")
        assert "points low" in result.output

    def test_a_failing_check(self, runner: CliRunner, register: str) -> None:
        result = do_check(runner, register, read="6.0")
        assert "out of limit" in result.output

    def test_moisture_off_the_scale(self, runner: CliRunner, register: str) -> None:
        result = do_check(runner, register, oven="45")
        assert result.exit_code != 0
        assert "PROBE_MOISTURE_OFF_SCALE" in result.output

    def test_the_same_probe_twice_in_a_day(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register)
        assert do_check(runner, register).exit_code != 0

    def test_replace(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register)
        assert do_check(runner, register, extra=("--replace",)).exit_code == 0

    def test_two_plants_keep_their_own_bin_one(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register)
        result = run(
            runner,
            register,
            "probe",
            "check",
            "MP-1",
            "--plant",
            "PL-2",
            "--probe-read",
            "4.5",
            "--oven",
            "4.3",
            "--on",
            TODAY,
        )
        assert result.exit_code == 0

    def test_the_window_listing(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, "MP-1")
        do_check(runner, register, "MP-2")
        result = run(
            runner,
            register,
            "probe",
            "checks",
            "--plant",
            "PL-1",
            "--from",
            TODAY,
            "--to",
            TODAY,
        )
        assert "2 check(s)" in result.output

    def test_an_empty_window(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "probe",
            "checks",
            "--plant",
            "PL-1",
            "--from",
            TODAY,
            "--to",
            TODAY,
        )
        assert "0 check(s)" in result.output


class CaseShow:
    def test_a_recently_checked_probe(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register)
        result = run(
            runner, register, "probe", "show", "MP-1", "--plant", "PL-1", "--on", TODAY
        )
        assert "may batch" in result.output
        assert "good" in result.output

    def test_the_offset_is_signed(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register)
        result = run(
            runner, register, "probe", "show", "MP-1", "--plant", "PL-1", "--on", TODAY
        )
        assert "+0.20" in result.output

    def test_an_overdue_probe(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, on=OLD)
        result = run(
            runner, register, "probe", "show", "MP-1", "--plant", "PL-1", "--on", TODAY
        )
        assert "overdue" in result.output

    def test_a_drifting_probe(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, read="4.35", oven="4.3", on="2024-06-01")
        do_check(runner, register, read="4.9", oven="4.2", on="2024-06-10")
        result = run(
            runner, register, "probe", "show", "MP-1", "--plant", "PL-1", "--on", TODAY
        )
        assert "drifting" in result.output
        assert "yes" in result.output

    def test_a_probe_with_no_checks(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner, register, "probe", "show", "MP-9", "--plant", "PL-1", "--on", TODAY
        )
        assert result.exit_code == 0
        assert "0" in result.output
        assert "overdue" in result.output


class CaseCorrecting:
    def test_a_good_probe_corrects(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register)
        result = run(
            runner,
            register,
            "probe",
            "correct",
            "MP-1",
            "5.0",
            "--plant",
            "PL-1",
            "--on",
            TODAY,
        )
        assert result.exit_code == 0
        assert "4.80" in result.output

    def test_an_overdue_probe_refuses(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, on=OLD)
        result = run(
            runner,
            register,
            "probe",
            "correct",
            "MP-1",
            "5.0",
            "--plant",
            "PL-1",
            "--on",
            TODAY,
        )
        assert result.exit_code != 0
        assert "PROBE_NOT_IN_STANDING" in result.output

    def test_a_probe_that_failed_refuses(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, read="6.0")
        result = run(
            runner,
            register,
            "probe",
            "correct",
            "MP-1",
            "5.0",
            "--plant",
            "PL-1",
            "--on",
            TODAY,
        )
        assert result.exit_code != 0
        assert "failed" in result.output


class CaseListing:
    def test_every_probe(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, "MP-1")
        do_check(runner, register, "MP-2")
        result = run(runner, register, "probe", "list", "--plant", "PL-1", "--on", TODAY)
        assert "2 probe(s)" in result.output

    def test_only_the_ones_to_look_at(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, "MP-1")
        do_check(runner, register, "MP-2", on=OLD)
        result = run(
            runner,
            register,
            "probe",
            "list",
            "--plant",
            "PL-1",
            "--on",
            TODAY,
            "--attention",
        )
        assert "1 probe(s)" in result.output
        assert "MP-2" in result.output

    def test_the_blocked_probes_are_named(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, "MP-2", on=OLD)
        result = run(runner, register, "probe", "list", "--plant", "PL-1", "--on", TODAY)
        assert "do not batch off: MP-2" in result.output

    def test_a_clean_plant_names_nobody(self, runner: CliRunner, register: str) -> None:
        do_check(runner, register, "MP-1")
        result = run(runner, register, "probe", "list", "--plant", "PL-1", "--on", TODAY)
        assert "do not batch off" not in result.output

    def test_a_plant_with_no_probes(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "probe", "list", "--plant", "PL-9", "--on", TODAY)
        assert "0 probe(s)" in result.output


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "probe" in run(runner, register, "--help").output
