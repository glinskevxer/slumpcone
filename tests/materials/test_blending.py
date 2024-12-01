from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.blending import (
    BlendComponent,
    blend_shares,
    blend_to_target,
    combine,
)
from slumpcone.materials.gradation import Gradation
from slumpcone.units.quantity import Quantity

STONE = {
    "1-1/2 in": 100.0,
    "1 in": 97.0,
    "3/4 in": 72.0,
    "1/2 in": 41.0,
    "3/8 in": 22.0,
    "No. 4": 4.0,
    "No. 8": 1.0,
    "No. 16": 0.5,
    "No. 30": 0.0,
    "No. 50": 0.0,
    "No. 100": 0.0,
}

SAND = {
    "3/8 in": 100.0,
    "No. 4": 98.0,
    "No. 8": 85.0,
    "No. 16": 68.0,
    "No. 30": 44.0,
    "No. 50": 17.0,
    "No. 100": 4.0,
}


def stone(weight: float = 1780.0, gravity: float | None = 2.68) -> BlendComponent:
    return BlendComponent("CA-57", Gradation.of(STONE), Quantity(weight, "lb"), gravity)


def sand(weight: float = 1255.0, gravity: float | None = 2.63) -> BlendComponent:
    return BlendComponent("FA-1", Gradation.of(SAND), Quantity(weight, "lb"), gravity)


class CaseComponent:
    def test_the_weight_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="is weighed"):
            BlendComponent("CA-57", Gradation.of(STONE), Quantity(1, "yd3"))

    def test_a_negative_weight_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            BlendComponent("CA-57", Gradation.of(STONE), Quantity(-1, "lb"))

    def test_a_non_positive_gravity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            BlendComponent("CA-57", Gradation.of(STONE), Quantity(1, "lb"), 0.0)

    def test_no_gravity_means_no_volume(self) -> None:
        with pytest.raises(ValidationError, match="cannot be blended by volume"):
            _ = stone(gravity=None).absolute_volume


class CaseShares:
    def test_by_weight(self) -> None:
        shares = blend_shares([stone(), sand()])
        assert shares[0][0] == "CA-57"
        assert shares[0][1].value == pytest.approx(58.65, abs=0.05)

    def test_by_volume_differs_when_the_gravities_do(self) -> None:
        by_weight = blend_shares([stone(), sand()])[0][1]
        by_volume = blend_shares([stone(), sand()], by_volume=True)[0][1]
        assert by_volume != by_weight

    def test_equal_gravities_give_the_same_answer(self) -> None:
        by_weight = blend_shares([stone(gravity=2.65), sand(gravity=2.65)])[0][1]
        by_volume = blend_shares([stone(gravity=2.65), sand(gravity=2.65)], by_volume=True)[0][
            1
        ]
        assert by_volume.value == pytest.approx(by_weight.value)

    def test_an_empty_blend_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one component"):
            blend_shares([])

    def test_a_blend_of_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="blend of nothing"):
            blend_shares([stone(weight=0.0), sand(weight=0.0)])


class CaseCombine:
    def test_the_combined_curve_sits_between_the_two(self) -> None:
        blended = combine([stone(), sand()])
        for label in ("No. 4", "No. 8", "No. 16"):
            stone_value = Gradation.of(STONE).passing_on(label)
            sand_value = Gradation.of(SAND).passing_on(label)
            combined = blended.passing_on(label)
            assert stone_value is not None and sand_value is not None
            assert combined is not None
            assert stone_value.value <= combined.value <= sand_value.value

    def test_every_sieve_appears(self) -> None:
        blended = combine([stone(), sand()])
        assert blended.passing_on("1-1/2 in") is not None
        assert blended.passing_on("No. 100") is not None

    def test_a_sieve_only_the_stone_was_run_on(self) -> None:
        blended = combine([stone(), sand()])
        top = blended.passing_on("1-1/2 in")
        assert top is not None
        assert top.value == pytest.approx(100.0)

    def test_all_stone_is_the_stone(self) -> None:
        blended = combine([stone(), sand(weight=0.0)])
        four = blended.passing_on("No. 4")
        assert four is not None
        assert four.value == pytest.approx(4.0)

    def test_it_still_reads_as_a_gradation(self) -> None:
        blended = combine([stone(), sand()])
        assert blended.fineness_modulus > 0.0

    def test_a_component_with_a_short_stack_is_refused(self) -> None:
        short = BlendComponent(
            "CA-57",
            Gradation.of({"1 in": 100.0, "3/4 in": 70.0}),
            Quantity(1780, "lb"),
            2.68,
        )
        with pytest.raises(ValidationError, match="not run down to"):
            combine([short, sand()])

    def test_blending_by_volume_moves_the_curve(self) -> None:
        by_weight = combine([stone(), sand()]).passing_on("No. 8")
        by_volume = combine([stone(), sand()], by_volume=True).passing_on("No. 8")
        assert by_weight is not None and by_volume is not None
        assert by_weight != by_volume


class CaseBlendToTarget:
    def test_it_finds_the_share(self) -> None:
        target = Gradation.of({"3/8 in": 100.0, "No. 8": 40.0, "No. 100": 2.0})
        share = blend_to_target(stone(), sand(), target, "No. 8")
        assert share.value == pytest.approx(53.6, abs=0.5)

    def test_the_share_actually_hits_the_target(self) -> None:
        target = Gradation.of({"3/8 in": 100.0, "No. 8": 40.0, "No. 100": 2.0})
        share = blend_to_target(stone(), sand(), target, "No. 8")
        blended = combine([stone(weight=share.value), sand(weight=100.0 - share.value)])
        reading = blended.passing_on("No. 8")
        assert reading is not None
        assert reading.value == pytest.approx(40.0, abs=0.5)

    def test_a_target_no_blend_reaches(self) -> None:
        target = Gradation.of({"3/8 in": 100.0, "No. 8": 95.0, "No. 100": 2.0})
        with pytest.raises(ValidationError, match="no blend of these two"):
            blend_to_target(stone(), sand(), target, "No. 8")

    def test_a_sieve_that_was_not_run(self) -> None:
        target = Gradation.of({"No. 8": 40.0, "No. 100": 2.0})
        with pytest.raises(ValidationError, match="not run on all three"):
            blend_to_target(stone(), sand(), target, "No. 200")

    def test_two_aggregates_that_agree_on_the_sieve(self) -> None:
        same = Gradation.of({"3/8 in": 100.0, "No. 8": 50.0, "No. 100": 2.0})
        first = BlendComponent("A", same, Quantity(100, "lb"), 2.65)
        second = BlendComponent("B", same, Quantity(100, "lb"), 2.65)
        with pytest.raises(ValidationError, match="no blend of them changes it"):
            blend_to_target(first, second, same, "No. 8")
