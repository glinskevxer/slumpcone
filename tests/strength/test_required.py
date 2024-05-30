from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.required import (
    FULL_RECORD_TESTS,
    MIN_RECORD_TESTS,
    modification_factor,
    required_average_strength,
    required_from_deviation,
    required_without_record,
    sample_standard_deviation,
)
from slumpcone.units.quantity import Quantity


def psi(*values: float) -> list[Quantity]:
    return [Quantity(value, "psi") for value in values]


def record(count: int, mean: float = 5000.0, spread: float = 400.0) -> list[Quantity]:
    """A record that alternates either side of the mean by a fixed amount."""
    return [
        Quantity(mean + (spread if index % 2 else -spread), "psi") for index in range(count)
    ]


class CaseStandardDeviation:
    def test_a_simple_set(self) -> None:
        deviation = sample_standard_deviation(psi(4800.0, 5000.0, 5200.0))
        assert deviation.value == pytest.approx(200.0)

    def test_it_is_the_sample_divisor(self) -> None:
        # Population deviation of this set is 100; sample is 141.42.
        deviation = sample_standard_deviation(psi(4900.0, 5100.0))
        assert deviation.value == pytest.approx(141.42, abs=0.01)

    def test_an_identical_set_has_no_spread(self) -> None:
        assert sample_standard_deviation(psi(5000.0, 5000.0)).value == pytest.approx(0.0)

    def test_one_test_is_not_enough(self) -> None:
        with pytest.raises(ValidationError, match="at least two tests"):
            sample_standard_deviation(psi(5000.0))

    def test_units_convert(self) -> None:
        mixed = [Quantity(4800, "psi"), Quantity(34.474, "MPa")]
        assert sample_standard_deviation(mixed).value == pytest.approx(141.42, abs=1.0)


class CaseModificationFactor:
    @pytest.mark.parametrize(
        ("count", "factor"), [(15, 1.16), (20, 1.08), (25, 1.03), (30, 1.00), (45, 1.00)]
    )
    def test_the_table_rows(self, count: int, factor: float) -> None:
        assert modification_factor(count) == pytest.approx(factor)

    def test_between_rows_it_interpolates(self) -> None:
        assert modification_factor(17) == pytest.approx(1.128, abs=1e-3)
        assert modification_factor(22) == pytest.approx(1.06, abs=1e-3)

    def test_below_fifteen_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="below the 15 needed"):
            modification_factor(14)

    def test_the_thresholds(self) -> None:
        assert MIN_RECORD_TESTS == 15
        assert FULL_RECORD_TESTS == 30


class CaseFromDeviation:
    def test_a_consistent_plant_is_bound_by_the_average_rule(self) -> None:
        # At s = 300 the average rule gives 4402 and the individual rule 4199.
        required = required_from_deviation(Quantity(4000, "psi"), Quantity(300, "psi"))
        assert required.value == pytest.approx(4402.0, abs=1.0)

    def test_a_variable_plant_is_bound_by_the_individual_rule(self) -> None:
        # At s = 700 the average rule gives 4938 and the individual rule 5131.
        required = required_from_deviation(Quantity(4000, "psi"), Quantity(700, "psi"))
        assert required.value == pytest.approx(5131.0, abs=1.0)

    def test_above_the_branch_the_second_formula_changes(self) -> None:
        required = required_from_deviation(Quantity(6000, "psi"), Quantity(600, "psi"))
        assert required.value == pytest.approx(6804.0, abs=1.0)

    def test_a_perfect_plant_still_designs_above_the_specified(self) -> None:
        required = required_from_deviation(Quantity(4000, "psi"), Quantity(0, "psi"))
        assert required.value == pytest.approx(4000.0)

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="specified strength is a pressure"):
            required_from_deviation(Quantity(4000, "lb"), Quantity(300, "psi"))
        with pytest.raises(ValidationError, match="deviation is a pressure"):
            required_from_deviation(Quantity(4000, "psi"), Quantity(300, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            required_from_deviation(Quantity(0, "psi"), Quantity(300, "psi"))
        with pytest.raises(ValidationError, match="cannot be negative"):
            required_from_deviation(Quantity(4000, "psi"), Quantity(-1, "psi"))


class CaseWithoutRecord:
    @pytest.mark.parametrize(
        ("specified", "required"),
        [(2500.0, 3500.0), (3000.0, 4200.0), (5000.0, 6200.0), (6000.0, 7300.0)],
    )
    def test_the_table(self, specified: float, required: float) -> None:
        result = required_without_record(Quantity(specified, "psi"))
        assert result.value == pytest.approx(required)

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            required_without_record(Quantity(4000, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            required_without_record(Quantity(0, "psi"))


class CaseRequiredAverageStrength:
    def test_no_record_at_all(self) -> None:
        result = required_average_strength(Quantity(4000, "psi"))
        assert result.basis == "no qualifying record"
        assert result.required.value == pytest.approx(5200.0)
        assert result.test_count == 0
        assert result.deviation is None

    def test_a_short_record_is_no_record(self) -> None:
        result = required_average_strength(Quantity(4000, "psi"), record(10))
        assert result.basis == "no qualifying record"
        assert result.test_count == 10

    def test_a_full_record_takes_the_deviation_at_face_value(self) -> None:
        result = required_average_strength(Quantity(4000, "psi"), record(30))
        assert result.basis == "test record"
        assert result.factor == pytest.approx(1.0)
        assert result.deviation is not None
        assert result.deviation.value == pytest.approx(406.8, abs=1.0)

    def test_a_short_record_inflates_the_deviation(self) -> None:
        short = required_average_strength(Quantity(4000, "psi"), record(15))
        full = required_average_strength(Quantity(4000, "psi"), record(30))
        assert short.factor > full.factor
        assert short.required > full.required

    def test_a_record_beats_having_none(self) -> None:
        with_record = required_average_strength(Quantity(4000, "psi"), record(30))
        without = required_average_strength(Quantity(4000, "psi"))
        assert with_record.required < without.required

    def test_the_margin(self) -> None:
        result = required_average_strength(Quantity(4000, "psi"))
        assert result.margin == Quantity(1200, "psi")

    def test_describe_without_a_record(self) -> None:
        text = required_average_strength(Quantity(4000, "psi")).describe()
        assert "specified 4000 psi" in text
        assert "no qualifying record" in text

    def test_describe_with_a_record(self) -> None:
        text = required_average_strength(Quantity(4000, "psi"), record(20)).describe()
        assert "test record" in text
        assert "from 20 tests" in text
        assert "x 1.08" in text
