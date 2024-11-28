from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.maturity import (
    DEFAULT_ACTIVATION,
    MaturityCurve,
    MaturityPoint,
    TemperatureReading,
    equivalent_age,
    estimate_in_place,
    temperature_time_factor,
)
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature

START = datetime(2024, 6, 12, 8, 0)


def history(*pairs: tuple[int, float]) -> list[TemperatureReading]:
    return [
        TemperatureReading(START + timedelta(hours=hours), Temperature(celsius, "C"))
        for hours, celsius in pairs
    ]


def curve(**overrides: object) -> MaturityCurve:
    fields: dict[str, object] = {
        "mix_code": "4000P-57",
        "points": (
            MaturityPoint(240.0, Quantity(2200, "psi")),
            MaturityPoint(480.0, Quantity(3300, "psi")),
            MaturityPoint(960.0, Quantity(4300, "psi")),
            MaturityPoint(1920.0, Quantity(5100, "psi")),
        ),
    }
    fields.update(overrides)
    return MaturityCurve(**fields)  # type: ignore[arg-type]


class CaseTemperatureTimeFactor:
    def test_a_flat_history(self) -> None:
        assert temperature_time_factor(history((0, 20.0), (24, 20.0))) == pytest.approx(480.0)

    def test_a_warmer_history_matures_faster(self) -> None:
        cool = temperature_time_factor(history((0, 10.0), (24, 10.0)))
        warm = temperature_time_factor(history((0, 30.0), (24, 30.0)))
        assert warm > cool

    def test_readings_are_ordered(self) -> None:
        forwards = temperature_time_factor(history((0, 20.0), (24, 20.0)))
        backwards = temperature_time_factor(list(reversed(history((0, 20.0), (24, 20.0)))))
        assert forwards == pytest.approx(backwards)

    def test_time_below_the_datum_contributes_nothing(self) -> None:
        assert temperature_time_factor(history((0, -5.0), (24, -5.0))) == pytest.approx(0.0)

    def test_a_datum_can_be_moved(self) -> None:
        plain = temperature_time_factor(history((0, 20.0), (24, 20.0)))
        raised = temperature_time_factor(history((0, 20.0), (24, 20.0)), Temperature(10.0, "C"))
        assert raised < plain

    def test_one_reading_is_not_a_history(self) -> None:
        with pytest.raises(ValidationError, match="at least two readings"):
            temperature_time_factor(history((0, 20.0)))

    def test_two_readings_at_the_same_moment(self) -> None:
        readings = history((0, 20.0), (0, 22.0))
        with pytest.raises(ValidationError, match="share the moment"):
            temperature_time_factor(readings)


class CaseEquivalentAge:
    def test_at_the_reference_temperature_it_is_the_real_age(self) -> None:
        assert equivalent_age(history((0, 20.0), (24, 20.0))) == pytest.approx(24.0)

    def test_warmer_curing_ages_it_faster(self) -> None:
        assert equivalent_age(history((0, 35.0), (24, 35.0))) > 24.0

    def test_colder_curing_ages_it_slower(self) -> None:
        assert equivalent_age(history((0, 5.0), (24, 5.0))) < 24.0

    def test_a_higher_activation_energy_widens_the_spread(self) -> None:
        low = equivalent_age(history((0, 35.0), (24, 35.0)), activation=3000.0)
        high = equivalent_age(history((0, 35.0), (24, 35.0)), activation=7000.0)
        assert high > low

    def test_the_default_activation(self) -> None:
        assert pytest.approx(5000.0) == DEFAULT_ACTIVATION

    def test_a_non_positive_activation_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="activation energy"):
            equivalent_age(history((0, 20.0), (24, 20.0)), activation=0.0)

    def test_it_disagrees_with_nurse_saul(self) -> None:
        readings = history((0, 35.0), (24, 35.0))
        assert equivalent_age(readings) != pytest.approx(temperature_time_factor(readings))


class CasePoints:
    def test_a_non_positive_maturity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="maturity has to be positive"):
            MaturityPoint(0.0, Quantity(2200, "psi"))

    def test_a_strength_has_to_be_a_pressure(self) -> None:
        with pytest.raises(ValidationError, match="strength is a pressure"):
            MaturityPoint(240.0, Quantity(2200, "lb"))

    def test_a_non_positive_strength_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            MaturityPoint(240.0, Quantity(0, "psi"))


class CaseCurve:
    def test_it_needs_three_ages(self) -> None:
        with pytest.raises(ValidationError, match="at least three ages"):
            curve(points=(MaturityPoint(240.0, Quantity(2200, "psi")),))

    def test_the_points_are_sorted(self) -> None:
        built = curve(
            points=(
                MaturityPoint(960.0, Quantity(4300, "psi")),
                MaturityPoint(240.0, Quantity(2200, "psi")),
                MaturityPoint(480.0, Quantity(3300, "psi")),
            )
        )
        assert [point.maturity for point in built.points] == [240.0, 480.0, 960.0]

    def test_the_span(self) -> None:
        assert curve().span == (240.0, 1920.0)

    def test_covers(self) -> None:
        assert curve().covers(500.0)
        assert curve().covers(240.0)
        assert not curve().covers(100.0)
        assert not curve().covers(3000.0)

    def test_the_fit_rises_with_maturity(self) -> None:
        _, slope = curve().fit()
        assert slope > 0.0

    def test_a_curve_with_no_spread_cannot_be_fitted(self) -> None:
        flat = curve(
            points=(
                MaturityPoint(240.0, Quantity(2200, "psi")),
                MaturityPoint(240.0, Quantity(2300, "psi")),
                MaturityPoint(240.0, Quantity(2400, "psi")),
            )
        )
        with pytest.raises(ValidationError, match="no curve can be fitted"):
            flat.fit()

    def test_strength_at_a_measured_point_is_close(self) -> None:
        predicted = curve().strength_at(960.0)
        assert predicted.value == pytest.approx(4300.0, abs=250.0)

    def test_strength_rises_with_maturity(self) -> None:
        assert curve().strength_at(1920.0) > curve().strength_at(240.0)

    def test_a_non_positive_maturity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="maturity has to be positive"):
            curve().strength_at(0.0)

    def test_maturity_for_a_strength_inverts_it(self) -> None:
        wanted = Quantity(4000, "psi")
        maturity = curve().maturity_for(wanted)
        assert curve().strength_at(maturity).value == pytest.approx(4000.0, abs=1.0)

    def test_describe(self) -> None:
        text = curve().describe()
        assert "4000P-57" in text
        assert "ln(M)" in text
        assert "measured from 240 to 1920" in text


class CaseEstimate:
    def test_a_history_inside_the_measured_range(self) -> None:
        readings = history((0, 20.0), (24, 20.0), (48, 20.0))
        estimate = estimate_in_place(curve(), readings)
        assert estimate.maturity == pytest.approx(960.0)
        assert not estimate.extrapolated
        assert "gives" in estimate.describe()

    def test_a_history_past_the_measured_range(self) -> None:
        readings = history((0, 30.0), (24, 30.0), (120, 30.0))
        estimate = estimate_in_place(curve(), readings)
        assert estimate.extrapolated
        assert "extrapolated" in estimate.describe()

    def test_a_history_that_never_rose_above_the_datum(self) -> None:
        with pytest.raises(ValidationError, match="never rose above the datum"):
            estimate_in_place(curve(), history((0, -5.0), (24, -5.0)))
