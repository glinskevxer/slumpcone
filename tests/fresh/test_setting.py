from __future__ import annotations

from datetime import timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.setting import (
    FINAL_SET,
    INITIAL_SET,
    PenetrationReading,
    curve_from,
    retardation,
)
from slumpcone.units.quantity import Quantity

# A plain mixture: resistance roughly doubling every hour after the third.
PLAIN = [
    (3.0, 120.0),
    (3.5, 260.0),
    (4.0, 520.0),
    (4.5, 1100.0),
    (5.0, 2300.0),
    (5.5, 4600.0),
]

RETARDED = [(hours + 2.0, psi) for hours, psi in PLAIN]


class CaseReading:
    def test_a_non_positive_time_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="elapsed time"):
            PenetrationReading(0.0, Quantity(500, "psi"))

    def test_a_resistance_has_to_be_a_pressure(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            PenetrationReading(3.0, Quantity(500, "lb"))

    def test_a_non_positive_resistance_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            PenetrationReading(3.0, Quantity(0, "psi"))

    def test_the_useful_band(self) -> None:
        assert PenetrationReading(3.0, Quantity(500, "psi")).is_useful
        assert not PenetrationReading(3.0, Quantity(10, "psi")).is_useful
        assert not PenetrationReading(3.0, Quantity(9000, "psi")).is_useful


class CaseCurve:
    def test_it_needs_three_useful_readings(self) -> None:
        with pytest.raises(ValidationError, match="at least three readings"):
            curve_from("S-1", [(3.0, 120.0), (3.5, 260.0)])

    def test_readings_outside_the_band_do_not_count_toward_the_three(self) -> None:
        with pytest.raises(ValidationError, match="at least three readings"):
            curve_from("S-1", [(3.0, 10.0), (3.5, 20.0), (4.0, 520.0), (4.5, 1100.0)])

    def test_the_readings_are_sorted(self) -> None:
        built = curve_from("S-1", list(reversed(PLAIN)))
        times = [reading.elapsed_hours for reading in built.readings]
        assert times == sorted(times)

    def test_the_useful_readings_are_a_subset(self) -> None:
        built = curve_from("S-1", [*PLAIN, (6.0, 9000.0)])
        assert len(built.useful) == len(PLAIN)

    def test_the_fit_slopes_upward(self) -> None:
        _, slope = curve_from("S-1", PLAIN).fit()
        assert slope > 0.0

    def test_a_falling_series_is_not_a_set(self) -> None:
        falling = [(3.0, 4000.0), (4.0, 1000.0), (5.0, 300.0)]
        with pytest.raises(ValidationError, match="not a set"):
            curve_from("S-1", falling).fit()

    def test_readings_all_at_one_time(self) -> None:
        same = [(3.0, 400.0), (3.0, 800.0), (3.0, 1600.0)]
        with pytest.raises(ValidationError, match="same time"):
            curve_from("S-1", same).fit()


class CaseSetTimes:
    curve = curve_from("S-1", PLAIN)

    def test_initial_set_falls_where_the_readings_cross_five_hundred(self) -> None:
        assert self.curve.initial_set.total_seconds() / 3600.0 == pytest.approx(3.9, abs=0.15)

    def test_final_set_is_later(self) -> None:
        assert self.curve.final_set > self.curve.initial_set

    def test_final_set_falls_where_the_readings_cross_four_thousand(self) -> None:
        assert self.curve.final_set.total_seconds() / 3600.0 == pytest.approx(5.5, abs=0.2)

    def test_the_span(self) -> None:
        assert self.curve.span == self.curve.final_set - self.curve.initial_set

    def test_time_at_an_arbitrary_resistance(self) -> None:
        middle = self.curve.time_at(Quantity(1000, "psi"))
        assert self.curve.initial_set < middle < self.curve.final_set

    def test_time_at_needs_a_pressure(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            self.curve.time_at(Quantity(1000, "lb"))

    def test_the_thresholds(self) -> None:
        assert INITIAL_SET.value == pytest.approx(500.0)
        assert FINAL_SET.value == pytest.approx(4000.0)


class CaseExtrapolation:
    def test_a_complete_series_is_not_extrapolated(self) -> None:
        assert not curve_from("S-1", PLAIN).is_extrapolated

    def test_a_series_that_stopped_early(self) -> None:
        short = curve_from("S-1", PLAIN[:4])
        assert short.is_extrapolated
        assert "extrapolated" in short.describe()

    def test_a_series_that_started_late(self) -> None:
        late = curve_from("S-1", [(4.5, 1100.0), (5.0, 2300.0), (5.5, 4600.0)])
        assert late.is_extrapolated

    def test_describe(self) -> None:
        text = curve_from("S-1", PLAIN).describe()
        assert "S-1" in text
        assert "initial 3h" in text


class CaseRetardation:
    def test_a_retarded_mixture_sets_later(self) -> None:
        delay = retardation(curve_from("S-1", PLAIN), curve_from("S-2", RETARDED))
        assert delay > timedelta(0)
        assert delay.total_seconds() / 3600.0 == pytest.approx(2.0, abs=0.2)

    def test_an_accelerated_mixture_reads_negative(self) -> None:
        early = [(hours - 1.0, psi) for hours, psi in PLAIN]
        delay = retardation(curve_from("S-1", PLAIN), curve_from("S-2", early))
        assert delay < timedelta(0)

    def test_the_same_mixture_twice_reads_nothing(self) -> None:
        delay = retardation(curve_from("S-1", PLAIN), curve_from("S-2", PLAIN))
        assert abs(delay.total_seconds()) < 1.0
