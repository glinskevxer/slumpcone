from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.project.trial import (
    MIN_TRIAL_POINTS,
    TrialBatch,
    TrialSeries,
    series_from_pairs,
)
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity

REQUIRED = Quantity(5200, "psi")


def batch(ratio: float = 0.45, strength: float = 5200.0, **overrides: object) -> TrialBatch:
    fields: dict[str, object] = {
        "water_cementitious": ratio,
        "strengths": (Quantity(strength, "psi"), Quantity(strength, "psi")),
        "slump": Quantity(4.0, "in"),
        "air": Percent(6.0),
    }
    fields.update(overrides)
    return TrialBatch(**fields)  # type: ignore[arg-type]


def series(**overrides: object) -> TrialSeries:
    fields: dict[str, object] = {
        "mix_code": "4000P-57",
        "batches": (
            batch(0.40, 6100.0),
            batch(0.45, 5200.0),
            batch(0.50, 4400.0),
        ),
        "required_average": REQUIRED,
    }
    fields.update(overrides)
    return TrialSeries(**fields)  # type: ignore[arg-type]


class CaseBatch:
    def test_the_average(self) -> None:
        mixed = TrialBatch(
            0.45,
            (Quantity(5100, "psi"), Quantity(5300, "psi")),
            Quantity(4, "in"),
            Percent(6.0),
        )
        assert mixed.average == Quantity(5200, "psi")

    @pytest.mark.parametrize("bad", [0.05, 1.5])
    def test_a_silly_ratio_is_refused(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="not a mixture"):
            batch(ratio=bad)

    def test_one_cylinder_is_not_a_point(self) -> None:
        with pytest.raises(ValidationError, match="at least two cylinders"):
            batch(strengths=(Quantity(5200, "psi"),))

    def test_the_strengths_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="strength is a pressure"):
            batch(strengths=(Quantity(1, "lb"), Quantity(1, "lb")))
        with pytest.raises(ValidationError, match="has to be positive"):
            batch(strengths=(Quantity(0, "psi"), Quantity(0, "psi")))

    def test_the_slump_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="slump is a length"):
            batch(slump=Quantity(4, "lb"))

    def test_the_age_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="test age has to be positive"):
            batch(age_days=0)

    def test_describe(self) -> None:
        assert "w/cm 0.450" in batch().describe()


class CaseSeries:
    def test_the_mix_code_is_normalised(self) -> None:
        assert series(mix_code="4000p 57").mix_code == "4000P-57"

    def test_an_empty_series_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one batch"):
            series(batches=())

    def test_the_required_average_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            series(required_average=Quantity(5200, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            series(required_average=Quantity(0, "psi"))

    def test_the_points_come_back_lowest_ratio_first(self) -> None:
        ratios = [point.water_cementitious for point in series().points]
        assert ratios == sorted(ratios)

    def test_distinct_ratios(self) -> None:
        assert series().distinct_ratios == 3

    def test_two_batches_at_the_same_ratio_count_once(self) -> None:
        doubled = series(
            batches=(batch(0.45, 5200.0), batch(0.45, 5300.0), batch(0.50, 4400.0))
        )
        assert doubled.distinct_ratios == 2

    def test_the_minimum(self) -> None:
        assert MIN_TRIAL_POINTS == 3


class CaseBracketing:
    def test_a_bracketing_series(self) -> None:
        assert series().brackets_the_requirement
        assert series().findings() == ()
        assert series().supports_a_submittal

    def test_a_series_entirely_above_the_requirement(self) -> None:
        high = series(batches=(batch(0.35, 7000.0), batch(0.38, 6600.0), batch(0.41, 6100.0)))
        assert not high.brackets_the_requirement
        assert any("do not bracket" in finding for finding in high.findings())

    def test_a_series_entirely_below(self) -> None:
        low = series(batches=(batch(0.55, 4000.0), batch(0.58, 3700.0), batch(0.61, 3400.0)))
        assert not low.brackets_the_requirement


class CaseRatioFor:
    def test_reading_the_required_ratio_off_a_point(self) -> None:
        assert series().ratio_for() == pytest.approx(0.45)

    def test_interpolating_between_two_points(self) -> None:
        assert series().ratio_for(Quantity(5650, "psi")) == pytest.approx(0.425, abs=1e-3)

    def test_a_target_outside_the_range_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="outside the trial range"):
            series().ratio_for(Quantity(7000, "psi"))

    def test_one_point_cannot_be_read(self) -> None:
        with pytest.raises(ValidationError, match="two trial points"):
            series(batches=(batch(),)).ratio_for()

    def test_a_flat_segment_returns_the_lower_ratio(self) -> None:
        flat = series(batches=(batch(0.40, 5200.0), batch(0.45, 5200.0)))
        assert flat.ratio_for() == pytest.approx(0.40)


class CaseFindings:
    def test_too_few_ratios(self) -> None:
        thin = series(batches=(batch(0.42, 5600.0), batch(0.48, 4800.0)))
        assert any("distinct ratios" in finding for finding in thin.findings())

    def test_mixed_ages(self) -> None:
        mixed = series(
            batches=(
                batch(0.40, 6100.0),
                batch(0.45, 5200.0),
                batch(0.50, 4400.0, age_days=56),
            )
        )
        assert any("different ages" in finding for finding in mixed.findings())

    def test_a_batch_outside_the_slump_band(self) -> None:
        checked = series(slump_band=Band.between(5.0, 7.0))
        assert len(checked.findings()) == 3

    def test_a_batch_outside_the_air_band(self) -> None:
        checked = series(air_band=Band.between(2.0, 4.0))
        assert any("air, outside" in finding for finding in checked.findings())
        assert not checked.supports_a_submittal

    def test_describe(self) -> None:
        text = series().describe()
        assert "4000P-57 trial against 5200 psi: 3 batches" in text
        assert "w/cm 0.400" in text


class CaseFromPairs:
    def test_it_builds_a_usable_series(self) -> None:
        built = series_from_pairs(
            "4000P-57", [(0.40, 6100.0), (0.45, 5200.0), (0.50, 4400.0)], REQUIRED
        )
        assert built.supports_a_submittal
        assert built.ratio_for() == pytest.approx(0.45)

    def test_the_slump_and_air_can_be_set(self) -> None:
        built = series_from_pairs(
            "4000P-57",
            [(0.40, 6100.0), (0.45, 5200.0)],
            REQUIRED,
            slump=Quantity(6.0, "in"),
            air=Percent(4.5),
        )
        assert built.points[0].slump == Quantity(6.0, "in")
        assert built.points[0].air == Percent(4.5)
