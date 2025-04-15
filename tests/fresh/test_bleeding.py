from __future__ import annotations

import pytest

from slumpcone.fresh.bleeding import (
    BleedingError,
    BleedReading,
    BleedTest,
    ColumnSegregation,
    VisualStability,
    worst_bleeder,
)
from slumpcone.units.quantity import Quantity


def reading(minutes: float, pounds: float) -> BleedReading:
    return BleedReading(minutes, Quantity(pounds, "lb"))


def bleed_test(*readings: BleedReading, sample: float = 60.0) -> BleedTest:
    return BleedTest(
        "881204",
        Quantity(sample, "lb"),
        Quantity(4000.0, "lb"),
        Quantity(260.0, "lb"),
        Quantity(100.0, "in2"),
        readings,
    )


class CaseReading:
    def test_it_holds_what_it_was_given(self) -> None:
        one = reading(10.0, 0.05)
        assert one.elapsed_minutes == pytest.approx(10.0)
        assert one.water == Quantity(0.05, "lb")

    def test_zero_elapsed_is_refused(self) -> None:
        with pytest.raises(BleedingError) as caught:
            reading(0.0, 0.05)
        assert caught.value.code == "BLEED_READING_NOT_ELAPSED"

    def test_negative_water_is_refused(self) -> None:
        with pytest.raises(BleedingError) as caught:
            reading(10.0, -0.01)
        assert caught.value.code == "BLEED_READING_NEGATIVE"

    def test_a_dry_draw_is_allowed(self) -> None:
        assert reading(60.0, 0.0).water.is_zero()


class CaseTestGuards:
    def test_a_zero_sample_is_refused(self) -> None:
        with pytest.raises(BleedingError) as caught:
            bleed_test(sample=0.0)
        assert caught.value.code == "BLEED_TEST_NOT_POSITIVE"

    def test_a_sample_bigger_than_its_batch(self) -> None:
        with pytest.raises(BleedingError) as caught:
            bleed_test(sample=5000.0)
        assert caught.value.code == "BLEED_SAMPLE_OVER_BATCH"

    def test_readings_out_of_order(self) -> None:
        with pytest.raises(BleedingError) as caught:
            bleed_test(reading(30.0, 0.02), reading(10.0, 0.03))
        assert caught.value.code == "BLEED_READINGS_UNORDERED"

    def test_no_readings_is_a_test_that_has_not_run(self) -> None:
        assert bleed_test().duration_minutes == pytest.approx(0.0)
        assert bleed_test().total_water.is_zero()


class CaseFigures:
    def test_the_sample_carries_its_share_of_the_water(self) -> None:
        # 60 lb out of a 4000 lb batch is 1.5 percent, of 260 lb of water.
        assert bleed_test().sample_water.value == pytest.approx(3.9)

    def test_the_draws_add_up(self) -> None:
        subject = bleed_test(reading(10, 0.05), reading(20, 0.04), reading(40, 0.03))
        assert subject.total_water.value == pytest.approx(0.12)
        assert subject.duration_minutes == pytest.approx(40.0)

    def test_bleeding_as_a_share_of_mixing_water(self) -> None:
        subject = bleed_test(reading(10, 0.05), reading(20, 0.04), reading(40, 0.03))
        assert subject.bleeding_percent_of_mixing_water.value == pytest.approx(
            0.12 / 3.9 * 100.0
        )

    def test_bleeding_as_a_depth(self) -> None:
        subject = bleed_test(reading(60, 0.624))
        # 0.624 lb of water is 0.01 ft3, which is 17.28 in3, over 100 in2.
        assert subject.bleeding_volume_per_area == pytest.approx(0.1728)

    def test_the_rate_over_the_whole_run(self) -> None:
        subject = bleed_test(reading(60, 0.39))
        assert subject.rate_percent_per_hour().value == pytest.approx(10.0)

    def test_the_rate_after_the_first_draw(self) -> None:
        subject = bleed_test(reading(10, 0.30), reading(70, 0.39))
        # Only the second draw counts, over the hour after minute ten.
        assert subject.rate_percent_per_hour(after_minutes=10.0).value == pytest.approx(10.0)

    def test_the_early_draw_dominates_the_whole_run_rate(self) -> None:
        subject = bleed_test(reading(10, 0.30), reading(70, 0.39))
        assert (
            subject.rate_percent_per_hour().value
            > subject.rate_percent_per_hour(after_minutes=10.0).value
        )

    def test_a_window_with_nothing_in_it(self) -> None:
        with pytest.raises(BleedingError) as caught:
            bleed_test(reading(10, 0.05)).rate_percent_per_hour(after_minutes=90.0)
        assert caught.value.code == "BLEED_RATE_NO_WINDOW"

    def test_describe(self) -> None:
        text = bleed_test(reading(60, 0.39)).describe()
        assert "881204" in text
        assert "60 min" in text


class CaseWorst:
    def test_nothing_to_pick(self) -> None:
        assert worst_bleeder([]) is None

    def test_it_picks_the_heaviest_bleeder(self) -> None:
        mild = bleed_test(reading(60, 0.10))
        heavy = bleed_test(reading(60, 0.50))
        assert worst_bleeder([mild, heavy]) is heavy

    def test_one_test_is_its_own_worst(self) -> None:
        only = bleed_test(reading(60, 0.10))
        assert worst_bleeder([only]) is only


class CaseSegregation:
    def test_a_uniform_column_reads_zero(self) -> None:
        column = ColumnSegregation("881204", Quantity(3.0, "lb"), Quantity(3.0, "lb"))
        assert column.index.value == pytest.approx(0.0)
        assert column.direction == "uniform"
        assert column.is_acceptable

    def test_a_settled_column(self) -> None:
        column = ColumnSegregation("881204", Quantity(2.0, "lb"), Quantity(3.0, "lb"))
        # 2 * (3 - 2) / 5 is 40 percent.
        assert column.index.value == pytest.approx(40.0)
        assert column.direction == "settled"
        assert not column.is_acceptable

    def test_a_risen_column_reads_negative(self) -> None:
        column = ColumnSegregation("881204", Quantity(3.0, "lb"), Quantity(2.0, "lb"))
        assert column.index.value == pytest.approx(-40.0)
        assert column.direction == "risen"

    def test_the_cap_is_ten_percent(self) -> None:
        near = ColumnSegregation("881204", Quantity(2.85, "lb"), Quantity(3.15, "lb"))
        assert near.index.value == pytest.approx(10.0)
        assert near.is_acceptable

    def test_an_empty_column(self) -> None:
        with pytest.raises(BleedingError) as caught:
            ColumnSegregation("881204", Quantity(0.0, "lb"), Quantity(0.0, "lb"))
        assert caught.value.code == "SEGREGATION_NO_AGGREGATE"

    def test_a_negative_section(self) -> None:
        with pytest.raises(BleedingError) as caught:
            ColumnSegregation("881204", Quantity(-1.0, "lb"), Quantity(3.0, "lb"))
        assert caught.value.code == "SEGREGATION_NEGATIVE"

    def test_describe(self) -> None:
        column = ColumnSegregation("881204", Quantity(2.0, "lb"), Quantity(3.0, "lb"))
        assert "settled" in column.describe()


class CaseVisualStability:
    def test_zero_and_one_pass(self) -> None:
        assert VisualStability.STABLE.is_acceptable
        assert VisualStability.STABLE_WITH_SHEEN.is_acceptable

    def test_two_still_passes(self) -> None:
        assert VisualStability.SLIGHT_HALO.is_acceptable

    def test_three_fails(self) -> None:
        assert not VisualStability.SEGREGATING.is_acceptable

    def test_every_index_has_a_note(self) -> None:
        for index in VisualStability:
            assert index.note

    def test_the_name_reads_as_words(self) -> None:
        assert str(VisualStability.STABLE_WITH_SHEEN) == "stable with sheen"
