from __future__ import annotations

import math

import pytest

from slumpcone.errors import UnitError, ValidationError
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


class CaseConstruction:
    def test_units_are_canonicalised(self) -> None:
        rate = MassPerVolume(564, "lbs", "cy")
        assert rate.mass_unit == "lb"
        assert rate.volume_unit == "yd3"
        assert rate.units == "lb/yd3"

    def test_mass_unit_must_be_a_mass(self) -> None:
        with pytest.raises(UnitError, match="not a mass"):
            MassPerVolume(1, "gal", "yd3")

    def test_volume_unit_must_be_a_volume(self) -> None:
        with pytest.raises(UnitError, match="not a volume"):
            MassPerVolume(1, "lb", "lb")

    def test_non_finite_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            MassPerVolume(math.inf, "lb", "yd3")

    def test_of_a_mass_and_a_volume(self) -> None:
        rate = MassPerVolume.of(Quantity(5640, "lb"), Quantity(10, "yd3"))
        assert rate == MassPerVolume(564, "lb", "yd3")

    def test_of_refuses_a_zero_volume(self) -> None:
        with pytest.raises(ValidationError):
            MassPerVolume.of(Quantity(1, "lb"), Quantity.zero("yd3"))


class CaseParse:
    @pytest.mark.parametrize(
        ("text", "value", "units"),
        [
            ("564 lb/yd3", 564.0, "lb/yd3"),
            ("335 kg per m3", 335.0, "kg/m3"),
            ("1780lb/cy", 1780.0, "lb/yd3"),
        ],
    )
    def test_reads_a_written_rate(self, text: str, value: float, units: str) -> None:
        rate = MassPerVolume.parse(text)
        assert rate.value == pytest.approx(value)
        assert rate.units == units

    @pytest.mark.parametrize("bad", ["564", "lb/yd3", "564 lb", ""])
    def test_unreadable_text_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            MassPerVolume.parse(bad)


class CaseConversion:
    def test_the_customary_to_metric_factor(self) -> None:
        metric = MassPerVolume(564, "lb", "yd3").to("kg", "m3")
        assert metric.value == pytest.approx(334.61, abs=0.01)

    def test_round_trip(self) -> None:
        rate = MassPerVolume(1780, "lb", "yd3")
        assert rate.to("kg", "m3").to("lb", "yd3") == rate

    def test_base_value_is_kilograms_per_cubic_metre(self) -> None:
        assert MassPerVolume(1, "kg", "m3").base_value == pytest.approx(1.0)

    def test_to_checks_both_dimensions(self) -> None:
        rate = MassPerVolume(564, "lb", "yd3")
        with pytest.raises(UnitError, match="not a mass"):
            rate.to("gal", "m3")
        with pytest.raises(UnitError, match="not a volume"):
            rate.to("kg", "kg")

    def test_times_a_volume_gives_a_mass(self) -> None:
        mass = MassPerVolume(564, "lb", "yd3").times(Quantity(9, "yd3"))
        assert mass == Quantity(5076, "lb")

    def test_times_converts_the_volume_first(self) -> None:
        mass = MassPerVolume(564, "lb", "yd3").times(Quantity(27, "ft3"))
        assert mass.value == pytest.approx(564.0)

    def test_times_refuses_a_non_volume(self) -> None:
        with pytest.raises(UnitError):
            MassPerVolume(564, "lb", "yd3").times(Quantity(1, "lb"))


class CaseArithmetic:
    def test_addition_and_subtraction(self) -> None:
        cement = MassPerVolume(470, "lb", "yd3")
        ash = MassPerVolume(94, "lb", "yd3")
        assert (cement + ash).value == pytest.approx(564.0)
        assert (cement - ash).value == pytest.approx(376.0)

    def test_addition_converts_the_operand(self) -> None:
        total = MassPerVolume(100, "kg", "m3") + MassPerVolume(100, "lb", "yd3")
        assert total.value == pytest.approx(159.33, abs=0.01)

    def test_scaling(self) -> None:
        assert (MassPerVolume(500, "lb", "yd3") * 0.8).value == pytest.approx(400.0)
        assert (0.8 * MassPerVolume(500, "lb", "yd3")).value == pytest.approx(400.0)
        halved = MassPerVolume(500, "lb", "yd3") / 2
        assert isinstance(halved, MassPerVolume)
        assert halved.value == pytest.approx(250.0)
        assert (-MassPerVolume(500, "lb", "yd3")).value == pytest.approx(-500.0)

    def test_ratio_of_two_rates(self) -> None:
        water = MassPerVolume(254, "lb", "yd3")
        cement = MassPerVolume(564, "lb", "yd3")
        assert water / cement == pytest.approx(0.4504, abs=1e-4)

    def test_division_by_zero_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            MassPerVolume(1, "lb", "yd3") / 0
        with pytest.raises(ValidationError):
            MassPerVolume(1, "lb", "yd3") / MassPerVolume(0, "lb", "yd3")


class CaseComparison:
    def test_equality_crosses_unit_pairs(self) -> None:
        assert MassPerVolume(564, "lb", "yd3") == MassPerVolume(564, "lb", "yd3").to("kg", "m3")

    def test_against_a_non_rate(self) -> None:
        assert MassPerVolume(1, "lb", "yd3") != 1.0

    def test_ordering(self) -> None:
        low = MassPerVolume(470, "lb", "yd3")
        high = MassPerVolume(564, "lb", "yd3")
        assert low < high
        assert high > low
        assert low <= MassPerVolume(470, "lb", "yd3")
        assert low >= MassPerVolume(470, "lb", "yd3")

    def test_hash_and_zero(self) -> None:
        assert hash(MassPerVolume(1, "kg", "m3")) == hash(MassPerVolume(1, "kg", "m3"))
        assert MassPerVolume(0, "lb", "yd3").is_zero()

    def test_text(self) -> None:
        assert str(MassPerVolume(564.0, "lb", "yd3")) == "564.0 lb/yd3"
        assert MassPerVolume(564.0, "lb", "yd3").format(2) == "564.00 lb/yd3"
        assert "MassPerVolume(" in repr(MassPerVolume(1, "lb", "yd3"))
