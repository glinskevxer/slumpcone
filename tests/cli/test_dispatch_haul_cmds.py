from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run
from tests.cli.test_dispatch_cmds import booked


class CaseFilingByHand:
    def test_it_files_a_profile(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "dispatch",
            "haul",
            "P-2024-118",
            "--out",
            "35",
            "--notes",
            "off the map",
        )
        assert result.exit_code == 0
        assert "round trip" in result.output

    def test_it_shows_up_in_the_listing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "dispatch", "haul", "P-2024-118", "--out", "35")
        result = run(runner, register, "dispatch", "profiles")
        assert "P-2024-118" in result.output
        assert "1 profile(s)" in result.output

    def test_the_note_is_kept(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "dispatch", "haul", "P-2024-118", "--notes", "off the map")
        assert "off the map" in run(runner, register, "dispatch", "profiles").output

    def test_a_hand_entered_profile_has_no_measured_day(
        self, runner: CliRunner, register: str
    ) -> None:
        run(runner, register, "dispatch", "haul", "P-2024-118")
        result = run(runner, register, "dispatch", "profiles")
        assert "-" in result.output

    def test_nothing_on_file(self, runner: CliRunner, register: str) -> None:
        assert "0 profile(s)" in run(runner, register, "dispatch", "profiles").output

    def test_forgetting_one(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "dispatch", "haul", "P-2024-118")
        result = run(runner, register, "dispatch", "forget", "P-2024-118")
        assert "dropped" in result.output
        assert "0 profile(s)" in run(runner, register, "dispatch", "profiles").output

    def test_forgetting_one_that_is_not_there(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "dispatch", "forget", "P-9").exit_code != 0


class CaseTheProfileWins:
    def test_a_filed_profile_moves_the_batch_time(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        plain = run(runner, register, "dispatch", "schedule", "ORD-1")
        run(runner, register, "dispatch", "haul", "P-2024-118", "--out", "45")
        with_profile = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert "06:30" in plain.output
        assert "06:05" in with_profile.output

    def test_the_profile_can_be_ignored(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        run(runner, register, "dispatch", "haul", "P-2024-118", "--out", "45")
        result = run(runner, register, "dispatch", "schedule", "ORD-1", "--ignore-profile")
        assert "06:30" in result.output

    def test_a_job_with_no_profile_keeps_the_given_cycle(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(runner, register, "dispatch", "schedule", "ORD-1", "--out", "45")
        assert "06:05" in result.output


class CaseFitting:
    def test_it_fits_off_the_seeded_deliveries(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "fit",
            "P-2024-118",
            "--on",
            "2024-06-12",
            "--label",
            "Route 9 shoulder",
        )
        assert result.exit_code == 0
        assert "delivery record(s)" in result.output
        assert "round trip" in result.output

    def test_the_fit_is_recorded_with_its_day(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        run(
            runner,
            register,
            "dispatch",
            "fit",
            "P-2024-118",
            "--on",
            "2024-06-12",
            "--label",
            "Route 9 shoulder",
        )
        result = run(runner, register, "dispatch", "profiles")
        assert "2024-06-12" in result.output
        assert "fitted from delivery records" in result.output

    def test_a_label_that_matches_nothing(self, runner: CliRunner, register: str) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "fit",
            "P-2024-118",
            "--on",
            "2024-06-12",
            "--label",
            "somewhere else",
        )
        assert result.exit_code != 0
        assert "HAUL_FIT_TOO_THIN" in result.output

    def test_the_label_is_matched_without_regard_to_case(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        result = run(
            runner,
            register,
            "dispatch",
            "fit",
            "P-2024-118",
            "--on",
            "2024-06-12",
            "--label",
            "route 9 SHOULDER",
        )
        assert result.exit_code == 0

    def test_the_fitted_profile_then_drives_the_schedule(
        self, runner: CliRunner, register: str
    ) -> None:
        booked(runner, register)
        run(
            runner,
            register,
            "dispatch",
            "fit",
            "P-2024-118",
            "--on",
            "2024-06-12",
            "--label",
            "Route 9 shoulder",
        )
        result = run(runner, register, "dispatch", "schedule", "ORD-1")
        assert result.exit_code == 0
        assert "trucks needed" in result.output


class CaseTheCycleOptions:
    def test_every_leg_reaches_the_command(self, runner: CliRunner, register: str) -> None:
        # The five legs are all integers in minutes, so a wrong order is silent.
        # Giving each one a different value proves each lands where it belongs.
        run(
            runner,
            register,
            "dispatch",
            "haul",
            "P-2024-118",
            "--load",
            "11",
            "--out",
            "22",
            "--site",
            "33",
            "--back",
            "44",
            "--wash",
            "55",
        )
        result = run(runner, register, "dispatch", "profiles")
        line = [row for row in result.output.splitlines() if "P-2024-118" in row][0]
        assert line.split()[1:6] == ["11", "22", "33", "44", "55"]

    def test_the_round_trip_is_the_sum(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "dispatch",
            "haul",
            "P-2024-118",
            "--load",
            "11",
            "--out",
            "22",
            "--site",
            "33",
            "--back",
            "44",
            "--wash",
            "55",
        )
        assert "165 min round trip" in result.output

    def test_the_trip_to_site_is_loading_plus_haul_out(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(
            runner,
            register,
            "dispatch",
            "haul",
            "P-2024-118",
            "--load",
            "11",
            "--out",
            "22",
            "--site",
            "33",
            "--back",
            "44",
            "--wash",
            "55",
        )
        assert "33 min to site" in result.output

    def test_the_defaults_still_apply(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "dispatch", "haul", "P-2024-118")
        assert "70 min round trip" in result.output

    def test_the_options_still_show_in_help(self, runner: CliRunner, register: str) -> None:
        text = run(runner, register, "dispatch", "haul", "--help").output
        for name in ("--load", "--out", "--site", "--back", "--wash"):
            assert name in text

    def test_the_command_takes_no_cycle_option_of_its_own(
        self, runner: CliRunner, register: str
    ) -> None:
        # The collapsing happens inside the decorator, so nobody can pass one.
        assert "--cycle" not in run(runner, register, "dispatch", "haul", "--help").output
