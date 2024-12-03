from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.blending import BlendComponent, combine
from slumpcone.materials.gradation import Gradation
from slumpcone.materials.workability import (
    REFERENCE_CEMENTITIOUS,
    ChartPoint,
    WorkabilityZone,
    chart_point,
    coarseness_factor,
    is_sand_heavy,
    largest_departure,
    power_deviations,
    power_line,
    workability_factor,
    zone_of,
)
from slumpcone.units.quantity import Quantity
from tests.materials.test_blending import SAND, STONE


def blended(stone_weight: float = 1780.0, sand_weight: float = 1255.0) -> Gradation:
    return combine(
        [
            BlendComponent("CA-57", Gradation.of(STONE), Quantity(stone_weight, "lb"), 2.68),
            BlendComponent("FA-1", Gradation.of(SAND), Quantity(sand_weight, "lb"), 2.63),
        ]
    )


class CaseCoarsenessFactor:
    def test_a_typical_blend(self) -> None:
        assert coarseness_factor(blended()) == pytest.approx(71.2, abs=1.0)

    def test_more_stone_raises_it(self) -> None:
        assert coarseness_factor(blended(2200.0, 900.0)) > coarseness_factor(blended())

    def test_a_stack_missing_a_sieve(self) -> None:
        short = Gradation.of({"1 in": 100.0, "3/4 in": 70.0})
        with pytest.raises(ValidationError, match="needs the 3/8 in and No. 8"):
            coarseness_factor(short)

    def test_a_grading_that_all_passes_the_number_eight(self) -> None:
        fine = Gradation.of({"3/8 in": 100.0, "No. 8": 100.0, "No. 100": 20.0})
        with pytest.raises(ValidationError, match="no coarseness factor"):
            coarseness_factor(fine)


class CaseWorkabilityFactor:
    def test_it_is_the_percent_passing_the_number_eight(self) -> None:
        passing = blended().passing_on("No. 8")
        assert passing is not None
        assert workability_factor(blended()) == pytest.approx(passing.value)

    def test_more_paste_raises_it(self) -> None:
        plain = workability_factor(blended())
        rich = workability_factor(blended(), Quantity(752, "lb"))
        assert rich == pytest.approx(plain + 5.0, abs=0.1)

    def test_less_paste_lowers_it(self) -> None:
        plain = workability_factor(blended())
        lean = workability_factor(blended(), Quantity(470, "lb"))
        assert lean < plain

    def test_the_reference_content_changes_nothing(self) -> None:
        assert workability_factor(blended(), REFERENCE_CEMENTITIOUS) == pytest.approx(
            workability_factor(blended())
        )

    def test_a_non_mass_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a mass"):
            workability_factor(blended(), Quantity(564, "yd3"))

    def test_a_stack_missing_the_number_eight(self) -> None:
        with pytest.raises(ValidationError, match="needs the No. 8"):
            workability_factor(Gradation.of({"1 in": 100.0, "3/4 in": 70.0}))


class CaseZones:
    def test_a_well_graded_point(self) -> None:
        assert zone_of(60.0, 36.0) is WorkabilityZone.WELL_GRADED

    def test_a_rocky_point(self) -> None:
        assert zone_of(80.0, 36.0) is WorkabilityZone.ROCKY

    def test_a_fine_point(self) -> None:
        assert zone_of(40.0, 36.0) is WorkabilityZone.FINE

    def test_a_sandy_point(self) -> None:
        assert zone_of(60.0, 45.0) is WorkabilityZone.SANDY

    def test_a_gap_graded_point(self) -> None:
        assert zone_of(60.0, 28.0) is WorkabilityZone.GAP_GRADED

    def test_only_one_zone_places_well(self) -> None:
        assert WorkabilityZone.WELL_GRADED.places_well
        for other in WorkabilityZone:
            if other is not WorkabilityZone.WELL_GRADED:
                assert not other.places_well

    def test_it_prints_its_own_value(self) -> None:
        assert str(WorkabilityZone.GAP_GRADED) == "gap graded"


class CaseChartPoint:
    def test_a_blend_lands_somewhere(self) -> None:
        point = chart_point(blended(), Quantity(564, "lb"))
        assert isinstance(point.zone, WorkabilityZone)

    def test_the_distance_from_the_trend(self) -> None:
        point = ChartPoint(60.0, 35.83)
        assert point.distance_from_trend == pytest.approx(0.0, abs=0.01)

    def test_a_sandy_point_sits_above_the_trend(self) -> None:
        assert ChartPoint(60.0, 45.0).distance_from_trend > 0.0

    def test_describe(self) -> None:
        text = ChartPoint(60.0, 36.0).describe()
        assert "CF 60.0" in text
        assert "WF 36.0" in text
        assert "well graded" in text


class CasePowerLine:
    def test_at_the_nominal_size_it_is_all_passing(self) -> None:
        assert power_line(Quantity(25, "mm"), 25.0) == pytest.approx(100.0)
        assert power_line(Quantity(25, "mm"), 37.5) == pytest.approx(100.0)

    def test_halfway_down_in_size(self) -> None:
        assert power_line(Quantity(25, "mm"), 12.5) == pytest.approx(73.2, abs=0.2)

    def test_a_different_exponent_moves_it(self) -> None:
        assert power_line(Quantity(25, "mm"), 12.5, 0.5) < power_line(
            Quantity(25, "mm"), 12.5, 0.45
        )

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a length"):
            power_line(Quantity(25, "lb"), 12.5)
        with pytest.raises(ValidationError, match="has to be positive"):
            power_line(Quantity(0, "mm"), 12.5)


class CaseDeviations:
    def test_one_per_sieve(self) -> None:
        deviations = power_deviations(blended(), Quantity(1.0, "in"))
        assert len(deviations) == len(blended().passing)

    def test_the_top_sieve_is_on_the_line(self) -> None:
        deviations = power_deviations(blended(), Quantity(1.0, "in"))
        assert deviations[0].deviation == pytest.approx(0.0, abs=0.01)

    def test_the_largest_departure(self) -> None:
        worst = largest_departure(blended(), Quantity(1.0, "in"))
        assert abs(worst.deviation) >= abs(
            power_deviations(blended(), Quantity(1.0, "in"))[0].deviation
        )

    def test_describe(self) -> None:
        text = power_deviations(blended(), Quantity(1.0, "in"))[1].describe()
        assert "on the line" in text

    def test_sand_heavy(self) -> None:
        assert not is_sand_heavy(blended(2200.0, 900.0), Quantity(1.0, "in"))
        assert is_sand_heavy(blended(900.0, 2200.0), Quantity(1.0, "in"))

    def test_sand_heavy_needs_the_number_eight(self) -> None:
        with pytest.raises(ValidationError, match="needs the No. 8"):
            is_sand_heavy(Gradation.of({"1 in": 100.0, "3/4 in": 70.0}), Quantity(1, "in"))
