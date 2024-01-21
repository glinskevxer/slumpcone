from __future__ import annotations

import math

import pytest

from slumpcone.errors import UnitError, ValidationError
from slumpcone.units.temperature import Temperature, TemperatureDelta


class CaseConstruction:
    @pytest.mark.parametrize("written", ["C", "c", "degC", "°C", "celsius", " CELSIUS "])
    def test_celsius_spellings(self, written: str) -> None:
        assert Temperature(20, written).unit == "C"

    @pytest.mark.parametrize("written", ["F", "f", "degF", "fahrenheit"])
    def test_fahrenheit_spellings(self, written: str) -> None:
        assert Temperature(70, written).unit == "F"

    def test_unknown_scale_is_refused(self) -> None:
        with pytest.raises(UnitError):
            Temperature(300, "K")

    def test_non_finite_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            Temperature(math.nan, "C")

    def test_below_absolute_zero_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="absolute zero"):
            Temperature(-300, "C")

    def test_absolute_zero_itself_is_allowed(self) -> None:
        assert Temperature(-273.15, "C").celsius == pytest.approx(-273.15)


class CaseConversion:
    @pytest.mark.parametrize(
        ("f", "c"),
        [(32.0, 0.0), (212.0, 100.0), (70.0, 21.111111), (-40.0, -40.0), (90.0, 32.222222)],
    )
    def test_the_two_scales_agree(self, f: float, c: float) -> None:
        assert Temperature(f, "F").celsius == pytest.approx(c, abs=1e-5)
        assert Temperature(c, "C").fahrenheit == pytest.approx(f, abs=1e-5)

    def test_to_is_a_no_op_on_the_same_scale(self) -> None:
        t = Temperature(70, "F")
        assert t.to("F") is t

    def test_round_trip(self) -> None:
        assert Temperature(88, "F").to("C").to("F") == Temperature(88, "F")

    def test_parse(self) -> None:
        assert Temperature.parse("72 F") == Temperature(72, "F")
        assert Temperature.parse("22degC") == Temperature(22, "C")
        assert Temperature.parse("-4 C").celsius == pytest.approx(-4.0)

    @pytest.mark.parametrize("bad", ["72", "hot", "72 K", ""])
    def test_unreadable_text_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            Temperature.parse(bad)


class CaseComparison:
    def test_equality_crosses_scales(self) -> None:
        assert Temperature(32, "F") == Temperature(0, "C")

    def test_ordering(self) -> None:
        assert Temperature(50, "F") < Temperature(20, "C")
        assert Temperature(20, "C") > Temperature(50, "F")
        assert Temperature(32, "F") <= Temperature(0, "C")
        assert Temperature(32, "F") >= Temperature(0, "C")

    def test_hash_agrees_across_scales(self) -> None:
        assert hash(Temperature(212, "F")) == hash(Temperature(100, "C"))

    def test_against_a_non_temperature(self) -> None:
        assert Temperature(70, "F") != "70 F"

    def test_text(self) -> None:
        assert str(Temperature(72.4, "F")) == "72 degF"
        assert repr(Temperature(72.0, "F")) == "Temperature(72.0, 'F')"


class CaseDelta:
    def test_difference_of_two_temperatures_is_a_delta(self) -> None:
        d = Temperature(90, "F") - Temperature(70, "F")
        assert isinstance(d, TemperatureDelta)
        assert d.value == pytest.approx(20.0)

    def test_a_delta_scales_without_an_offset(self) -> None:
        assert TemperatureDelta(10, "C").to("F").value == pytest.approx(18.0)
        assert TemperatureDelta(18, "F").to("C").value == pytest.approx(10.0)

    def test_adding_a_delta_to_a_temperature(self) -> None:
        assert Temperature(70, "F") + TemperatureDelta(10, "F") == Temperature(80, "F")

    def test_subtracting_a_delta_from_a_temperature(self) -> None:
        result = Temperature(70, "F") - TemperatureDelta(10, "F")
        assert isinstance(result, Temperature)
        assert result == Temperature(60, "F")

    def test_delta_arithmetic(self) -> None:
        five_c = TemperatureDelta(5, "C")
        nine_f = TemperatureDelta(9, "F")
        assert (five_c + nine_f).value == pytest.approx(10.0)
        assert (five_c - nine_f).value == pytest.approx(0.0)
        assert (TemperatureDelta(5, "C") * 2).value == pytest.approx(10.0)
        assert (2 * TemperatureDelta(5, "C")).value == pytest.approx(10.0)
        assert (-TemperatureDelta(5, "C")).value == pytest.approx(-5.0)
        assert abs(TemperatureDelta(-5, "C")).value == pytest.approx(5.0)

    def test_delta_comparison(self) -> None:
        assert TemperatureDelta(5, "C") == TemperatureDelta(9, "F")
        assert TemperatureDelta(4, "C") < TemperatureDelta(9, "F")
        assert TemperatureDelta(6, "C") > TemperatureDelta(9, "F")
        assert TemperatureDelta(5, "C") <= TemperatureDelta(9, "F")
        assert TemperatureDelta(5, "C") >= TemperatureDelta(9, "F")
        assert hash(TemperatureDelta(5, "C")) == hash(TemperatureDelta(9, "F"))
        assert TemperatureDelta(5, "C") != 5

    def test_delta_is_finite(self) -> None:
        with pytest.raises(ValidationError):
            TemperatureDelta(math.inf, "C")

    def test_delta_text(self) -> None:
        assert str(TemperatureDelta(2.5, "C")) == "2.5 degC"

    def test_a_temperature_cannot_be_multiplied(self) -> None:
        assert not hasattr(Temperature(70, "F"), "__mul__")
