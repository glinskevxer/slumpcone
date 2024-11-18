from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.spec.frequency import (
    AREA_PER_SAMPLE,
    VOLUME_PER_SAMPLE,
    WAIVER_VOLUME,
    check_frequency,
    may_waive_strength_tests,
    required_samples,
)
from slumpcone.units.quantity import Quantity


class CaseRequiredSamples:
    def test_the_day_rule_binds_on_a_small_pour(self) -> None:
        requirement = required_samples(Quantity(60, "yd3"), 1)
        assert requirement.required == 1
        assert requirement.governing_rule == "one a day"

    def test_the_volume_rule_binds_on_a_big_one(self) -> None:
        requirement = required_samples(Quantity(600, "yd3"), 1)
        assert requirement.from_volume == 4
        assert requirement.required == 4
        assert requirement.governing_rule == "volume"

    def test_a_partial_hundred_and_fifty_still_counts(self) -> None:
        assert required_samples(Quantity(151, "yd3"), 1).from_volume == 2

    def test_several_days_raise_the_floor(self) -> None:
        requirement = required_samples(Quantity(120, "yd3"), 3)
        assert requirement.required == 3
        assert requirement.governing_rule == "one a day"

    def test_the_area_rule_binds_on_a_thin_slab(self) -> None:
        requirement = required_samples(Quantity(150, "yd3"), 1, Quantity(24000, "ft2"))
        assert requirement.from_area == 5
        assert requirement.required == 5
        assert requirement.governing_rule == "surface area"

    def test_no_area_means_no_area_rule(self) -> None:
        assert required_samples(Quantity(150, "yd3"), 1).from_area == 0

    def test_nothing_placed_needs_nothing(self) -> None:
        requirement = required_samples(Quantity(0, "yd3"), 1)
        assert requirement.required == 0
        assert requirement.governing_rule == "none"

    def test_the_thresholds(self) -> None:
        assert VOLUME_PER_SAMPLE.value == pytest.approx(150.0)
        assert AREA_PER_SAMPLE.value == pytest.approx(5000.0)

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="placed quantity is a volume"):
            required_samples(Quantity(150, "lb"), 1)
        with pytest.raises(ValidationError, match="cannot be negative"):
            required_samples(Quantity(-1, "yd3"), 1)
        with pytest.raises(ValidationError, match="placement days"):
            required_samples(Quantity(150, "yd3"), -1)
        with pytest.raises(ValidationError, match="surface area is an area"):
            required_samples(Quantity(150, "yd3"), 1, Quantity(5000, "ft3"))

    def test_a_metric_area_works(self) -> None:
        requirement = required_samples(Quantity(150, "yd3"), 1, Quantity(2000, "m2"))
        assert requirement.from_area == 5

    def test_describe(self) -> None:
        text = required_samples(Quantity(600, "yd3"), 1).describe()
        assert "4 sample(s) required by the volume rule" in text


class CaseWaiver:
    def test_a_small_class_may_be_waived(self) -> None:
        assert may_waive_strength_tests(Quantity(40, "yd3"))

    def test_exactly_fifty_may_not(self) -> None:
        assert not may_waive_strength_tests(WAIVER_VOLUME)

    def test_a_large_class_may_not(self) -> None:
        assert not may_waive_strength_tests(Quantity(600, "yd3"))

    def test_a_non_volume_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a volume"):
            may_waive_strength_tests(Quantity(40, "lb"))


class CaseCheckFrequency:
    def test_enough_samples(self) -> None:
        finding = check_frequency("SLAB", Quantity(600, "yd3"), 1, 4)
        assert finding.conforms
        assert finding.shortfall == 0
        assert "ok" in finding.describe()

    def test_too_few(self) -> None:
        finding = check_frequency("SLAB", Quantity(600, "yd3"), 1, 2)
        assert not finding.conforms
        assert finding.shortfall == 2
        assert "2 short" in finding.describe()

    def test_a_small_class_is_forgiven_by_the_waiver(self) -> None:
        finding = check_frequency("FOOTING", Quantity(40, "yd3"), 1, 0)
        assert finding.shortfall == 1
        assert finding.waiver_available
        assert finding.conforms
        assert "waiver is available" in finding.describe()

    def test_the_area_rule_can_produce_the_shortfall(self) -> None:
        finding = check_frequency("SLAB", Quantity(150, "yd3"), 1, 1, Quantity(24000, "ft2"))
        assert finding.shortfall == 4

    def test_the_class_code_is_folded(self) -> None:
        assert check_frequency("slab", Quantity(60, "yd3"), 1, 1).class_code == "SLAB"

    def test_a_negative_sample_count_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="sample count"):
            check_frequency("SLAB", Quantity(60, "yd3"), 1, -1)

    def test_more_samples_than_needed(self) -> None:
        finding = check_frequency("SLAB", Quantity(60, "yd3"), 1, 5)
        assert finding.shortfall == 0
        assert finding.conforms
