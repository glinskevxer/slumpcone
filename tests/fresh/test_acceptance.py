from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.acceptance import LoadOutcome, PropertyOutcome, judge_load
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.percent import Percent
from slumpcone.tolerance import Side
from slumpcone.units.quantity import Quantity
from tests.factories import design, proportions

TAKEN = datetime(2024, 6, 12, 8, 5)


def slump_test(value: float, minutes: int = 0, retest: bool = False) -> FreshTest:
    return FreshTest(
        "881204",
        FreshTestKind.SLUMP,
        TAKEN + timedelta(minutes=minutes),
        slump=Quantity(value, "in"),
        is_retest=retest,
    )


def air_test(value: float, minutes: int = 0, retest: bool = False) -> FreshTest:
    return FreshTest(
        "881204",
        FreshTestKind.AIR_PRESSURE,
        TAKEN + timedelta(minutes=minutes),
        air=Percent(value),
        is_retest=retest,
    )


class CaseOutcomes:
    def test_settled_outcomes(self) -> None:
        assert PropertyOutcome.PASSED.is_settled
        assert PropertyOutcome.FAILED.is_settled
        assert not PropertyOutcome.RETEST_DUE.is_settled
        assert not PropertyOutcome.NOT_TESTED.is_settled

    def test_acceptable_outcomes(self) -> None:
        assert PropertyOutcome.PASSED_ON_RETEST.is_acceptable
        assert PropertyOutcome.NOT_TESTED.is_acceptable
        assert not PropertyOutcome.FAILED.is_acceptable

    def test_they_print_their_own_values(self) -> None:
        assert str(PropertyOutcome.RETEST_DUE) == "retest_due"
        assert str(LoadOutcome.REJECTED) == "rejected"


class CaseSlump:
    def test_a_passing_slump(self) -> None:
        verdict = judge_load("881204", [slump_test(4.0)], design())
        assert verdict.outcome is LoadOutcome.ACCEPTED
        slump = verdict.property_for("slump")
        assert slump is not None
        assert slump.outcome is PropertyOutcome.PASSED

    def test_one_failing_slump_asks_for_a_retest(self) -> None:
        verdict = judge_load("881204", [slump_test(7.0)], design())
        assert verdict.outcome is LoadOutcome.RETEST_DUE

    def test_a_passing_retest_saves_the_load(self) -> None:
        verdict = judge_load(
            "881204", [slump_test(7.0), slump_test(5.0, minutes=4, retest=True)], design()
        )
        slump = verdict.property_for("slump")
        assert slump is not None
        assert slump.outcome is PropertyOutcome.PASSED_ON_RETEST
        assert verdict.outcome is LoadOutcome.ACCEPTED

    def test_a_failing_retest_rejects_the_load(self) -> None:
        verdict = judge_load(
            "881204", [slump_test(7.0), slump_test(6.8, minutes=4, retest=True)], design()
        )
        assert verdict.outcome is LoadOutcome.REJECTED
        assert [p.kind for p in verdict.failures] == ["slump"]

    def test_a_third_sample_does_not_count(self) -> None:
        verdict = judge_load(
            "881204",
            [
                slump_test(7.0),
                slump_test(6.8, minutes=4, retest=True),
                slump_test(4.0, minutes=9, retest=True),
            ],
            design(),
        )
        assert verdict.outcome is LoadOutcome.REJECTED

    def test_a_low_slump_fails_the_same_way(self) -> None:
        verdict = judge_load("881204", [slump_test(1.0)], design())
        slump = verdict.property_for("slump")
        assert slump is not None
        assert slump.sides[0] is Side.LOW

    def test_nothing_tested(self) -> None:
        verdict = judge_load("881204", [], design())
        assert verdict.outcome is LoadOutcome.NOT_TESTED
        slump = verdict.property_for("slump")
        assert slump is not None
        assert slump.first is None
        assert slump.governing is None
        assert "not tested" in slump.describe()


class CaseAir:
    def test_air_is_judged_when_the_design_has_a_band(self) -> None:
        verdict = judge_load("881204", [slump_test(4.0), air_test(6.0)], design())
        assert verdict.property_for("air") is not None

    def test_a_design_with_no_air_band_is_not_judged_on_air(self) -> None:
        no_air = design(proportions=proportions(air=0.0))
        verdict = judge_load("881204", [slump_test(4.0)], no_air)
        assert verdict.property_for("air") is None

    def test_a_volumetric_reading_counts_the_same(self) -> None:
        volumetric = FreshTest("881204", FreshTestKind.AIR_VOLUMETRIC, TAKEN, air=Percent(6.1))
        verdict = judge_load("881204", [slump_test(4.0), volumetric], design())
        air = verdict.property_for("air")
        assert air is not None
        assert air.outcome is PropertyOutcome.PASSED

    def test_the_retest_budgets_are_kept_apart(self) -> None:
        verdict = judge_load(
            "881204",
            [
                slump_test(7.0),
                slump_test(5.0, minutes=4, retest=True),
                air_test(9.0, minutes=6),
            ],
            design(),
        )
        slump = verdict.property_for("slump")
        air = verdict.property_for("air")
        assert slump is not None and air is not None
        assert slump.outcome is PropertyOutcome.PASSED_ON_RETEST
        assert air.outcome is PropertyOutcome.RETEST_DUE
        assert verdict.outcome is LoadOutcome.RETEST_DUE

    def test_a_failure_anywhere_rejects_the_load(self) -> None:
        verdict = judge_load(
            "881204",
            [
                slump_test(4.0),
                air_test(9.0),
                air_test(9.2, minutes=5, retest=True),
            ],
            design(),
        )
        assert verdict.outcome is LoadOutcome.REJECTED


class CaseOrdering:
    def test_samples_are_judged_in_the_order_they_were_taken(self) -> None:
        verdict = judge_load(
            "881204",
            [slump_test(5.0, minutes=4, retest=True), slump_test(7.0)],
            design(),
        )
        slump = verdict.property_for("slump")
        assert slump is not None
        assert slump.first == pytest.approx(7.0)
        assert slump.outcome is PropertyOutcome.PASSED_ON_RETEST

    def test_a_test_from_another_ticket_is_refused(self) -> None:
        other = FreshTest("881205", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4, "in"))
        with pytest.raises(ValidationError, match="881205"):
            judge_load("881204", [other], design())


class CaseReporting:
    def test_describe(self) -> None:
        verdict = judge_load("881204", [slump_test(7.0), air_test(6.0)], design())
        text = verdict.describe()
        assert "ticket 881204: retest_due" in text
        assert "slump: 7" in text
        assert "air: 6" in text

    def test_an_unknown_property_comes_back_empty(self) -> None:
        verdict = judge_load("881204", [slump_test(4.0)], design())
        assert verdict.property_for("temperature") is None
