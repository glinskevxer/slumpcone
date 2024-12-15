from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.flexural import (
    DEFAULT_RUPTURE_FACTOR,
    FlexuralBreak,
    FractureLocation,
    average_rupture,
    equivalent_compressive,
    estimated_rupture,
    locate_fracture,
)
from slumpcone.units.quantity import Quantity

SPAN = Quantity(18.0, "in")


def beam(distance: float = 7.0, load: float = 6200.0, **overrides: object) -> FlexuralBreak:
    fields: dict[str, object] = {
        "specimen_code": "B-4471-A",
        "span": SPAN,
        "width": Quantity(6.0, "in"),
        "depth": Quantity(6.0, "in"),
        "max_load": Quantity(load, "lbf"),
        "fracture_from_support": Quantity(distance, "in"),
    }
    fields.update(overrides)
    return FlexuralBreak(**fields)  # type: ignore[arg-type]


class CaseLocate:
    def test_dead_centre(self) -> None:
        assert locate_fracture(SPAN, Quantity(9.0, "in")) is FractureLocation.MIDDLE_THIRD

    def test_on_the_middle_third_boundary(self) -> None:
        assert locate_fracture(SPAN, Quantity(6.0, "in")) is FractureLocation.MIDDLE_THIRD

    def test_just_outside(self) -> None:
        assert locate_fracture(SPAN, Quantity(5.5, "in")) is FractureLocation.JUST_OUTSIDE

    def test_well_outside(self) -> None:
        assert locate_fracture(SPAN, Quantity(4.0, "in")) is FractureLocation.WELL_OUTSIDE

    def test_it_is_symmetric_about_the_middle(self) -> None:
        assert locate_fracture(SPAN, Quantity(12.5, "in")) is FractureLocation.JUST_OUTSIDE

    def test_which_locations_are_usable(self) -> None:
        assert FractureLocation.MIDDLE_THIRD.is_usable
        assert FractureLocation.JUST_OUTSIDE.is_usable
        assert not FractureLocation.WELL_OUTSIDE.is_usable

    def test_which_need_correcting(self) -> None:
        assert FractureLocation.JUST_OUTSIDE.needs_correction
        assert not FractureLocation.MIDDLE_THIRD.needs_correction

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="span is a length"):
            locate_fracture(Quantity(18, "lb"), Quantity(9, "in"))
        with pytest.raises(ValidationError, match="has to be positive"):
            locate_fracture(Quantity(0, "in"), Quantity(9, "in"))
        with pytest.raises(ValidationError, match="cannot be negative"):
            locate_fracture(SPAN, Quantity(-1, "in"))

    def test_it_prints_its_own_value(self) -> None:
        assert str(FractureLocation.JUST_OUTSIDE) == "just outside"


class CaseBreak:
    def test_the_dimensions_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="beam span is a length"):
            beam(span=Quantity(18, "lb"))
        with pytest.raises(ValidationError, match="beam depth has to be positive"):
            beam(depth=Quantity(0, "in"))

    def test_the_load_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="load is a force"):
            beam(max_load=Quantity(6200, "lb"))
        with pytest.raises(ValidationError, match="load has to be positive"):
            beam(load=0.0)

    def test_the_age_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="age at test"):
            beam(age_days=0.0)

    def test_a_middle_third_break(self) -> None:
        result = beam(distance=9.0)
        assert result.location is FractureLocation.MIDDLE_THIRD
        assert result.modulus_of_rupture.value == pytest.approx(516.7, abs=1.0)

    def test_a_corrected_break_reads_lower(self) -> None:
        centre = beam(distance=9.0).modulus_of_rupture
        outside = beam(distance=5.5).modulus_of_rupture
        assert outside < centre

    def test_a_correction_from_the_far_side(self) -> None:
        near = beam(distance=5.5).modulus_of_rupture
        far = beam(distance=12.5).modulus_of_rupture
        assert near == far

    def test_a_discarded_break_has_no_result(self) -> None:
        broken = beam(distance=4.0)
        assert not broken.is_usable
        with pytest.raises(ValidationError, match="well outside the middle third"):
            _ = broken.modulus_of_rupture

    def test_describe(self) -> None:
        assert "middle third" in beam(distance=9.0).describe()
        assert "discarded" in beam(distance=4.0).describe()


class CaseEstimates:
    def test_the_default_factor(self) -> None:
        assert pytest.approx(7.5) == DEFAULT_RUPTURE_FACTOR

    def test_rupture_from_compressive(self) -> None:
        assert estimated_rupture(Quantity(4000, "psi")).value == pytest.approx(474.3, abs=0.5)

    def test_a_bigger_factor_gives_more(self) -> None:
        assert estimated_rupture(Quantity(4000, "psi"), 9.0) > estimated_rupture(
            Quantity(4000, "psi")
        )

    def test_the_two_estimates_invert_each_other(self) -> None:
        rupture = estimated_rupture(Quantity(4000, "psi"))
        assert equivalent_compressive(rupture).value == pytest.approx(4000.0, abs=1.0)

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="compressive strength is a pressure"):
            estimated_rupture(Quantity(4000, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            estimated_rupture(Quantity(0, "psi"))
        with pytest.raises(ValidationError, match="rupture factor"):
            estimated_rupture(Quantity(4000, "psi"), 0.0)
        with pytest.raises(ValidationError, match="modulus of rupture is a pressure"):
            equivalent_compressive(Quantity(500, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            equivalent_compressive(Quantity(0, "psi"))
        with pytest.raises(ValidationError, match="rupture factor"):
            equivalent_compressive(Quantity(500, "psi"), 0.0)


class CaseAverage:
    def test_over_two_good_beams(self) -> None:
        result = average_rupture([beam(distance=9.0), beam(distance=8.0, load=6400.0)])
        assert result.value > 500.0

    def test_a_discarded_beam_is_left_out(self) -> None:
        with_bad = average_rupture([beam(distance=9.0), beam(distance=4.0, load=3000.0)])
        alone = average_rupture([beam(distance=9.0)])
        assert with_bad == alone

    def test_every_beam_discarded(self) -> None:
        with pytest.raises(ValidationError, match="every beam broke"):
            average_rupture([beam(distance=4.0)])
