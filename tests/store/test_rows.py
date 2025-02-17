from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.percent import Percent
from slumpcone.store.rows import (
    band_columns,
    band_from,
    day,
    day_range,
    moment,
    number,
    percent,
    quantity,
    text,
    whole,
)
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity


class CaseDayRange:
    def test_it_is_half_open_to_the_next_day(self) -> None:
        assert day_range(date(2024, 6, 12), date(2024, 6, 12)) == ("2024-06-12", "2024-06-13")

    def test_a_wider_window(self) -> None:
        assert day_range(date(2024, 6, 1), date(2024, 6, 30)) == ("2024-06-01", "2024-07-01")

    def test_the_last_microsecond_of_the_closing_day_is_inside(self) -> None:
        _, upper = day_range(date(2024, 6, 12), date(2024, 6, 12))
        assert datetime(2024, 6, 12, 23, 59, 59, 999999).isoformat() < upper

    def test_it_crosses_a_month_end(self) -> None:
        assert day_range(date(2024, 2, 28), date(2024, 2, 29))[1] == "2024-03-01"


class CaseBands:
    def test_a_symmetric_band_round_trips(self) -> None:
        band = Band.symmetric(4.0, 1.0)
        assert band_from(*band_columns(band)) == band

    def test_a_one_sided_band_round_trips(self) -> None:
        band = Band.at_most(5.0)
        rebuilt = band_from(*band_columns(band))
        assert rebuilt is not None
        assert rebuilt.low is None
        assert rebuilt.high == pytest.approx(5.0)

    def test_no_band_packs_to_nulls(self) -> None:
        assert band_columns(None) == (None, None, None)

    def test_no_band_unpacks_to_none(self) -> None:
        assert band_from(None, None, None) is None
        assert band_from(4.0, None, None) is None


class CaseNullables:
    def test_moment(self) -> None:
        assert moment(None) is None
        assert moment("2024-06-12T07:42:00") == datetime(2024, 6, 12, 7, 42)

    def test_day(self) -> None:
        assert day(None) is None
        assert day("2024-06-12") == date(2024, 6, 12)

    def test_text_does_not_stringify_none(self) -> None:
        assert text(None) is None
        assert text(7) == "7"

    def test_number(self) -> None:
        assert number(None) is None
        assert number("4.5") == pytest.approx(4.5)


class CaseTypedNullables:
    def test_whole(self) -> None:
        assert whole(None) is None
        assert whole("7") == 7

    def test_percent(self) -> None:
        assert percent(None) is None
        assert percent("6.0") == Percent(6.0)

    def test_quantity_takes_its_unit_from_the_column(self) -> None:
        assert quantity(None, "lb") is None
        assert quantity("4230", "lb") == Quantity(4230, "lb")

    def test_a_quantity_column_in_another_unit(self) -> None:
        assert quantity("9", "yd3") == Quantity(9, "yd3")

    def test_none_never_becomes_the_string_none(self) -> None:
        for reader in (text, number, whole, day, moment, percent):
            assert reader(None) is None
