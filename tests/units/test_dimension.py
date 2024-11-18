from __future__ import annotations

import pytest

from slumpcone.errors import UnitError
from slumpcone.units.dimension import Dimension, dimension_of, resolve, symbols_for


class CaseResolve:
    def test_exact_symbol(self) -> None:
        assert resolve("lb").symbol == "lb"
        assert resolve("yd3").symbol == "yd3"

    @pytest.mark.parametrize(
        ("written", "canonical"),
        [
            ("lbs", "lb"),
            ("pounds", "lb"),
            ("cy", "yd3"),
            ("yd^3", "yd3"),
            ("cf", "ft3"),
            ("gallons", "gal"),
            ("inches", "in"),
            ("hr", "h"),
            ("litre", "L"),
        ],
    )
    def test_aliases(self, written: str, canonical: str) -> None:
        assert resolve(written).symbol == canonical

    def test_surrounding_space_is_ignored(self) -> None:
        assert resolve("  psi ").symbol == "psi"

    def test_empty_symbol_is_refused(self) -> None:
        with pytest.raises(UnitError, match="required"):
            resolve("   ")

    def test_unknown_symbol_names_itself(self) -> None:
        with pytest.raises(UnitError, match="Mpa"):
            resolve("Mpa")


class CaseTable:
    def test_base_units_are_exactly_one(self) -> None:
        for symbol in ("kg", "m3", "m", "Pa", "s"):
            assert resolve(symbol).to_base == 1.0

    def test_pound_is_the_international_avoirdupois_value(self) -> None:
        assert resolve("lb").to_base == pytest.approx(0.45359237, abs=1e-12)

    def test_cubic_yard_is_twenty_seven_cubic_feet(self) -> None:
        assert resolve("yd3").to_base == pytest.approx(27 * resolve("ft3").to_base, rel=1e-12)

    def test_dimension_of(self) -> None:
        assert dimension_of("psi") is Dimension.PRESSURE
        assert dimension_of("cy") is Dimension.VOLUME

    def test_symbols_for_a_dimension(self) -> None:
        mass = symbols_for(Dimension.MASS)
        assert mass[0] == "kg"
        assert "lb" in mass
        assert "psi" not in mass

    def test_the_area_rows_were_added_for_the_sampling_rule(self) -> None:
        assert dimension_of("ft2") is Dimension.AREA
        assert resolve("sf").symbol == "ft2"
        assert resolve("yd2").to_base == pytest.approx(9 * resolve("ft2").to_base, rel=1e-9)

    def test_the_force_row_was_added_for_the_testing_machine(self) -> None:
        assert dimension_of("lbf") is Dimension.FORCE
        assert dimension_of("kN") is Dimension.FORCE
        assert resolve("kip").to_base == pytest.approx(1000 * resolve("lbf").to_base, rel=1e-12)
        assert resolve("kips").symbol == "kip"

    def test_dimension_prints_its_own_name(self) -> None:
        assert str(Dimension.VOLUME) == "volume"
