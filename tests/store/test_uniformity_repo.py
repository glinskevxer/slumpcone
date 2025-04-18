from __future__ import annotations

from datetime import date

import pytest

from slumpcone.batching.uniformity import UniformityError, UniformitySample
from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.percent import Percent
from slumpcone.register import Register
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

DAY = date(2024, 6, 12)
LATER = date(2025, 6, 12)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


def sample(
    label: str,
    *,
    unit_weight: float = 145.0,
    air: float = 5.0,
    strength: float | None = None,
) -> UniformitySample:
    return UniformitySample(
        label,
        MassPerVolume(unit_weight, "lb", "ft3"),
        Percent(air),
        Quantity(4.0, "in"),
        Percent(42.0),
        2.68,
        Quantity(0.25, "ft3"),
        Quantity(15.225, "lb"),
        None if strength is None else Quantity(strength, "psi"),
    )


def file_one(register: Register, mixer: str = "MX-1", on: date = DAY) -> None:
    register.uniformity.save(
        mixer,
        on,
        sample("first draw"),
        sample("second draw", unit_weight=144.6, air=5.4),
        plant_code="PL-1",
        technician="R. Okafor",
        notes="annual",
    )


class CaseRoundTrip:
    def test_both_samples_come_back(self, register: Register) -> None:
        file_one(register)
        record = register.uniformity.get("MX-1", DAY)
        assert {record.first.label, record.second.label} == {"first draw", "second draw"}

    def test_the_header_survives(self, register: Register) -> None:
        file_one(register)
        record = register.uniformity.get("MX-1", DAY)
        assert record.plant_code == "PL-1"
        assert record.technician == "R. Okafor"
        assert record.notes == "annual"

    def test_the_readings_survive(self, register: Register) -> None:
        file_one(register)
        record = register.uniformity.get("MX-1", DAY)
        weights = sorted(
            sample.unit_weight.to("lb", "ft3").value for sample in (record.first, record.second)
        )
        assert weights == pytest.approx([144.6, 145.0])

    def test_a_missing_strength_stays_missing(self, register: Register) -> None:
        file_one(register)
        record = register.uniformity.get("MX-1", DAY)
        assert record.first.strength_7day is None

    def test_a_strength_that_was_taken_comes_back(self, register: Register) -> None:
        register.uniformity.save(
            "MX-1", DAY, sample("a", strength=3200.0), sample("b", strength=3300.0)
        )
        record = register.uniformity.get("MX-1", DAY)
        assert record.first.strength_7day == Quantity(3200.0, "psi")

    def test_the_verdict_runs_off_the_filed_pair(self, register: Register) -> None:
        file_one(register)
        verdict = register.uniformity.get("MX-1", DAY).judge()
        assert verdict.mixer == "MX-1"
        assert verdict.is_uniform

    def test_an_unknown_test(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.uniformity.get("MX-1", DAY)

    def test_the_mixer_is_normalised(self, register: Register) -> None:
        file_one(register)
        assert register.uniformity.get(" mx-1 ", DAY).mixer == "MX-1"


class CaseGuards:
    def test_two_samples_with_one_label(self, register: Register) -> None:
        with pytest.raises(UniformityError) as caught:
            register.uniformity.save("MX-1", DAY, sample("same"), sample("same"))
        assert caught.value.code == "UNIFORMITY_SAME_SAMPLE"

    def test_the_same_mixer_on_the_same_day_twice(self, register: Register) -> None:
        file_one(register)
        with pytest.raises(ConflictError):
            file_one(register)

    def test_half_a_test_is_refused_on_the_way_out(self, register: Register) -> None:
        file_one(register)
        register.database.execute(
            "DELETE FROM uniformity_sample WHERE label = ?", ("second draw",)
        )
        with pytest.raises(UniformityError) as caught:
            register.uniformity.get("MX-1", DAY)
        assert caught.value.code == "UNIFORMITY_HALF_A_TEST"

    def test_a_second_test_on_a_later_day_is_fine(self, register: Register) -> None:
        file_one(register)
        file_one(register, on=LATER)
        assert len(register.uniformity.for_mixer("MX-1")) == 2


class CaseWindows:
    def test_for_a_mixer_never_tested(self, register: Register) -> None:
        assert register.uniformity.for_mixer("MX-9") == ()

    def test_between(self, register: Register) -> None:
        file_one(register, "MX-1")
        file_one(register, "MX-2")
        file_one(register, "MX-3", on=LATER)
        assert len(register.uniformity.between(DAY, DAY)) == 2
        assert len(register.uniformity.between(DAY, LATER)) == 3

    def test_between_at_one_plant(self, register: Register) -> None:
        file_one(register, "MX-1")
        register.uniformity.save("MX-2", DAY, sample("a"), sample("b"), plant_code="PL-2")
        assert len(register.uniformity.between(DAY, DAY, plant_code="PL-1")) == 1
        assert len(register.uniformity.between(DAY, DAY, plant_code="PL-9")) == 0

    def test_an_empty_window(self, register: Register) -> None:
        file_one(register)
        assert register.uniformity.between(date(2020, 1, 1), date(2020, 12, 31)) == ()


class CaseLatestAndDue:
    def test_a_mixer_never_tested_has_no_latest(self, register: Register) -> None:
        assert register.uniformity.latest("MX-1") is None

    def test_the_latest_is_the_newest(self, register: Register) -> None:
        file_one(register, on=DAY)
        file_one(register, on=LATER)
        latest = register.uniformity.latest("MX-1")
        assert latest is not None
        assert latest.tested_on == LATER

    def test_a_mixer_never_tested_is_due(self, register: Register) -> None:
        assert register.uniformity.due(("MX-1",), DAY) == ("MX-1",)

    def test_a_mixer_tested_this_year_is_not_due(self, register: Register) -> None:
        file_one(register)
        assert register.uniformity.due(("MX-1",), DAY) == ()

    def test_a_year_and_a_day_is_due(self, register: Register) -> None:
        file_one(register)
        assert register.uniformity.due(("MX-1",), date(2025, 6, 13)) == ("MX-1",)

    def test_exactly_a_year_is_not_due(self, register: Register) -> None:
        file_one(register)
        assert register.uniformity.due(("MX-1",), LATER) == ()

    def test_a_shorter_interval(self, register: Register) -> None:
        file_one(register)
        assert register.uniformity.due(("MX-1",), date(2024, 9, 12), every_days=30) == ("MX-1",)

    def test_nothing_asked_about(self, register: Register) -> None:
        assert register.uniformity.due((), DAY) == ()


def test_the_health_check_counts_uniformity(register: Register) -> None:
    file_one(register)
    assert register.health().counts["uniformity_test"] == 1
