from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run

DAY = "2024-06-12"


def read_tank(
    runner: CliRunner,
    register: str,
    name: str = "WW-1",
    sg: str = "1.02",
    *,
    on: str = DAY,
    extra: tuple[str, ...] = (),
) -> Result:
    return run(
        runner,
        register,
        "reclaim",
        "tank",
        name,
        "--plant",
        "PL-1",
        "--sg",
        sg,
        "--volume",
        "2000 gal",
        "--on",
        on,
        *extra,
    )


def came_back(runner: CliRunner, register: str, ticket: str = "881204", age: str = "45"):  # type: ignore[no-untyped-def]
    return run(
        runner,
        register,
        "reclaim",
        "returned",
        ticket,
        "--mix",
        "4000P-57",
        "--volume",
        "3 yd3",
        "--age",
        age,
        "--on",
        DAY,
    )


class CaseTanks:
    def test_a_reading_lands(self, runner: CliRunner, register: str) -> None:
        result = read_tank(runner, register)
        assert result.exit_code == 0
        assert "ppm solids" in result.output
        assert "usable" in result.output

    def test_a_dirty_tank_says_so(self, runner: CliRunner, register: str) -> None:
        result = read_tank(runner, register, sg="1.08")
        assert "over the solids limit" in result.output

    def test_water_lighter_than_water(self, runner: CliRunner, register: str) -> None:
        result = read_tank(runner, register, sg="0.99")
        assert result.exit_code != 0
        assert "WASH_WATER_LIGHTER_THAN_WATER" in result.output

    def test_the_same_tank_twice_in_a_day(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register)
        assert read_tank(runner, register).exit_code != 0

    def test_replace(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register)
        assert read_tank(runner, register, extra=("--replace",)).exit_code == 0

    def test_the_listing(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register, "WW-1", "1.02")
        read_tank(runner, register, "WW-2", "1.08")
        result = run(runner, register, "reclaim", "tanks", "--plant", "PL-1", "--on", DAY)
        assert "2 tank(s)" in result.output
        assert "over the limit" in result.output

    def test_only_the_usable(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register, "WW-1", "1.02")
        read_tank(runner, register, "WW-2", "1.08")
        result = run(
            runner,
            register,
            "reclaim",
            "tanks",
            "--plant",
            "PL-1",
            "--on",
            DAY,
            "--usable",
        )
        assert "1 tank(s)" in result.output
        assert "WW-2" not in result.output

    def test_an_empty_day(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "reclaim", "tanks", "--plant", "PL-1", "--on", DAY)
        assert "0 tank(s)" in result.output


class CaseDrawing:
    def test_it_splits_the_draw(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register)
        result = run(
            runner,
            register,
            "reclaim",
            "draw",
            "WW-1",
            "100 gal",
            "--plant",
            "PL-1",
            "--on",
            DAY,
        )
        assert result.exit_code == 0
        assert "water" in result.output
        assert "solids" in result.output

    def test_a_dirty_tank_fails_the_command(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register, sg="1.08")
        result = run(
            runner,
            register,
            "reclaim",
            "draw",
            "WW-1",
            "100 gal",
            "--plant",
            "PL-1",
            "--on",
            DAY,
        )
        assert result.exit_code != 0
        assert "C1602 solids limit" in result.output

    def test_overdrawing(self, runner: CliRunner, register: str) -> None:
        read_tank(runner, register)
        result = run(
            runner,
            register,
            "reclaim",
            "draw",
            "WW-1",
            "5000 gal",
            "--plant",
            "PL-1",
            "--on",
            DAY,
        )
        assert result.exit_code != 0
        assert "WASH_WATER_OVERDRAWN" in result.output

    def test_a_tank_never_read(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "reclaim",
            "draw",
            "WW-9",
            "100 gal",
            "--plant",
            "PL-1",
            "--on",
            DAY,
        )
        assert result.exit_code != 0


class CaseReturned:
    def test_it_records_a_load(self, runner: CliRunner, register: str) -> None:
        result = came_back(runner, register)
        assert result.exit_code == 0
        assert "usable" in result.output

    def test_an_old_load_says_so(self, runner: CliRunner, register: str) -> None:
        result = came_back(runner, register, age="200")
        assert "too old to reuse" in result.output

    def test_the_same_ticket_twice(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register)
        assert came_back(runner, register).exit_code != 0

    def test_the_yard(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register)
        result = run(runner, register, "reclaim", "yard", "--on", DAY)
        assert "1 load(s) on the yard" in result.output
        assert "1.35 yd3" in result.output

    def test_an_old_load_offers_nothing(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register, age="200")
        result = run(runner, register, "reclaim", "yard", "--on", DAY)
        assert "1 too old to use" in result.output
        assert "0.00 yd3" in result.output

    def test_waiting_ages_it_out(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register, age="110")
        fresh = run(runner, register, "reclaim", "yard", "--on", DAY)
        aged = run(runner, register, "reclaim", "yard", "--on", DAY, "--waited", "30")
        assert "0 too old to use" in fresh.output
        assert "1 too old to use" in aged.output

    def test_a_raised_cap_offers_more(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register)
        result = run(runner, register, "reclaim", "yard", "--on", DAY, "--cap", "30")
        assert "2.70 yd3" in result.output

    def test_an_empty_yard(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "reclaim", "yard", "--on", DAY)
        assert "0 load(s) on the yard" in result.output


class CaseFate:
    def test_using_it(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register)
        result = run(runner, register, "reclaim", "use", "881204", "881210")
        assert "went into 881210" in result.output
        assert (
            "0 load(s) on the yard"
            in run(runner, register, "reclaim", "yard", "--on", DAY).output
        )

    def test_dumping_it(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register)
        result = run(runner, register, "reclaim", "dispose", "881204", "--on", DAY)
        assert "disposed of" in result.output

    def test_the_history(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register, "881204")
        came_back(runner, register, "881205")
        run(runner, register, "reclaim", "use", "881204", "881210")
        run(runner, register, "reclaim", "dispose", "881205", "--on", DAY)
        result = run(runner, register, "reclaim", "history", "--from", DAY, "--to", DAY)
        assert "used in 881210" in result.output
        assert "dumped 2024-06-12" in result.output
        assert "2 load(s) came back" in result.output

    def test_a_load_with_no_fate_yet(self, runner: CliRunner, register: str) -> None:
        came_back(runner, register)
        result = run(runner, register, "reclaim", "history", "--from", DAY, "--to", DAY)
        assert "still on the yard" in result.output

    def test_using_a_load_that_is_not_there(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "reclaim", "use", "881204", "881210").exit_code != 0


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "reclaim" in run(runner, register, "--help").output
