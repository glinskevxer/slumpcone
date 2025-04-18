from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.fresh.bleeding import (
    BleedReading,
    BleedTest,
    ColumnSegregation,
    VisualStability,
)
from slumpcone.register import Register
from slumpcone.units.quantity import Quantity

DAY = date(2024, 6, 12)
LATER = date(2024, 6, 13)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


def a_test(number: str = "881204", *draws: tuple[float, float]) -> BleedTest:
    readings = draws or ((10.0, 0.05), (30.0, 0.04), (60.0, 0.02))
    return BleedTest(
        number,
        Quantity(60.0, "lb"),
        Quantity(4000.0, "lb"),
        Quantity(260.0, "lb"),
        Quantity(100.0, "in2"),
        tuple(BleedReading(minutes, Quantity(water, "lb")) for minutes, water in readings),
    )


class CaseRoundTrip:
    def test_a_test_comes_back_whole(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY, technician="R. Okafor")
        back = register.bleeding.get("881204", DAY)
        assert back == a_test()

    def test_draws_out_of_order_never_reach_the_store(self) -> None:
        from slumpcone.fresh.bleeding import BleedingError

        with pytest.raises(BleedingError):
            a_test("881204", (60.0, 0.02), (10.0, 0.05))

    def test_the_figures_survive(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        back = register.bleeding.get("881204", DAY)
        assert back.total_water.value == pytest.approx(0.11)
        assert back.sample_water.value == pytest.approx(3.9)

    def test_a_test_with_no_draws(self, register: Register) -> None:
        empty = BleedTest(
            "881204",
            Quantity(60.0, "lb"),
            Quantity(4000.0, "lb"),
            Quantity(260.0, "lb"),
            Quantity(100.0, "in2"),
        )
        register.bleeding.save(empty, DAY)
        assert register.bleeding.get("881204", DAY).readings == ()

    def test_an_unknown_test(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.bleeding.get("881204", DAY)

    def test_the_ticket_number_is_normalised(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        assert register.bleeding.get("  881204 ", DAY).ticket_number == "881204"


class CaseSameLoadTwice:
    def test_two_days_sit_side_by_side(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        register.bleeding.save(a_test("881204", (60.0, 0.30)), LATER)
        assert len(register.bleeding.for_ticket("881204")) == 2

    def test_the_same_day_twice_collides(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        with pytest.raises(ConflictError):
            register.bleeding.save(a_test(), DAY)

    def test_replace_takes_the_new_draws(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        register.bleeding.save(a_test("881204", (60.0, 0.30)), DAY, replace=True)
        back = register.bleeding.get("881204", DAY)
        assert len(back.readings) == 1
        assert back.total_water.value == pytest.approx(0.30)

    def test_replace_leaves_no_orphan_draws(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        register.bleeding.save(a_test("881204", (60.0, 0.30)), DAY, replace=True)
        rows = register.database.query("SELECT * FROM bleed_reading")
        assert len(rows) == 1


class CaseWindows:
    def test_for_ticket_is_oldest_first(self, register: Register) -> None:
        register.bleeding.save(a_test(), LATER)
        register.bleeding.save(a_test(), DAY)
        tests = register.bleeding.for_ticket("881204")
        assert len(tests) == 2

    def test_for_a_ticket_with_nothing_on_file(self, register: Register) -> None:
        assert register.bleeding.for_ticket("881204") == ()

    def test_between(self, register: Register) -> None:
        register.bleeding.save(a_test("881204"), DAY)
        register.bleeding.save(a_test("881205"), DAY)
        register.bleeding.save(a_test("881206"), LATER)
        assert len(register.bleeding.between(DAY, DAY)) == 2
        assert len(register.bleeding.between(DAY, LATER)) == 3

    def test_an_empty_window(self, register: Register) -> None:
        register.bleeding.save(a_test(), DAY)
        assert register.bleeding.between(date(2024, 1, 1), date(2024, 1, 31)) == ()


class CaseSegregation:
    def test_it_round_trips(self, register: Register) -> None:
        column = ColumnSegregation("881204", Quantity(2.9, "lb"), Quantity(3.1, "lb"))
        register.bleeding.save_segregation(column, DAY)
        assert register.bleeding.segregation("881204", DAY) == column

    def test_the_visual_index_is_optional(self, register: Register) -> None:
        column = ColumnSegregation("881204", Quantity(2.9, "lb"), Quantity(3.1, "lb"))
        register.bleeding.save_segregation(column, DAY)
        assert register.bleeding.visual_index("881204", DAY) is None

    def test_the_visual_index_comes_back(self, register: Register) -> None:
        column = ColumnSegregation("881204", Quantity(2.9, "lb"), Quantity(3.1, "lb"))
        register.bleeding.save_segregation(column, DAY, visual=VisualStability.SLIGHT_HALO)
        assert register.bleeding.visual_index("881204", DAY) is VisualStability.SLIGHT_HALO

    def test_an_index_of_zero_is_not_missing(self, register: Register) -> None:
        column = ColumnSegregation("881204", Quantity(3.0, "lb"), Quantity(3.0, "lb"))
        register.bleeding.save_segregation(column, DAY, visual=VisualStability.STABLE)
        assert register.bleeding.visual_index("881204", DAY) is VisualStability.STABLE

    def test_the_same_day_twice_collides(self, register: Register) -> None:
        column = ColumnSegregation("881204", Quantity(2.9, "lb"), Quantity(3.1, "lb"))
        register.bleeding.save_segregation(column, DAY)
        with pytest.raises(ConflictError):
            register.bleeding.save_segregation(column, DAY)

    def test_an_unknown_result(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.bleeding.segregation("881204", DAY)

    def test_an_unknown_index(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.bleeding.visual_index("881204", DAY)

    def test_between(self, register: Register) -> None:
        register.bleeding.save_segregation(
            ColumnSegregation("881204", Quantity(2.9, "lb"), Quantity(3.1, "lb")), DAY
        )
        register.bleeding.save_segregation(
            ColumnSegregation("881205", Quantity(2.0, "lb"), Quantity(4.0, "lb")), LATER
        )
        assert len(register.bleeding.segregations_between(DAY, LATER)) == 2

    def test_failing_reads_everything_when_given_nothing(self, register: Register) -> None:
        register.bleeding.save_segregation(
            ColumnSegregation("881204", Quantity(2.9, "lb"), Quantity(3.1, "lb")), DAY
        )
        register.bleeding.save_segregation(
            ColumnSegregation("881205", Quantity(2.0, "lb"), Quantity(4.0, "lb")), LATER
        )
        failing = register.bleeding.failing_segregations()
        assert [result.ticket_number for result in failing] == ["881205"]

    def test_failing_takes_a_handed_in_pool(self, register: Register) -> None:
        good = ColumnSegregation("881204", Quantity(3.0, "lb"), Quantity(3.0, "lb"))
        assert register.bleeding.failing_segregations([good]) == ()


def test_the_health_check_counts_bleeding(register: Register) -> None:
    register.bleeding.save(a_test(), DAY)
    assert register.health().counts["bleed_test"] == 1
