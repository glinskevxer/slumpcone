from __future__ import annotations

from datetime import timedelta

import pytest

from slumpcone.delivery.slumploss import (
    REFERENCE_TEMPERATURE,
    SlumpLossModel,
    forecast,
)
from slumpcone.errors import ValidationError
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature

FOUR = Quantity(4.0, "in")
MILD = Temperature(70.0, "F")
HOT = Temperature(90.0, "F")


class CaseModel:
    def test_the_rate_has_to_be_a_length(self) -> None:
        with pytest.raises(ValidationError, match="rate is a length"):
            SlumpLossModel(Quantity(1, "lb"))

    def test_a_negative_rate_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            SlumpLossModel(Quantity(-1, "in"))

    def test_a_non_positive_doubling_interval(self) -> None:
        with pytest.raises(ValidationError, match="doubling interval"):
            SlumpLossModel(doubling_interval=0.0)

    def test_at_the_reference_the_rate_is_the_rate(self) -> None:
        assert SlumpLossModel().rate_at(REFERENCE_TEMPERATURE).value == pytest.approx(1.0)

    def test_twenty_degrees_hotter_doubles_it(self) -> None:
        assert SlumpLossModel().rate_at(HOT).value == pytest.approx(2.0)

    def test_twenty_degrees_colder_halves_it(self) -> None:
        assert SlumpLossModel().rate_at(Temperature(50, "F")).value == pytest.approx(0.5)

    def test_a_retarder_halves_it(self) -> None:
        plain = SlumpLossModel().rate_at(HOT)
        retarded = SlumpLossModel().rate_at(HOT, has_retarder=True)
        assert retarded.value == pytest.approx(plain.value / 2.0)

    def test_a_plant_can_set_its_own_rate(self) -> None:
        model = SlumpLossModel(Quantity(0.5, "in"))
        assert model.rate_at(MILD).value == pytest.approx(0.5)


class CaseSlumpAfter:
    def test_no_time_no_loss(self) -> None:
        assert SlumpLossModel().slump_after(FOUR, timedelta(0), MILD) == FOUR

    def test_an_hour_at_the_reference(self) -> None:
        after = SlumpLossModel().slump_after(FOUR, timedelta(hours=1), MILD)
        assert after.value == pytest.approx(3.0)

    def test_the_same_hour_when_it_is_hot(self) -> None:
        after = SlumpLossModel().slump_after(FOUR, timedelta(hours=1), HOT)
        assert after.value == pytest.approx(2.0)

    def test_it_floors_at_nothing(self) -> None:
        after = SlumpLossModel().slump_after(FOUR, timedelta(hours=8), HOT)
        assert after.value == pytest.approx(0.0)

    def test_a_retarder_keeps_it_wetter(self) -> None:
        plain = SlumpLossModel().slump_after(FOUR, timedelta(hours=1), HOT)
        retarded = SlumpLossModel().slump_after(
            FOUR, timedelta(hours=1), HOT, has_retarder=True
        )
        assert retarded > plain

    def test_a_non_length_slump_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="slump is a length"):
            SlumpLossModel().slump_after(Quantity(4, "lb"), timedelta(hours=1), MILD)

    def test_negative_time_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            SlumpLossModel().slump_after(FOUR, timedelta(hours=-1), MILD)


class CaseTimeTo:
    def test_it_inverts_the_loss(self) -> None:
        span = SlumpLossModel().time_to(FOUR, Quantity(2.0, "in"), MILD)
        assert span.total_seconds() / 3600.0 == pytest.approx(2.0)

    def test_heat_shortens_it(self) -> None:
        mild = SlumpLossModel().time_to(FOUR, Quantity(2.0, "in"), MILD)
        hot = SlumpLossModel().time_to(FOUR, Quantity(2.0, "in"), HOT)
        assert hot < mild

    def test_a_target_above_the_initial_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="does not gain slump"):
            SlumpLossModel().time_to(FOUR, Quantity(5.0, "in"), MILD)

    def test_a_zero_rate_never_gets_there(self) -> None:
        model = SlumpLossModel(Quantity(0.0, "in"))
        with pytest.raises(ValidationError, match="never reaches the target"):
            model.time_to(FOUR, Quantity(2.0, "in"), MILD)

    def test_the_workable_window(self) -> None:
        window = SlumpLossModel().workable_window(FOUR, MILD)
        assert window.total_seconds() / 3600.0 == pytest.approx(3.0)


class CaseForecast:
    def test_a_short_haul_arrives_placeable(self) -> None:
        result = forecast(FOUR, timedelta(minutes=30), MILD)
        assert result.is_placeable
        assert "placeable" in result.describe()

    def test_a_long_hot_haul_does_not(self) -> None:
        result = forecast(FOUR, timedelta(hours=2), HOT)
        assert not result.is_placeable
        assert "too stiff" in result.describe()

    def test_the_margin_runs_out(self) -> None:
        result = forecast(FOUR, timedelta(hours=2), HOT)
        assert result.margin.total_seconds() < 0.0

    def test_a_retarder_saves_the_same_haul(self) -> None:
        plain = forecast(FOUR, timedelta(hours=2), HOT)
        retarded = forecast(FOUR, timedelta(hours=2), HOT, has_retarder=True)
        assert not plain.is_placeable
        assert retarded.is_placeable

    def test_a_plant_model_is_used_when_given(self) -> None:
        gentle = forecast(
            FOUR, timedelta(hours=2), HOT, model=SlumpLossModel(Quantity(0.25, "in"))
        )
        assert gentle.is_placeable

    def test_describe_names_the_numbers(self) -> None:
        text = forecast(FOUR, timedelta(minutes=30), MILD).describe()
        assert "4.0 in at 70 degF" in text
        assert "30 minutes" in text
