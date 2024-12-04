from __future__ import annotations

from decimal import Decimal

import pytest

from slumpcone.errors import ValidationError
from slumpcone.money import Money, minor_units, total


class CaseCurrencies:
    def test_known_currencies(self) -> None:
        assert minor_units("usd") == 2
        assert minor_units("JPY") == 0

    def test_an_unknown_currency(self) -> None:
        with pytest.raises(ValidationError, match="unknown currency"):
            minor_units("XYZ")


class CaseConstruction:
    def test_it_quantises_to_the_minor_unit(self) -> None:
        assert Money.of("12.345").amount == Decimal("12.35")
        assert Money.of("12.344").amount == Decimal("12.34")

    def test_a_currency_with_no_minor_unit(self) -> None:
        assert Money.of("1234.56", "JPY").amount == Decimal("1235")

    def test_it_does_not_go_through_binary_float(self) -> None:
        running = Money.zero()
        for _ in range(10):
            running = running + Money.of("0.10")
        assert running == Money.of("1.00")

    def test_zero(self) -> None:
        assert Money.zero().is_zero()
        assert not Money.zero()

    def test_an_unknown_currency_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="unknown currency"):
            Money.of("1.00", "XYZ")

    def test_something_that_is_not_an_amount(self) -> None:
        with pytest.raises(ValidationError, match="not an amount"):
            Money("twelve")  # type: ignore[arg-type]

    def test_a_non_finite_amount(self) -> None:
        with pytest.raises(ValidationError, match="has to be finite"):
            Money(Decimal("nan"))


class CaseParse:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("12.50", "12.50"),
            ("$12.50", "12.50"),
            ("$1,234.56", "1234.56"),
            ("-12.50", "-12.50"),
            (" 12 ", "12.00"),
        ],
    )
    def test_reading(self, text: str, expected: str) -> None:
        assert Money.parse(text) == Money.of(expected)

    @pytest.mark.parametrize("bad", ["", "twelve", "12.50.50", "$"])
    def test_unreadable(self, bad: str) -> None:
        with pytest.raises(ValidationError, match="as an amount"):
            Money.parse(bad)


class CaseArithmetic:
    def test_addition_and_subtraction(self) -> None:
        assert Money.of("10.00") + Money.of("2.50") == Money.of("12.50")
        assert Money.of("10.00") - Money.of("2.50") == Money.of("7.50")

    def test_scaling(self) -> None:
        assert Money.of("10.00") * 3 == Money.of("30.00")
        assert 3 * Money.of("10.00") == Money.of("30.00")
        assert Money.of("10.00") / 4 == Money.of("2.50")

    def test_scaling_rounds_to_the_minor_unit(self) -> None:
        assert Money.of("10.00") / 3 == Money.of("3.33")

    def test_division_by_zero(self) -> None:
        with pytest.raises(ValidationError, match="division by zero"):
            Money.of("10.00") / 0

    def test_sign(self) -> None:
        assert -Money.of("10.00") == Money.of("-10.00")
        assert abs(Money.of("-10.00")) == Money.of("10.00")

    def test_mixing_currencies_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot add"):
            Money.of("10.00", "USD") + Money.of("10.00", "EUR")

    def test_the_ratio_of_two_amounts(self) -> None:
        assert Money.of("30.00").ratio_to(Money.of("120.00")) == pytest.approx(0.25)

    def test_a_ratio_against_nothing(self) -> None:
        with pytest.raises(ValidationError, match="zero amount"):
            Money.of("1.00").ratio_to(Money.zero())

    def test_total_of_an_empty_list(self) -> None:
        assert total([]).is_zero()

    def test_total(self) -> None:
        assert total([Money.of("1.10"), Money.of("2.20")]) == Money.of("3.30")


class CaseComparison:
    def test_ordering(self) -> None:
        assert Money.of("1.00") < Money.of("2.00")
        assert Money.of("2.00") > Money.of("1.00")
        assert Money.of("1.00") <= Money.of("1.00")
        assert Money.of("1.00") >= Money.of("1.00")

    def test_ordering_across_currencies_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot order"):
            _ = Money.of("1.00", "USD") < Money.of("1.00", "EUR")

    def test_equality_across_currencies_is_false(self) -> None:
        assert Money.of("1.00", "USD") != Money.of("1.00", "EUR")

    def test_against_a_non_amount(self) -> None:
        assert Money.of("1.00") != 1.0

    def test_hashing(self) -> None:
        assert hash(Money.of("1.00")) == hash(Money.of("1.000"))


class CaseSplit:
    def test_an_even_split(self) -> None:
        parts = Money.of("9.00").split(3)
        assert parts == (Money.of("3.00"),) * 3

    def test_an_uneven_split_still_adds_up(self) -> None:
        parts = Money.of("1.01").split(3)
        assert parts == (Money.of("0.34"), Money.of("0.34"), Money.of("0.33"))
        assert total(list(parts)) == Money.of("1.01")

    def test_a_negative_split(self) -> None:
        parts = Money.of("-1.01").split(3)
        assert total(list(parts)) == Money.of("-1.01")

    def test_splitting_into_one(self) -> None:
        assert Money.of("1.01").split(1) == (Money.of("1.01"),)

    def test_splitting_into_nothing(self) -> None:
        with pytest.raises(ValidationError, match="fewer than one part"):
            Money.of("1.00").split(0)


class CaseText:
    def test_the_symbol(self) -> None:
        assert Money.of("1234.5").format() == "$1,234.50"

    def test_a_negative_amount(self) -> None:
        assert Money.of("-1234.5").format() == "-$1,234.50"

    def test_without_a_symbol(self) -> None:
        assert Money.of("1234.5").format(symbol=False) == "1,234.50 USD"

    def test_a_currency_with_no_symbol(self) -> None:
        assert "JPY" in Money.of("1234", "JPY").format(symbol=False)

    def test_str_and_repr(self) -> None:
        assert str(Money.of("1.00")) == "$1.00"
        assert repr(Money.of("1.00")) == "Money('1.00', 'USD')"
