from __future__ import annotations

import pytest

from slumpcone.carbon.factors import CarbonError, EmissionFactor, FactorBook, Stage
from slumpcone.carbon.footprint import (
    Contribution,
    Footprint,
    compare,
    footprint_of,
    reduction,
)
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from tests import factories

# Densities close to what a real air entrainer and water reducer weigh.
ADMIXTURE_DENSITY = {
    "AD-AE": MassPerVolume(8.4, "lb", "gal"),
    "AD-WR": MassPerVolume(9.9, "lb", "gal"),
}


def book(*, with_admixtures: bool = False) -> FactorBook:
    factors = [
        EmissionFactor("CEM-I", MaterialClass.CEMENT, 0.922),
        EmissionFactor("SCM-F", MaterialClass.SCM, 0.027),
        EmissionFactor("CA-57", MaterialClass.COARSE_AGGREGATE, 0.0075),
        EmissionFactor("FA-1", MaterialClass.FINE_AGGREGATE, 0.0048),
        EmissionFactor("W-1", MaterialClass.WATER, 0.0003),
    ]
    if with_admixtures:
        factors.extend(
            [
                EmissionFactor("AD-AE", MaterialClass.ADMIXTURE, 1.88),
                EmissionFactor("AD-WR", MaterialClass.ADMIXTURE, 1.88),
            ]
        )
    return FactorBook(factors)


class CaseFootprint:
    def test_the_total_over_a_cubic_yard(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.total_kg == pytest.approx(206.5328, rel=1e-4)

    def test_per_cubic_yard_is_the_total_when_the_volume_is_one(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.per_cubic_yard == pytest.approx(found.total_kg)

    def test_per_cubic_metre_is_the_bigger_number(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.per_cubic_metre == pytest.approx(270.1348, rel=1e-4)
        assert found.per_cubic_metre > found.per_cubic_yard

    def test_ten_yards_carries_ten_times_as_much(self) -> None:
        one = footprint_of(factories.design(), book())
        ten = footprint_of(factories.design(), book(), volume=Quantity(10.0, "yd3"))
        assert ten.total_kg == pytest.approx(10.0 * one.total_kg)

    def test_the_rate_does_not_move_with_the_volume(self) -> None:
        one = footprint_of(factories.design(), book())
        ten = footprint_of(factories.design(), book(), volume=Quantity(10.0, "yd3"))
        assert ten.per_cubic_metre == pytest.approx(one.per_cubic_metre)

    def test_the_stage_comes_off_the_book(self) -> None:
        assert footprint_of(factories.design(), book()).stage is Stage.A1_A3

    def test_a_zero_volume(self) -> None:
        with pytest.raises(CarbonError) as caught:
            footprint_of(factories.design(), book(), volume=Quantity(0.0, "yd3"))
        assert caught.value.code == "CARBON_NO_VOLUME"

    def test_a_book_mixing_stages_is_refused_before_anything_is_added(self) -> None:
        mixed = book()
        mixed.add(EmissionFactor("W-1", MaterialClass.WATER, 0.0003, Stage.A4))
        with pytest.raises(CarbonError) as caught:
            footprint_of(factories.design(), mixed)
        assert caught.value.code == "CARBON_MIXED_STAGES"


class CaseWhatGotCounted:
    def test_the_admixtures_are_not_counted_without_a_density(self) -> None:
        found = footprint_of(factories.design(), book(with_admixtures=True))
        assert not found.is_complete
        assert set(found.uncounted) == {"AD-AE", "AD-WR"}

    def test_a_density_brings_them_in(self) -> None:
        found = footprint_of(
            factories.design(),
            book(with_admixtures=True),
            admixture_density=ADMIXTURE_DENSITY,
        )
        assert found.is_complete
        assert found.of_class(MaterialClass.ADMIXTURE) > 0.0

    def test_counting_them_makes_the_total_larger(self) -> None:
        without = footprint_of(factories.design(), book(with_admixtures=True))
        with_them = footprint_of(
            factories.design(),
            book(with_admixtures=True),
            admixture_density=ADMIXTURE_DENSITY,
        )
        assert with_them.total_kg > without.total_kg

    def test_a_material_with_no_factor_is_named(self) -> None:
        thin = FactorBook([EmissionFactor("CEM-I", MaterialClass.CEMENT, 0.922)])
        found = footprint_of(factories.design(), thin)
        assert "CA-57" in found.uncounted
        assert not found.is_complete

    def test_a_density_without_a_factor_is_still_uncounted(self) -> None:
        found = footprint_of(factories.design(), book(), admixture_density=ADMIXTURE_DENSITY)
        assert set(found.uncounted) == {"AD-AE", "AD-WR"}

    def test_describe_says_what_was_missed(self) -> None:
        found = footprint_of(factories.design(), book(with_admixtures=True))
        assert "not counted" in found.describe()

    def test_describe_of_a_complete_footprint_says_nothing_extra(self) -> None:
        found = footprint_of(
            factories.design(),
            book(with_admixtures=True),
            admixture_density=ADMIXTURE_DENSITY,
        )
        assert "not counted" not in found.describe()
        assert "4000P-57" in found.describe()


class CaseShares:
    def test_the_cement_carries_nearly_all_of_it(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.cement_share.value == pytest.approx(95.171, rel=1e-4)

    def test_the_binder_share_is_a_little_larger(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.binder_share.value > found.cement_share.value

    def test_the_heaviest_line_is_the_cement(self) -> None:
        largest = footprint_of(factories.design(), book()).largest()
        assert largest is not None
        assert largest.material_code == "CEM-I"

    def test_ranked_is_heaviest_first(self) -> None:
        ranked = footprint_of(factories.design(), book()).ranked()
        assert ranked[0].material_code == "CEM-I"
        assert ranked[0].kg_co2e >= ranked[-1].kg_co2e

    def test_replacing_cement_with_ash_moves_the_share(self) -> None:
        plain = footprint_of(factories.design(), book())
        blended = footprint_of(
            factories.design(proportions=factories.proportions(scm=200.0)), book()
        )
        assert blended.total_kg < plain.total_kg
        assert blended.cement_share.value < plain.cement_share.value

    def test_a_class_nothing_belongs_to(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.of_class(MaterialClass.FIBER) == pytest.approx(0.0)


class CaseIntensity:
    def test_it_divides_by_the_specified_strength(self) -> None:
        found = footprint_of(factories.design(), book())
        assert found.intensity(Quantity(4500, "psi")) == pytest.approx(8.7066, rel=1e-4)

    def test_a_richer_mix_can_still_be_more_efficient(self) -> None:
        lean = footprint_of(factories.design(), book())
        assert lean.intensity(Quantity(6000, "psi")) < lean.intensity(Quantity(4500, "psi"))

    def test_a_zero_strength(self) -> None:
        found = footprint_of(factories.design(), book())
        with pytest.raises(CarbonError) as caught:
            found.intensity(Quantity(0.0, "psi"))
        assert caught.value.code == "CARBON_NO_STRENGTH"


class CaseEmpty:
    def test_a_footprint_with_no_lines(self) -> None:
        empty = Footprint("X", 1, Quantity(1.0, "yd3"), Stage.A1_A3, ())
        assert empty.total_kg == pytest.approx(0.0)
        assert empty.largest() is None
        assert empty.cement_share.value == pytest.approx(0.0)
        assert empty.binder_share.value == pytest.approx(0.0)

    def test_a_line_against_a_zero_total(self) -> None:
        line = Contribution("X", MaterialClass.CEMENT, Quantity(1.0, "lb"), 0.0)
        assert line.share_of(0.0).value == pytest.approx(0.0)

    def test_a_line_describes(self) -> None:
        line = Contribution("CEM-I", MaterialClass.CEMENT, Quantity(470.0, "lb"), 196.5)
        assert "CEM-I" in line.describe()
        assert "196.5" in line.describe()


class CaseComparing:
    def test_lightest_first(self) -> None:
        plain = footprint_of(factories.design(), book())
        blended = footprint_of(
            factories.design(proportions=factories.proportions(scm=200.0)), book()
        )
        assert compare([plain, blended])[0] is blended

    def test_nothing_to_compare(self) -> None:
        assert compare([]) == ()

    def test_a_reduction_is_positive(self) -> None:
        plain = footprint_of(factories.design(), book())
        blended = footprint_of(
            factories.design(proportions=factories.proportions(scm=200.0)), book()
        )
        assert reduction(plain, blended).value > 0.0

    def test_a_change_for_the_worse_reads_negative(self) -> None:
        plain = footprint_of(factories.design(), book())
        richer = footprint_of(
            factories.design(proportions=factories.proportions(scm=0.0)), book()
        )
        assert reduction(plain, richer).value < 0.0

    def test_no_change_is_zero(self) -> None:
        plain = footprint_of(factories.design(), book())
        assert reduction(plain, plain).value == pytest.approx(0.0)

    def test_a_baseline_that_carries_nothing(self) -> None:
        empty = Footprint("X", 1, Quantity(1.0, "yd3"), Stage.A1_A3, ())
        with pytest.raises(CarbonError) as caught:
            reduction(empty, empty)
        assert caught.value.code == "CARBON_NO_BASELINE"
