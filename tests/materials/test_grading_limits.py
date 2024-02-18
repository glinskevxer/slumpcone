from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.gradation import Gradation
from slumpcone.materials.grading_limits import (
    FINE_AGGREGATE,
    GradingFinding,
    check_fineness_modulus,
    check_grading,
    conforms,
    limits_for,
    size_numbers,
)
from slumpcone.percent import Percent
from slumpcone.tolerance import Band

GOOD_57 = {
    "1-1/2 in": 100.0,
    "1 in": 97.0,
    "1/2 in": 41.0,
    "No. 4": 4.0,
    "No. 8": 1.0,
}

GOOD_SAND = {
    "3/8 in": 100.0,
    "No. 4": 98.0,
    "No. 8": 85.0,
    "No. 16": 68.0,
    "No. 30": 44.0,
    "No. 50": 17.0,
    "No. 100": 4.0,
}


class CaseTable:
    def test_size_numbers_end_with_the_sand(self) -> None:
        assert size_numbers()[-1] == FINE_AGGREGATE
        assert "57" in size_numbers()

    def test_limits_for_a_coarse_size(self) -> None:
        bands = limits_for("57")
        assert bands["1 in"].low == pytest.approx(95.0)
        assert bands["No. 8"].high == pytest.approx(5.0)

    def test_a_leading_hash_is_ignored(self) -> None:
        assert limits_for("#57").keys() == limits_for("57").keys()

    def test_an_unknown_size_number_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="size number"):
            limits_for("99")


class CaseCheckGrading:
    def test_a_conforming_57(self) -> None:
        assert check_grading(Gradation.of(GOOD_57), "57") == ()
        assert conforms(Gradation.of(GOOD_57), "57")

    def test_a_sieve_outside_its_band(self) -> None:
        readings = dict(GOOD_57)
        readings["1/2 in"] = 68.0
        findings = check_grading(Gradation.of(readings), "57")
        assert [f.sieve_label for f in findings] == ["1/2 in"]
        assert not conforms(Gradation.of(readings), "57")

    def test_a_sieve_that_was_not_run_is_a_finding(self) -> None:
        readings = dict(GOOD_57)
        del readings["No. 8"]
        findings = check_grading(Gradation.of(readings), "57")
        assert findings[0].is_missing
        assert "not run" in findings[0].describe()

    def test_a_finding_describes_what_was_measured(self) -> None:
        readings = dict(GOOD_57)
        readings["1/2 in"] = 68.0
        finding = check_grading(Gradation.of(readings), "57")[0]
        assert "68.0% passing" in finding.describe()
        assert "25 to 60" in finding.describe() or "42 +/- 18" in finding.describe()

    def test_a_conforming_sand(self) -> None:
        assert conforms(Gradation.of(GOOD_SAND), FINE_AGGREGATE)

    def test_a_sand_checked_against_a_stone_size_fails_everywhere(self) -> None:
        findings = check_grading(Gradation.of(GOOD_SAND), "57")
        assert len(findings) >= 3

    def test_a_finding_can_be_built_directly(self) -> None:
        finding = GradingFinding("No. 4", Percent(12.0), Band.between(0.0, 10.0))
        assert not finding.is_missing
        assert "No. 4" in finding.describe()


class CaseFinenessModulus:
    def test_a_sand_inside_the_band_and_on_design(self) -> None:
        assert check_fineness_modulus(Gradation.of(GOOD_SAND), design_value=2.84) == ()

    def test_a_sand_outside_the_band(self) -> None:
        coarse_sand = {
            "3/8 in": 100.0,
            "No. 4": 92.0,
            "No. 8": 70.0,
            "No. 16": 44.0,
            "No. 30": 22.0,
            "No. 50": 6.0,
            "No. 100": 1.0,
        }
        complaints = check_fineness_modulus(Gradation.of(coarse_sand))
        assert len(complaints) == 1
        assert "outside" in complaints[0]

    def test_drift_from_the_design_value(self) -> None:
        complaints = check_fineness_modulus(Gradation.of(GOOD_SAND), design_value=2.55)
        assert len(complaints) == 1
        assert "from the design value" in complaints[0]

    def test_drift_exactly_at_the_limit_passes(self) -> None:
        assert check_fineness_modulus(Gradation.of(GOOD_SAND), design_value=2.64) == ()

    def test_both_rules_can_fire_at_once(self) -> None:
        fine_sand = {
            "3/8 in": 100.0,
            "No. 4": 100.0,
            "No. 8": 98.0,
            "No. 16": 90.0,
            "No. 30": 70.0,
            "No. 50": 35.0,
            "No. 100": 12.0,
        }
        complaints = check_fineness_modulus(Gradation.of(fine_sand), design_value=2.84)
        assert len(complaints) == 2

    def test_no_design_value_means_only_the_band_is_checked(self) -> None:
        assert check_fineness_modulus(Gradation.of(GOOD_SAND)) == ()
