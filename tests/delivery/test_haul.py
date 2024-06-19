from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.delivery.haul import (
    BASE_TIME_LIMIT,
    REVOLUTION_LIMIT,
    haul_limits,
    judge_haul,
)
from slumpcone.errors import ValidationError
from slumpcone.units.temperature import Temperature

BATCHED = datetime(2024, 6, 12, 7, 42)


class CaseLimits:
    def test_the_standard_limits(self) -> None:
        limits = haul_limits()
        assert limits.time_limit == BASE_TIME_LIMIT
        assert limits.revolution_limit == REVOLUTION_LIMIT
        assert limits.basis == "standard"
        assert not limits.time_is_waived

    def test_a_retarder_extends_the_clock(self) -> None:
        limits = haul_limits(has_retarder=True)
        assert limits.time_limit == timedelta(minutes=180)
        assert limits.basis == "retarded mixture"

    def test_hot_concrete_shortens_it(self) -> None:
        limits = haul_limits(concrete_temperature=Temperature(95, "F"))
        assert limits.time_limit == timedelta(minutes=60)
        assert limits.basis == "hot weather"

    def test_hot_weather_beats_a_retarder(self) -> None:
        limits = haul_limits(has_retarder=True, concrete_temperature=Temperature(95, "F"))
        assert limits.time_limit == timedelta(minutes=60)

    def test_exactly_ninety_degrees_is_not_hot_weather(self) -> None:
        limits = haul_limits(concrete_temperature=Temperature(90, "F"))
        assert limits.time_limit == BASE_TIME_LIMIT

    def test_a_waiver_lifts_the_clock_only(self) -> None:
        limits = haul_limits(time_waived=True)
        assert limits.time_is_waived
        assert limits.revolution_limit == REVOLUTION_LIMIT
        assert "waived" in limits.describe()

    def test_a_waiver_beats_everything_else(self) -> None:
        limits = haul_limits(
            has_retarder=True, concrete_temperature=Temperature(95, "F"), time_waived=True
        )
        assert limits.time_is_waived

    def test_describe(self) -> None:
        assert haul_limits().describe() == "90 min, 300 revolutions (standard)"


class CaseJudge:
    def test_a_good_haul(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=52), 180)
        assert verdict.conforms
        assert verdict.reasons == ()
        assert "inside" in verdict.describe()
        assert verdict.elapsed_minutes == pytest.approx(52.0)

    def test_over_the_clock(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=97), 180)
        assert verdict.over_time
        assert not verdict.conforms
        assert "97 minutes after batching" in verdict.describe()

    def test_exactly_at_the_clock_is_inside(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=90), 180)
        assert verdict.conforms

    def test_over_the_revolutions(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=52), 340)
        assert verdict.over_revolutions
        assert "drum turned 340 times" in verdict.describe()

    def test_both_at_once(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=120), 340)
        assert len(verdict.reasons) == 2

    def test_a_waiver_forgives_the_clock_but_not_the_drum(self) -> None:
        limits = haul_limits(time_waived=True)
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=200), 340, limits)
        assert not verdict.over_time
        assert verdict.over_revolutions

    def test_a_retarded_load_gets_the_longer_clock(self) -> None:
        limits = haul_limits(has_retarder=True)
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=150), 180, limits)
        assert verdict.conforms

    def test_discharge_before_batching_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="before it was batched"):
            judge_haul(BATCHED, BATCHED - timedelta(minutes=1), 100)

    def test_a_negative_revolution_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            judge_haul(BATCHED, BATCHED + timedelta(minutes=10), -1)

    def test_the_revolution_limit_can_bind_first(self) -> None:
        verdict = judge_haul(BATCHED, BATCHED + timedelta(minutes=40), 420)
        assert not verdict.over_time
        assert not verdict.conforms
