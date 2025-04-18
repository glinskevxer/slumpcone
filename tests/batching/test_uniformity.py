from __future__ import annotations

import pytest

from slumpcone.batching.uniformity import (
    AIR_CONTENT,
    AIR_FREE_MORTAR,
    REQUIRED_PASSES,
    Basis,
    Comparison,
    UniformityError,
    UniformityLimit,
    UniformityResult,
    UniformitySample,
    compare,
    failing_mixers,
    slump_limit,
)
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def sample(
    label: str = "first",
    *,
    unit_weight: float = 145.0,
    air: float = 5.0,
    slump: float = 4.0,
    retained: float = 42.0,
    coarse: float = 15.225,
    strength: float | None = None,
) -> UniformitySample:
    return UniformitySample(
        label,
        MassPerVolume(unit_weight, "lb", "ft3"),
        Percent(air),
        Quantity(slump, "in"),
        Percent(retained),
        2.68,
        Quantity(0.25, "ft3"),
        Quantity(coarse, "lb"),
        None if strength is None else Quantity(strength, "psi"),
    )


class CaseLimits:
    def test_an_absolute_limit_is_a_plain_gap(self) -> None:
        assert AIR_CONTENT.difference(5.0, 6.2) == pytest.approx(1.2)

    def test_a_share_limit_divides_by_the_average(self) -> None:
        # A gap of 2 on an average of 100 is 2 percent.
        assert AIR_FREE_MORTAR.difference(99.0, 101.0) == pytest.approx(2.0)

    def test_the_order_of_the_pair_does_not_matter(self) -> None:
        assert AIR_CONTENT.difference(6.2, 5.0) == AIR_CONTENT.difference(5.0, 6.2)

    def test_a_share_of_a_zero_average(self) -> None:
        with pytest.raises(UniformityError) as caught:
            AIR_FREE_MORTAR.difference(0.0, 0.0)
        assert caught.value.code == "UNIFORMITY_ZERO_AVERAGE"

    def test_a_row_on_the_limit_passes(self) -> None:
        assert AIR_CONTENT.judge(5.0, 6.0).passed

    def test_a_row_over_the_limit_fails(self) -> None:
        row = AIR_CONTENT.judge(5.0, 6.5)
        assert not row.passed
        assert row.margin == pytest.approx(-0.5)

    def test_describe_carries_the_unit(self) -> None:
        assert "%" in AIR_CONTENT.judge(5.0, 6.5).describe()
        assert "over" in AIR_CONTENT.judge(5.0, 6.5).describe()

    def test_a_share_row_always_describes_in_percent(self) -> None:
        assert AIR_FREE_MORTAR.judge(99.0, 101.0).describe().count("%") == 2

    def test_the_basis_reads_as_words(self) -> None:
        assert str(Basis.SHARE_OF_AVERAGE) == "share of average"


class CaseSlumpLimit:
    @pytest.mark.parametrize("average", [1.0, 3.0, 4.0])
    def test_a_stiff_batch_gets_one_inch(self, average: float) -> None:
        assert slump_limit(average).limit == pytest.approx(1.0)

    @pytest.mark.parametrize("average", [4.5, 6.0])
    def test_a_wet_batch_gets_an_inch_and_a_half(self, average: float) -> None:
        assert slump_limit(average).limit == pytest.approx(1.5)

    def test_above_six_inches_the_table_runs_out(self) -> None:
        with pytest.raises(UniformityError) as caught:
            slump_limit(6.5)
        assert caught.value.code == "UNIFORMITY_SLUMP_OFF_TABLE"

    def test_a_zero_average(self) -> None:
        with pytest.raises(UniformityError) as caught:
            slump_limit(0.0)
        assert caught.value.code == "UNIFORMITY_SLUMP_NOT_POSITIVE"


class CaseSample:
    def test_the_air_free_unit_weight(self) -> None:
        assert sample().air_free_unit_weight == pytest.approx(152.6315789, rel=1e-6)

    def test_zero_air_leaves_the_unit_weight_alone(self) -> None:
        assert sample(air=0.0).air_free_unit_weight == pytest.approx(145.0)

    def test_the_sample_mass_comes_off_the_unit_weight(self) -> None:
        assert sample().sample_mass.value == pytest.approx(36.25)

    def test_the_air_free_mortar_unit_weight(self) -> None:
        assert sample().air_free_mortar_unit_weight == pytest.approx(143.5557189, rel=1e-6)

    def test_all_rock_leaves_no_mortar(self) -> None:
        with pytest.raises(UniformityError) as caught:
            assert sample(coarse=40.0).air_free_mortar_unit_weight
        assert caught.value.code == "UNIFORMITY_NO_MORTAR"

    def test_a_gravity_of_zero(self) -> None:
        with pytest.raises(UniformityError) as caught:
            UniformitySample(
                "first",
                MassPerVolume(145.0, "lb", "ft3"),
                Percent(5.0),
                Quantity(4.0, "in"),
                Percent(42.0),
                0.0,
                Quantity(0.25, "ft3"),
                Quantity(15.0, "lb"),
            )
        assert caught.value.code == "UNIFORMITY_NO_GRAVITY"

    def test_a_measure_with_no_volume(self) -> None:
        with pytest.raises(UniformityError) as caught:
            UniformitySample(
                "first",
                MassPerVolume(145.0, "lb", "ft3"),
                Percent(5.0),
                Quantity(4.0, "in"),
                Percent(42.0),
                2.68,
                Quantity(0.0, "ft3"),
                Quantity(15.0, "lb"),
            )
        assert caught.value.code == "UNIFORMITY_NO_VOLUME"

    def test_air_at_a_hundred_percent(self) -> None:
        with pytest.raises(UniformityError) as caught:
            sample(air=100.0)
        assert caught.value.code == "UNIFORMITY_AIR_OFF_SCALE"


def five_good_rows() -> tuple[Comparison, ...]:
    """Five comparisons that all sit inside their limits."""
    return (
        AIR_CONTENT.judge(5.0, 5.1),
        AIR_CONTENT.judge(5.0, 5.2),
        AIR_CONTENT.judge(5.0, 5.3),
        AIR_FREE_MORTAR.judge(143.0, 143.5),
        AIR_FREE_MORTAR.judge(143.0, 143.6),
    )


class CaseCompare:
    def test_a_tight_mixer_passes_every_row(self) -> None:
        result = compare(
            "MX-1",
            sample("first"),
            sample("second", unit_weight=144.6, air=5.4, retained=43.0, coarse=15.60),
        )
        assert result.passes == 5
        assert result.is_uniform
        assert result.failures == ()

    def test_the_strength_row_only_shows_when_both_were_broken(self) -> None:
        without = compare("MX-1", sample("first"), sample("second"))
        assert len(without.comparisons) == 5
        with_strength = compare(
            "MX-1",
            sample("first", strength=3200.0),
            sample("second", strength=3300.0),
        )
        assert len(with_strength.comparisons) == 6

    def test_one_sample_broken_is_not_enough(self) -> None:
        result = compare("MX-1", sample("first", strength=3200.0), sample("second"))
        assert len(result.comparisons) == 5

    def test_one_bad_row_out_of_six_still_passes(self) -> None:
        # Perturbing a sample moves several rows at once, because four of the
        # six read off the same measurements. The counting rule is easier to
        # state on rows than on samples, so it is stated on rows.
        result = UniformityResult("MX-1", (*five_good_rows(), AIR_CONTENT.judge(5.0, 7.5)))
        assert len(result.failures) == 1
        assert result.passes == 5
        assert result.is_uniform

    def test_two_bad_rows_out_of_six_fail(self) -> None:
        result = compare(
            "MX-1",
            sample("first", slump=3.0, strength=3200.0),
            sample("second", air=7.5, slump=5.0, retained=60.0, strength=3300.0),
        )
        assert len(result.failures) >= 2
        assert not result.is_uniform

    def test_five_rows_all_have_to_pass_when_there_are_only_five(self) -> None:
        rows = (*five_good_rows()[:4], AIR_CONTENT.judge(5.0, 7.5))
        result = UniformityResult("MX-1", rows)
        assert result.passes == 4
        assert not result.is_uniform

    def test_the_slump_limit_follows_the_average(self) -> None:
        result = compare("MX-1", sample("first", slump=5.0), sample("second", slump=6.2))
        slump_row = next(row for row in result.comparisons if row.name == "slump")
        # The average is 5.6, so the wetter limit applies and 1.2 is inside it.
        assert slump_row.limit == pytest.approx(1.5)
        assert slump_row.passed

    def test_two_samples_with_the_same_label(self) -> None:
        with pytest.raises(UniformityError) as caught:
            compare("MX-1", sample("first"), sample("first"))
        assert caught.value.code == "UNIFORMITY_SAME_SAMPLE"

    def test_describe(self) -> None:
        result = compare("MX-1", sample("first"), sample("second"))
        assert "MX-1" in result.describe()
        assert "uniform" in result.describe()

    def test_a_failed_mixer_says_so(self) -> None:
        result = compare("MX-1", sample("first"), sample("second", air=9.0, retained=60.0))
        assert "not uniform" in result.describe()


class CaseFleet:
    def test_nothing_tested(self) -> None:
        assert failing_mixers([]) == ()

    def test_it_names_only_the_failures(self) -> None:
        good = compare("MX-1", sample("first"), sample("second"))
        bad = compare("MX-2", sample("first"), sample("second", air=9.0, retained=60.0))
        assert failing_mixers([good, bad]) == ("MX-2",)

    def test_the_order_is_the_order_tested(self) -> None:
        first = compare("MX-9", sample("first"), sample("second", air=9.0, retained=60.0))
        second = compare("MX-2", sample("first"), sample("second", air=9.0, retained=60.0))
        assert failing_mixers([first, second]) == ("MX-9", "MX-2")


def test_the_standard_asks_for_five_of_six() -> None:
    assert REQUIRED_PASSES == 5


def test_an_empty_result_cannot_be_uniform() -> None:
    assert not UniformityResult("MX-1", ()).is_uniform


def test_a_custom_limit_can_be_declared() -> None:
    tighter = UniformityLimit("air content", 0.5, Basis.ABSOLUTE, "%")
    assert not tighter.judge(5.0, 6.0).passed
