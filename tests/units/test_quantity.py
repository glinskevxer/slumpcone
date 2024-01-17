from __future__ import annotations

import math

import pytest

from slumpcone.errors import UnitError, ValidationError
from slumpcone.units.dimension import Dimension
from slumpcone.units.quantity import Quantity


class CaseConstruction:
    def test_unit_is_canonicalised(self) -> None:
        assert Quantity(1.0, "lbs").unit == "lb"
        assert Quantity(1.0, "cy").unit == "yd3"

    def test_integers_become_floats(self) -> None:
        q = Quantity(564, "lb")
        assert isinstance(q.value, float)

    def test_dimension_is_read_from_the_unit(self) -> None:
        assert Quantity(4000, "psi").dimension is Dimension.PRESSURE

    def test_unknown_unit_is_refused(self) -> None:
        with pytest.raises(UnitError):
            Quantity(1.0, "furlong")

    @pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
    def test_non_finite_is_refused(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="finite"):
            Quantity(bad, "lb")

    def test_zero_carries_a_unit(self) -> None:
        assert Quantity.zero("lb") == Quantity(0.0, "lb")


class CaseParse:
    @pytest.mark.parametrize(
        ("text", "value", "unit"),
        [
            ("3000 psi", 3000.0, "psi"),
            ("27ft3", 27.0, "ft3"),
            ("  564.5  lb ", 564.5, "lb"),
            ("-1.5 in", -1.5, "in"),
            ("1e3 kg", 1000.0, "kg"),
        ],
    )
    def test_reads_a_written_quantity(self, text: str, value: float, unit: str) -> None:
        q = Quantity.parse(text)
        assert q.value == pytest.approx(value)
        assert q.unit == unit

    @pytest.mark.parametrize("bad", ["", "psi", "   ", "4000"])
    def test_unreadable_text_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            Quantity.parse(bad)


class CaseConversion:
    def test_pounds_to_kilograms(self) -> None:
        assert Quantity(100, "lb").to("kg").value == pytest.approx(45.359237)

    def test_cubic_yards_to_cubic_feet(self) -> None:
        assert Quantity(1, "yd3").to("ft3").value == pytest.approx(27.0)

    def test_psi_to_megapascal(self) -> None:
        assert Quantity(4000, "psi").to("MPa").value == pytest.approx(27.5790, abs=1e-4)

    def test_round_trip_returns_the_original(self) -> None:
        q = Quantity(3.75, "in")
        assert q.to("mm").to("in") == q

    def test_cross_dimension_conversion_is_refused(self) -> None:
        with pytest.raises(UnitError, match="measures"):
            Quantity(1, "lb").to("yd3")

    def test_base_value_is_si(self) -> None:
        assert Quantity(1, "ft3").base_value == pytest.approx(0.028316846592)


class CaseArithmetic:
    def test_addition_keeps_the_left_unit(self) -> None:
        total = Quantity(1, "yd3") + Quantity(27, "ft3")
        assert total.unit == "yd3"
        assert total.value == pytest.approx(2.0)

    def test_subtraction(self) -> None:
        assert (Quantity(10, "gal") - Quantity(4, "gal")).value == pytest.approx(6.0)

    def test_scalar_multiplication_both_ways(self) -> None:
        assert (Quantity(2, "lb") * 3).value == pytest.approx(6.0)
        assert (3 * Quantity(2, "lb")).value == pytest.approx(6.0)

    def test_scalar_division(self) -> None:
        half = Quantity(9, "yd3") / 2
        assert isinstance(half, Quantity)
        assert half.value == pytest.approx(4.5)

    def test_quantity_division_is_a_ratio(self) -> None:
        ratio = Quantity(300, "lb") / Quantity(600, "lb")
        assert ratio == pytest.approx(0.5)

    def test_negation_and_absolute(self) -> None:
        assert (-Quantity(3, "in")).value == pytest.approx(-3.0)
        assert abs(Quantity(-3, "in")).value == pytest.approx(3.0)

    def test_adding_across_dimensions_is_refused(self) -> None:
        with pytest.raises(UnitError, match="add"):
            Quantity(1, "lb") + Quantity(1, "gal")

    def test_dividing_by_zero_scalar_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Quantity(1, "lb") / 0

    def test_dividing_by_a_zero_quantity_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Quantity(1, "lb") / Quantity.zero("lb")

    def test_dividing_across_dimensions_is_refused(self) -> None:
        with pytest.raises(UnitError):
            Quantity(1, "lb") / Quantity(1, "gal")


class CaseComparison:
    def test_equality_crosses_units(self) -> None:
        assert Quantity(1, "yd3") == Quantity(27, "ft3")

    def test_different_dimensions_are_never_equal(self) -> None:
        assert Quantity(1, "lb") != Quantity(1, "gal")

    def test_equality_against_a_non_quantity(self) -> None:
        assert Quantity(1, "lb") != "1 lb"

    def test_ordering(self) -> None:
        assert Quantity(1, "in") < Quantity(1, "ft")
        assert Quantity(1, "ft") > Quantity(1, "in")
        assert Quantity(12, "in") <= Quantity(1, "ft")
        assert Quantity(12, "in") >= Quantity(1, "ft")

    def test_ordering_across_dimensions_is_refused(self) -> None:
        with pytest.raises(UnitError):
            _ = Quantity(1, "in") < Quantity(1, "lb")

    def test_hashes_agree_across_units(self) -> None:
        assert hash(Quantity(1, "yd3")) == hash(Quantity(27, "ft3"))

    def test_truthiness_follows_the_magnitude(self) -> None:
        assert Quantity(1, "lb")
        assert not Quantity.zero("lb")
        assert Quantity.zero("lb").is_zero()


class CaseText:
    def test_default_format_is_two_places(self) -> None:
        assert str(Quantity(564.0, "lb")) == "564.00 lb"

    def test_explicit_digits(self) -> None:
        assert Quantity(0.455, "yd3").format(3) == "0.455 yd3"

    def test_negative_digits_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            Quantity(1, "lb").format(-1)

    def test_format_spec_is_passed_through(self) -> None:
        assert f"{Quantity(1234.5, 'lb'):,.1f}" == "1,234.5 lb"

    def test_repr_round_trips(self) -> None:
        q = Quantity(2.5, "in")
        assert eval(repr(q)) == q  # noqa: S307


class CaseWireForm:
    def test_as_dict(self) -> None:
        assert Quantity(5, "gal").as_dict() == {"value": 5.0, "unit": "gal"}

    def test_from_dict(self) -> None:
        assert Quantity.from_dict({"value": 5, "unit": "gal"}) == Quantity(5, "gal")

    def test_from_dict_names_the_missing_key(self) -> None:
        with pytest.raises(ValidationError, match="unit"):
            Quantity.from_dict({"value": 5})
