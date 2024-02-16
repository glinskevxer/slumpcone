from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.gradation import SIEVES, Gradation, Sieve, sieve
from slumpcone.percent import Percent

# A number 57 coarse aggregate, and a concrete sand, both as a lab reports them.
STONE_57 = {
    "1-1/2 in": 100.0,
    "1 in": 97.0,
    "3/4 in": 72.0,
    "1/2 in": 41.0,
    "3/8 in": 22.0,
    "No. 4": 4.0,
    "No. 8": 1.0,
}

SAND = {
    "3/8 in": 100.0,
    "No. 4": 98.0,
    "No. 8": 85.0,
    "No. 16": 68.0,
    "No. 30": 44.0,
    "No. 50": 17.0,
    "No. 100": 4.0,
    "No. 200": 1.5,
}


class CaseSieve:
    def test_the_stack_runs_coarse_to_fine(self) -> None:
        openings = [s.opening_mm for s in SIEVES]
        assert openings == sorted(openings, reverse=True)

    def test_lookup_by_label(self) -> None:
        assert sieve("No. 4").opening_mm == pytest.approx(4.75)
        assert sieve(" 3/4 in ").opening_mm == pytest.approx(19.0)

    def test_lookup_accepts_a_hash(self) -> None:
        assert sieve("#4") == sieve("No. 4")
        assert sieve("no.4") == sieve("No. 4")

    def test_unknown_sieve_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="unknown sieve"):
            sieve("No. 7")

    def test_ordering(self) -> None:
        assert sieve("No. 4") < sieve("1 in")
        assert sieve("1 in") > sieve("No. 4")
        assert sieve("1 in") >= sieve("1 in")
        assert sieve("1 in") <= sieve("1 in")

    def test_opening_is_a_length(self) -> None:
        assert sieve("1 in").opening.to("in").value == pytest.approx(0.9843, abs=1e-4)

    def test_prints_its_label(self) -> None:
        assert str(Sieve("No. 4", 4.75)) == "No. 4"


class CaseConstruction:
    def test_of_sorts_coarse_to_fine(self) -> None:
        grading = Gradation.of(STONE_57)
        assert [str(s) for s, _ in grading.passing][0] == "1-1/2 in"
        assert [str(s) for s, _ in grading.passing][-1] == "No. 8"

    def test_an_empty_gradation_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one sieve"):
            Gradation(())

    def test_a_repeated_sieve_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="twice"):
            Gradation(
                (
                    (sieve("1 in"), Percent(100.0)),
                    (sieve("1 in"), Percent(90.0)),
                )
            )

    def test_a_percentage_outside_the_range_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="outside 0 to 100"):
            Gradation(((sieve("1 in"), Percent(101.0)),))

    def test_percent_passing_cannot_rise_down_the_stack(self) -> None:
        with pytest.raises(ValidationError, match="rises at"):
            Gradation(
                (
                    (sieve("1 in"), Percent(80.0)),
                    (sieve("3/4 in"), Percent(90.0)),
                )
            )

    def test_out_of_order_sieves_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="coarse to fine"):
            Gradation(
                (
                    (sieve("3/4 in"), Percent(90.0)),
                    (sieve("1 in"), Percent(80.0)),
                )
            )


class CaseReadings:
    grading = Gradation.of(STONE_57)

    def test_passing_on(self) -> None:
        value = self.grading.passing_on("3/4 in")
        assert value is not None
        assert value.value == pytest.approx(72.0)

    def test_passing_on_a_sieve_that_was_not_run(self) -> None:
        assert self.grading.passing_on("No. 200") is None

    def test_retained_on(self) -> None:
        value = self.grading.retained_on("3/4 in")
        assert value is not None
        assert value.value == pytest.approx(28.0)

    def test_retained_on_a_sieve_that_was_not_run(self) -> None:
        assert self.grading.retained_on("No. 200") is None

    def test_coarsest_and_finest(self) -> None:
        assert str(self.grading.coarsest) == "1-1/2 in"
        assert str(self.grading.finest) == "No. 8"


class CaseFinenessModulus:
    def test_a_concrete_sand(self) -> None:
        assert Gradation.of(SAND).fineness_modulus == pytest.approx(2.84)

    def test_sieves_coarser_than_the_stack_are_skipped(self) -> None:
        assert Gradation.of(SAND).fineness_modulus < 3.0

    def test_a_missing_interior_sieve_is_refused(self) -> None:
        broken = dict(SAND)
        del broken["No. 100"]
        with pytest.raises(ValidationError, match="No. 100"):
            _ = Gradation.of(broken).fineness_modulus

    def test_a_coarse_aggregate_has_a_high_modulus(self) -> None:
        readings = dict(STONE_57)
        readings.update({"No. 16": 0.0, "No. 30": 0.0, "No. 50": 0.0, "No. 100": 0.0})
        assert Gradation.of(readings).fineness_modulus > 6.5


class CaseNominalMaximumSize:
    def test_a_57_stone_is_a_one_inch_aggregate(self) -> None:
        assert str(Gradation.of(STONE_57).nominal_max_size) == "1 in"

    def test_a_sand_is_a_number_four_aggregate(self) -> None:
        assert str(Gradation.of(SAND).nominal_max_size) == "No. 4"

    def test_a_stack_that_never_reaches_ninety_uses_the_coarsest(self) -> None:
        grading = Gradation.of({"1 in": 60.0, "3/4 in": 40.0})
        assert str(grading.nominal_max_size) == "1 in"

    def test_describe(self) -> None:
        text = Gradation.of(STONE_57).describe()
        assert text.startswith("1 in nominal")
        assert "3/4 in=72%" in text
