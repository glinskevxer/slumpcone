from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.units.checks import (
    require_area,
    require_dimension,
    require_force,
    require_length,
    require_mass,
    require_not_negative,
    require_positive,
    require_pressure,
    require_volume,
)
from slumpcone.units.dimension import Dimension
from slumpcone.units.quantity import Quantity


class CaseDimension:
    def test_it_returns_the_quantity_so_it_can_be_assigned(self) -> None:
        weight = Quantity(564, "lb")
        assert require_mass(weight, "a charge", field="charge") is weight

    def test_the_noun_is_the_plant_s_own_wording(self) -> None:
        with pytest.raises(ValidationError, match="a scale capacity is a mass"):
            require_mass(Quantity(1, "yd3"), "a scale capacity", field="capacity")

    def test_the_field_travels_with_the_error(self) -> None:
        with pytest.raises(ValidationError) as caught:
            require_mass(Quantity(1, "yd3"), "a charge", field="charge")
        assert caught.value.field == "charge"

    @pytest.mark.parametrize(
        ("check", "good", "bad"),
        [
            (require_mass, "lb", "yd3"),
            (require_volume, "yd3", "lb"),
            (require_length, "in", "lb"),
            (require_pressure, "psi", "lb"),
            (require_force, "lbf", "lb"),
            (require_area, "ft2", "lb"),
        ],
    )
    def test_each_helper(self, check: object, good: str, bad: str) -> None:
        assert check(Quantity(1, good), "a value", field="value")  # type: ignore[operator]
        with pytest.raises(ValidationError):
            check(Quantity(1, bad), "a value", field="value")  # type: ignore[operator]

    def test_the_generic_helper(self) -> None:
        require_dimension(Quantity(1, "min"), Dimension.TIME, "a span", field="span")
        with pytest.raises(ValidationError, match="a span is a time"):
            require_dimension(Quantity(1, "lb"), Dimension.TIME, "a span", field="span")


class CaseRange:
    def test_positive_passes_a_positive(self) -> None:
        assert require_positive(Quantity(1, "lb"), "a charge", field="charge")

    def test_positive_refuses_zero(self) -> None:
        with pytest.raises(ValidationError, match="a charge has to be positive"):
            require_positive(Quantity(0, "lb"), "a charge", field="charge")

    def test_not_negative_allows_zero(self) -> None:
        zero = Quantity(0, "lb")
        assert require_not_negative(zero, "a charge", field="charge") is zero

    def test_not_negative_refuses_below_zero(self) -> None:
        with pytest.raises(ValidationError, match="a charge cannot be negative"):
            require_not_negative(Quantity(-1, "lb"), "a charge", field="charge")


class CaseCallers:
    def test_a_silo_still_refuses_a_volume_capacity(self) -> None:
        from slumpcone.plant.silo import Silo

        with pytest.raises(ValidationError, match="a silo capacity is a mass"):
            Silo("SI-1", "One", "CEM-I", Quantity(1, "yd3"), Quantity(0, "lb"))

    def test_a_drawdown_still_refuses_a_volume(self) -> None:
        from slumpcone.plant.silo import Silo

        silo = Silo("SI-1", "One", "CEM-I", Quantity(100, "lb"), Quantity(50, "lb"))
        with pytest.raises(ValidationError, match="a drawdown is a mass"):
            silo.draw(Quantity(1, "yd3"))

    def test_a_weighing_tolerance_still_refuses_a_volume(self) -> None:
        from slumpcone.batching.weighing import weighing_allowance
        from slumpcone.materials.kinds import MaterialClass

        with pytest.raises(ValidationError, match="a required weight is a mass"):
            weighing_allowance(MaterialClass.CEMENT, Quantity(1, "yd3"))
