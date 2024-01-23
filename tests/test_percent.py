from __future__ import annotations

import math

import pytest

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent


class CaseConstruction:
    def test_value_is_the_percentage_not_the_fraction(self) -> None:
        assert Percent(6.0).value == pytest.approx(6.0)
        assert Percent(6.0).fraction == pytest.approx(0.06)

    def test_from_fraction(self) -> None:
        assert Percent.from_fraction(0.06) == Percent(6.0)

    def test_non_finite_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Percent(math.nan)

    @pytest.mark.parametrize("text", ["6", "6%", " 6.0 % ", "6.00"])
    def test_parse(self, text: str) -> None:
        assert Percent.parse(text) == Percent(6.0)

    @pytest.mark.parametrize("bad", ["", "six", "%"])
    def test_unreadable_text_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            Percent.parse(bad)

    def test_negative_is_allowed_because_deviations_are_signed(self) -> None:
        assert Percent(-1.5).fraction == pytest.approx(-0.015)


class CaseArithmetic:
    def test_of_an_amount(self) -> None:
        assert Percent(25.0).of(564.0) == pytest.approx(141.0)

    def test_addition_and_subtraction(self) -> None:
        assert Percent(6.0) + Percent(1.5) == Percent(7.5)
        assert Percent(6.0) - Percent(1.5) == Percent(4.5)

    def test_scaling(self) -> None:
        assert Percent(6.0) * 2 == Percent(12.0)
        assert 2 * Percent(6.0) == Percent(12.0)
        assert Percent(6.0) / 2 == Percent(3.0)

    def test_division_by_zero_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Percent(6.0) / 0

    def test_sign(self) -> None:
        assert -Percent(6.0) == Percent(-6.0)
        assert abs(Percent(-6.0)) == Percent(6.0)


class CaseComparison:
    def test_ordering(self) -> None:
        assert Percent(4.5) < Percent(6.0)
        assert Percent(6.0) > Percent(4.5)
        assert Percent(6.0) <= Percent(6.0)
        assert Percent(6.0) >= Percent(6.0)

    def test_against_a_non_percent(self) -> None:
        assert Percent(6.0) != 6.0

    def test_hash(self) -> None:
        assert hash(Percent(6.0)) == hash(Percent.from_fraction(0.06))

    def test_truthiness(self) -> None:
        assert Percent(0.1)
        assert not Percent(0.0)

    def test_text(self) -> None:
        assert str(Percent(6.0)) == "6.0%"
        assert Percent(6.25).format(2) == "6.25%"
        assert repr(Percent(6.0)) == "Percent(6.0)"
