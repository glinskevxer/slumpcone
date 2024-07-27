from __future__ import annotations

from datetime import date, time

import pytest

from slumpcone.errors import ValidationError
from slumpcone.project.order import Order, OrderStatus, progress_of
from slumpcone.units.quantity import Quantity


def order(**overrides: object) -> Order:
    fields: dict[str, object] = {
        "number": "ORD-9912",
        "project_code": "P-2024-118",
        "class_code": "SLAB",
        "volume": Quantity(60, "yd3"),
        "placement_date": date(2024, 6, 12),
        "mix_code": "4000P-57",
        "start_time": time(6, 30),
        "rate": Quantity(24, "yd3"),
        "placement": "Station 12 to 18 shoulder",
    }
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


class CaseStatus:
    def test_which_states_accept_loads(self) -> None:
        assert OrderStatus.BOOKED.accepts_loads
        assert OrderStatus.IN_PROGRESS.accepts_loads
        assert not OrderStatus.COMPLETE.accepts_loads
        assert not OrderStatus.CANCELLED.accepts_loads

    def test_prints_its_own_value(self) -> None:
        assert str(OrderStatus.IN_PROGRESS) == "in_progress"


class CaseOrder:
    def test_codes_are_normalised(self) -> None:
        built = order(number=" ord 9912 ", project_code="p 2024 118", mix_code="4000p 57")
        assert built.number == "ORD-9912"
        assert built.project_code == "P-2024-118"
        assert built.mix_code == "4000P-57"

    def test_the_placement_whitespace_collapses(self) -> None:
        assert order(placement="  Station 12   to 18 ").placement == "Station 12 to 18"

    def test_the_volume_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="ordered quantity is a volume"):
            order(volume=Quantity(60, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            order(volume=Quantity(0, "yd3"))

    def test_the_rate_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="delivery rate is a volume"):
            order(rate=Quantity(24, "lb"))
        with pytest.raises(ValidationError, match="rate has to be positive"):
            order(rate=Quantity(0, "yd3"))

    def test_loads_at(self) -> None:
        assert order().loads_at == "60.0 yd3 at 24.0 yd3/h"

    def test_loads_at_without_a_rate(self) -> None:
        assert order(rate=None).loads_at == "60.0 yd3"

    def test_expected_loads_divides_evenly(self) -> None:
        assert order().expected_loads(Quantity(10, "yd3")) == 6

    def test_expected_loads_rounds_up(self) -> None:
        assert order().expected_loads(Quantity(9, "yd3")) == 7

    def test_expected_loads_checks_its_input(self) -> None:
        with pytest.raises(ValidationError, match="load size is a volume"):
            order().expected_loads(Quantity(9, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            order().expected_loads(Quantity(0, "yd3"))

    def test_describe(self) -> None:
        line = order().describe()
        assert "ORD-9912" in line
        assert "P-2024-118/SLAB" in line
        assert "4000P-57" in line
        assert "2024-06-12" in line
        assert "booked" in line


class CaseProgress:
    def test_nothing_delivered(self) -> None:
        progress = progress_of(order(), [])
        assert progress.delivered.is_zero()
        assert progress.remaining == Quantity(60, "yd3")
        assert progress.is_short
        assert not progress.is_over

    def test_part_way_through(self) -> None:
        progress = progress_of(order(), [Quantity(9, "yd3")] * 4)
        assert progress.delivered == Quantity(36, "yd3")
        assert progress.load_count == 4
        assert progress.completion.value == pytest.approx(60.0)
        assert progress.remaining == Quantity(24, "yd3")

    def test_exactly_filled(self) -> None:
        progress = progress_of(order(), [Quantity(10, "yd3")] * 6)
        assert progress.remaining.is_zero()
        assert not progress.is_short
        assert not progress.is_over
        assert progress.overrun.is_zero()

    def test_a_small_overrun_is_inside_the_tolerance(self) -> None:
        progress = progress_of(order(), [Quantity(10, "yd3")] * 6 + [Quantity(2, "yd3")])
        assert progress.overrun == Quantity(2, "yd3")
        assert not progress.is_over

    def test_a_real_overrun(self) -> None:
        progress = progress_of(order(), [Quantity(10, "yd3")] * 7)
        assert progress.is_over
        assert progress.overrun == Quantity(10, "yd3")

    def test_returned_concrete_comes_off_what_was_placed(self) -> None:
        progress = progress_of(
            order(), [Quantity(10, "yd3")] * 6, [Quantity(0.5, "yd3"), Quantity(1.5, "yd3")]
        )
        assert progress.placed == Quantity(58, "yd3")
        assert progress.delivered == Quantity(60, "yd3")

    def test_loads_in_other_units_convert(self) -> None:
        progress = progress_of(order(), [Quantity(7.6455, "m3")])
        assert progress.delivered.value == pytest.approx(10.0, abs=0.01)

    def test_a_non_volume_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="delivered quantity is a volume"):
            progress_of(order(), [Quantity(10, "lb")])

    def test_describe(self) -> None:
        progress = progress_of(order(), [Quantity(9, "yd3")] * 4)
        assert progress.describe() == "ORD-9912  36.0 yd3 of 60.0 yd3 in 4 loads  60%"
