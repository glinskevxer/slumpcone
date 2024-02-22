from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.plant.scale import Scale, ScaleState
from slumpcone.units.quantity import Quantity

CALIBRATED = date(2024, 3, 1)


def scale(**overrides: object) -> Scale:
    fields: dict[str, object] = {
        "code": "SC-AGG",
        "name": "Aggregate hopper scale",
        "capacity": Quantity(12000, "lb"),
        "graduation": Quantity(2, "lb"),
        "weighs": (MaterialClass.COARSE_AGGREGATE, MaterialClass.FINE_AGGREGATE),
        "last_calibrated": CALIBRATED,
    }
    fields.update(overrides)
    return Scale(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_code_and_name_are_normalised(self) -> None:
        built = scale(code=" sc agg ", name="  Aggregate   hopper ")
        assert built.code == "SC-AGG"
        assert built.name == "Aggregate hopper"

    def test_capacity_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="capacity is a mass"):
            scale(capacity=Quantity(12000, "gal"))

    def test_graduation_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="graduation is a mass"):
            scale(graduation=Quantity(2, "in"))

    @pytest.mark.parametrize("bad", [0, -1])
    def test_capacity_has_to_be_positive(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="capacity has to be positive"):
            scale(capacity=Quantity(bad, "lb"))

    def test_graduation_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="graduation has to be positive"):
            scale(graduation=Quantity(0, "lb"))

    def test_graduation_smaller_than_capacity(self) -> None:
        with pytest.raises(ValidationError, match="smaller than its capacity"):
            scale(graduation=Quantity(12000, "lb"))

    def test_a_scale_has_to_weigh_something(self) -> None:
        with pytest.raises(ValidationError, match="weigh something"):
            scale(weighs=())

    def test_the_calibration_interval_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="interval has to be positive"):
            scale(calibration_days=0)


class CaseCalibration:
    def test_due_date_follows_the_interval(self) -> None:
        assert scale().calibration_due == date(2024, 8, 30)

    def test_current_well_inside(self) -> None:
        assert scale().state(date(2024, 5, 1)) is ScaleState.CURRENT
        assert scale().is_current(date(2024, 5, 1))

    def test_due_soon_inside_the_warning_window(self) -> None:
        assert scale().state(date(2024, 8, 15)) is ScaleState.DUE_SOON
        assert scale().is_current(date(2024, 8, 15))

    def test_current_on_the_due_date_itself(self) -> None:
        assert scale().is_current(date(2024, 8, 30))

    def test_overdue_the_day_after(self) -> None:
        assert scale().state(date(2024, 8, 31)) is ScaleState.OVERDUE
        assert not scale().is_current(date(2024, 8, 31))

    def test_the_warning_window_is_adjustable(self) -> None:
        assert scale().state(date(2024, 8, 15), warning_days=0) is ScaleState.CURRENT

    def test_days_until_due(self) -> None:
        assert scale().days_until_due(date(2024, 8, 20)) == 10
        assert scale().days_until_due(date(2024, 9, 9)) == -10

    def test_only_overdue_blocks_a_batch(self) -> None:
        assert ScaleState.OVERDUE.blocks_batching
        assert not ScaleState.DUE_SOON.blocks_batching
        assert not ScaleState.CURRENT.blocks_batching

    def test_state_prints_its_own_value(self) -> None:
        assert str(ScaleState.DUE_SOON) == "due_soon"


class CaseAssignment:
    def test_can_weigh(self) -> None:
        assert scale().can_weigh(MaterialClass.COARSE_AGGREGATE)
        assert not scale().can_weigh(MaterialClass.CEMENT)

    def test_smallest_defensible_charge(self) -> None:
        assert scale().smallest_defensible_charge() == Quantity(40, "lb")

    def test_the_graduation_count_is_adjustable(self) -> None:
        assert scale().smallest_defensible_charge(graduations=50) == Quantity(100, "lb")

    def test_a_non_positive_graduation_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="graduations"):
            scale().smallest_defensible_charge(graduations=0)

    def test_describe(self) -> None:
        line = scale().describe(date(2024, 5, 1))
        assert "SC-AGG" in line
        assert "12000 lb capacity" in line
        assert "coarse_aggregate" in line
        assert "current until 2024-08-30" in line
