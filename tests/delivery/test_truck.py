from __future__ import annotations

from datetime import date

import pytest

from slumpcone.delivery.truck import AGITATING_CAPACITY, MIXING_CAPACITY, Truck
from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.plant.plant import MixingMethod
from slumpcone.units.quantity import Quantity

DAY = date(2024, 6, 12)


def truck(**overrides: object) -> Truck:
    fields: dict[str, object] = {
        "code": "TR-114",
        "drum_volume": Quantity(11.0, "yd3"),
        "fleet": "Northmoor",
        "last_uniformity_test": date(2024, 2, 1),
    }
    fields.update(overrides)
    return Truck(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_the_code_and_fleet_are_normalised(self) -> None:
        built = truck(code=" tr 114 ", fleet="  Northmoor   south ")
        assert built.code == "TR-114"
        assert built.fleet == "Northmoor south"

    def test_the_drum_volume_has_to_be_a_volume(self) -> None:
        with pytest.raises(ValidationError, match="drum volume is a volume"):
            truck(drum_volume=Quantity(11, "lb"))

    def test_the_drum_volume_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            truck(drum_volume=Quantity(0, "yd3"))

    def test_the_interval_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="interval has to be positive"):
            truck(uniformity_test_days=0)


class CaseCapacity:
    def test_the_two_ratings(self) -> None:
        assert truck().mixing_capacity.value == pytest.approx(6.93)
        assert truck().agitating_capacity.value == pytest.approx(8.8)

    def test_the_percentages(self) -> None:
        assert MIXING_CAPACITY.value == pytest.approx(63.0)
        assert AGITATING_CAPACITY.value == pytest.approx(80.0)

    def test_truck_mixing_uses_the_lower_rating(self) -> None:
        assert truck().capacity_for(MixingMethod.TRUCK_MIXED).value == pytest.approx(6.93)

    def test_shrink_mixing_still_mixes_in_the_drum(self) -> None:
        assert truck().capacity_for(MixingMethod.SHRINK_MIXED).value == pytest.approx(6.93)

    def test_central_mixing_uses_the_higher_rating(self) -> None:
        assert truck().capacity_for(MixingMethod.CENTRAL_MIXED).value == pytest.approx(8.8)

    def test_can_carry(self) -> None:
        assert truck().can_carry(Quantity(6.5, "yd3"), MixingMethod.TRUCK_MIXED)
        assert not truck().can_carry(Quantity(8.0, "yd3"), MixingMethod.TRUCK_MIXED)
        assert truck().can_carry(Quantity(8.0, "yd3"), MixingMethod.CENTRAL_MIXED)

    def test_can_carry_refuses_a_non_volume(self) -> None:
        with pytest.raises(ValidationError, match="load size is a volume"):
            truck().can_carry(Quantity(8, "lb"), MixingMethod.TRUCK_MIXED)

    def test_require_capacity_refuses_an_overload(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            truck().require_capacity(Quantity(9, "yd3"), MixingMethod.TRUCK_MIXED)
        assert caught.value.code == "TRUCK_OVERLOADED"
        assert "TR-114" in caught.value.detail

    def test_require_capacity_passes_a_legal_load(self) -> None:
        truck().require_capacity(Quantity(6.5, "yd3"), MixingMethod.TRUCK_MIXED)

    def test_the_same_load_can_be_legal_one_way_and_not_the_other(self) -> None:
        load = Quantity(8.0, "yd3")
        truck().require_capacity(load, MixingMethod.CENTRAL_MIXED)
        with pytest.raises(RuleViolationError):
            truck().require_capacity(load, MixingMethod.TRUCK_MIXED)


class CaseUniformity:
    def test_the_due_date(self) -> None:
        assert truck().uniformity_due == date(2025, 1, 31)

    def test_a_current_truck(self) -> None:
        assert truck().uniformity_is_current(DAY)
        assert truck().blocking_reasons(DAY) == ()

    def test_a_lapsed_truck(self) -> None:
        assert not truck().uniformity_is_current(date(2025, 3, 1))
        reasons = truck().blocking_reasons(date(2025, 3, 1))
        assert "lapsed 2025-01-31" in reasons[0]

    def test_a_truck_that_has_never_been_tested(self) -> None:
        never = truck(last_uniformity_test=None)
        assert never.uniformity_due is None
        assert not never.uniformity_is_current(DAY)
        assert never.blocking_reasons(DAY) == ("no mixer uniformity test on file",)

    def test_a_shorter_interval(self) -> None:
        assert truck(uniformity_test_days=90).uniformity_due == date(2024, 5, 1)

    def test_describe(self) -> None:
        line = truck().describe()
        assert "TR-114" in line
        assert "Northmoor" in line
        assert "drum 11.0 yd3" in line
        assert "mixing 6.93 yd3" in line
