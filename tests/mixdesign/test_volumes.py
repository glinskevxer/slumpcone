from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.proportions import Charge, Proportions
from slumpcone.mixdesign.volumes import (
    WATER_DENSITY,
    absolute_volume,
    check_yield,
    compute_volumes,
    gravimetric_air,
    relative_yield,
)
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from tests.factories import gravities, proportions, rate

GRAVITIES = gravities()


def closing_mix() -> Proportions:
    """The shared paving mix with no admixtures on it."""
    return proportions(admixtures=())


class CaseAbsoluteVolume:
    def test_water_occupies_its_own_weight(self) -> None:
        volume = absolute_volume(Quantity(62.42796, "lb"), 1.0)
        assert volume.value == pytest.approx(1.0)

    def test_cement_is_denser(self) -> None:
        volume = absolute_volume(Quantity(564, "lb"), 3.15)
        assert volume.value == pytest.approx(2.868, abs=1e-3)

    def test_a_non_mass_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="taken of a mass"):
            absolute_volume(Quantity(1, "yd3"), 2.65)

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_a_non_positive_gravity_is_refused(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="positive"):
            absolute_volume(Quantity(1, "lb"), bad)

    def test_the_water_density_reference(self) -> None:
        assert WATER_DENSITY.to("lb", "ft3").value == pytest.approx(62.42796)


class CaseComputeVolumes:
    def test_every_charge_gets_a_volume(self) -> None:
        breakdown = compute_volumes(closing_mix(), GRAVITIES)
        assert len(breakdown.per_material) == 5

    def test_water_defaults_to_a_gravity_of_one(self) -> None:
        without_water = {k: v for k, v in GRAVITIES.items() if k != "W-1"}
        breakdown = compute_volumes(closing_mix(), without_water)
        assert breakdown.volume_of("W-1").value == pytest.approx(250 / 62.42796, abs=1e-6)

    def test_a_missing_gravity_on_a_solid_is_refused(self) -> None:
        without_stone = {k: v for k, v in GRAVITIES.items() if k != "CA-57"}
        with pytest.raises(ValidationError, match="no specific gravity for CA-57"):
            compute_volumes(closing_mix(), without_stone)

    def test_air_is_the_design_share_of_the_unit_volume(self) -> None:
        breakdown = compute_volumes(closing_mix(), GRAVITIES)
        assert breakdown.air.value == pytest.approx(27.0 * 0.06, abs=1e-6)

    def test_totals(self) -> None:
        breakdown = compute_volumes(closing_mix(), GRAVITIES)
        assert breakdown.total_mass.value == pytest.approx(3849.0)
        assert breakdown.total_volume.value == pytest.approx(26.94, abs=0.02)

    def test_scaling_to_a_load(self) -> None:
        breakdown = compute_volumes(closing_mix(), GRAVITIES, Quantity(9, "yd3"))
        assert breakdown.total_mass.value == pytest.approx(3849.0 * 9)
        assert breakdown.total_volume.value == pytest.approx(242.4, abs=0.5)

    def test_volume_of_and_share_of(self) -> None:
        breakdown = compute_volumes(closing_mix(), GRAVITIES)
        assert breakdown.volume_of("CEM-I").value == pytest.approx(2.390, abs=1e-3)
        assert breakdown.share_of("CEM-I").value == pytest.approx(8.85, abs=0.1)

    def test_a_material_that_is_not_in_the_batch(self) -> None:
        breakdown = compute_volumes(closing_mix(), GRAVITIES)
        with pytest.raises(ValidationError, match="not in this batch"):
            breakdown.volume_of("CEM-III")


class CaseDensities:
    breakdown = compute_volumes(closing_mix(), GRAVITIES)

    def test_theoretical_density_has_no_air_in_it(self) -> None:
        assert self.breakdown.theoretical_density.to("lb", "ft3").value == pytest.approx(
            152.0, abs=0.5
        )

    def test_design_density_is_lower(self) -> None:
        assert self.breakdown.design_density < self.breakdown.theoretical_density


class CaseYieldCheck:
    def test_a_closing_mix(self) -> None:
        check = check_yield(closing_mix(), GRAVITIES)
        assert check.conforms
        assert abs(check.error.value) < 0.01

    def test_a_short_mix_does_not_close(self) -> None:
        short = Proportions(
            (
                Charge("CEM-I", MaterialClass.CEMENT, rate(470)),
                Charge("SCM-F", MaterialClass.SCM, rate(94)),
                Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1600)),
                Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1000)),
                Charge("W-1", MaterialClass.WATER, rate(254)),
            ),
            design_air=Percent(6.0),
        )
        check = check_yield(short, GRAVITIES)
        assert not check.conforms
        assert check.error.value < 0.0
        assert "does not close" in check.describe()

    def test_the_tolerance_is_adjustable(self) -> None:
        check = check_yield(closing_mix(), GRAVITIES, tolerance=0.0)
        assert isinstance(check.conforms, bool)

    def test_describe_reads_as_a_percentage(self) -> None:
        assert "%" in check_yield(closing_mix(), GRAVITIES).describe()

    def test_relative_is_about_one(self) -> None:
        assert check_yield(closing_mix(), GRAVITIES).relative == pytest.approx(1.0, abs=0.005)


class CaseMeasured:
    breakdown = compute_volumes(closing_mix(), GRAVITIES)

    def test_relative_yield_of_exactly_one(self) -> None:
        density = self.breakdown.design_density
        assert relative_yield(density, self.breakdown) == pytest.approx(1.0)

    def test_a_heavy_load_yields_short(self) -> None:
        density = self.breakdown.design_density * 1.02
        assert relative_yield(density, self.breakdown) < 1.0

    def test_a_zero_density_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no yield"):
            relative_yield(MassPerVolume(0, "lb", "ft3"), self.breakdown)

    def test_gravimetric_air_recovers_the_design_air(self) -> None:
        air = gravimetric_air(self.breakdown.design_density, self.breakdown)
        assert air.value == pytest.approx(6.0, abs=0.05)

    def test_a_heavier_load_reads_less_air(self) -> None:
        air = gravimetric_air(self.breakdown.design_density * 1.01, self.breakdown)
        assert air.value < 6.0
