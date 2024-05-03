from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume
from slumpcone.units.temperature import Temperature

TAKEN = datetime(2024, 6, 12, 8, 5)


class CaseKind:
    def test_parse(self) -> None:
        assert FreshTestKind.parse("slump") is FreshTestKind.SLUMP
        assert FreshTestKind.parse("AIR") is FreshTestKind.AIR_PRESSURE
        assert FreshTestKind.parse("air volumetric") is FreshTestKind.AIR_VOLUMETRIC
        assert FreshTestKind.parse("density") is FreshTestKind.UNIT_WEIGHT
        assert FreshTestKind.parse("temp") is FreshTestKind.TEMPERATURE

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="unknown fresh test"):
            FreshTestKind.parse("bleed")

    def test_standards(self) -> None:
        assert FreshTestKind.SLUMP.standard == "ASTM C143"
        assert FreshTestKind.AIR_PRESSURE.standard == "ASTM C231"
        assert FreshTestKind.AIR_VOLUMETRIC.standard == "ASTM C173"
        assert FreshTestKind.UNIT_WEIGHT.standard == "ASTM C138"

    def test_air_family(self) -> None:
        assert FreshTestKind.AIR_PRESSURE.is_air
        assert FreshTestKind.AIR_VOLUMETRIC.is_air
        assert not FreshTestKind.SLUMP.is_air

    def test_which_tests_can_reject_a_load(self) -> None:
        assert FreshTestKind.SLUMP.can_reject_a_load
        assert FreshTestKind.AIR_PRESSURE.can_reject_a_load
        assert not FreshTestKind.TEMPERATURE.can_reject_a_load
        assert not FreshTestKind.UNIT_WEIGHT.can_reject_a_load

    def test_the_pressure_meter_does_not_suit_lightweight(self) -> None:
        assert not FreshTestKind.AIR_PRESSURE.suits_lightweight
        assert FreshTestKind.AIR_VOLUMETRIC.suits_lightweight

    def test_prints_its_own_value(self) -> None:
        assert str(FreshTestKind.AIR_PRESSURE) == "air_pressure"


class CaseReadingRequired:
    def test_slump_needs_a_slump(self) -> None:
        with pytest.raises(ValidationError, match="slump test needs a reading"):
            FreshTest("881204", FreshTestKind.SLUMP, TAKEN)

    def test_air_needs_an_air_content(self) -> None:
        with pytest.raises(ValidationError, match="needs a reading"):
            FreshTest("881204", FreshTestKind.AIR_PRESSURE, TAKEN)

    def test_temperature_needs_a_temperature(self) -> None:
        with pytest.raises(ValidationError, match="needs a reading"):
            FreshTest("881204", FreshTestKind.TEMPERATURE, TAKEN)

    def test_unit_weight_needs_a_unit_weight(self) -> None:
        with pytest.raises(ValidationError, match="needs a reading"):
            FreshTest("881204", FreshTestKind.UNIT_WEIGHT, TAKEN)

    def test_a_slump_reading_on_a_slump_test_is_enough(self) -> None:
        result = FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4.5, "in"))
        assert result.slump is not None


class CaseRanges:
    def test_a_slump_has_to_be_a_length(self) -> None:
        with pytest.raises(ValidationError, match="slump is a length"):
            FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4, "lb"))

    def test_a_negative_slump_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(-1, "in"))

    def test_a_collapsed_cone_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="collapsed cone"):
            FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(13, "in"))

    def test_an_impossible_air_content_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not a reading"):
            FreshTest("881204", FreshTestKind.AIR_PRESSURE, TAKEN, air=Percent(30.0))

    def test_a_non_positive_unit_weight_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            FreshTest(
                "881204",
                FreshTestKind.UNIT_WEIGHT,
                TAKEN,
                unit_weight=MassPerVolume(0, "lb", "ft3"),
            )

    def test_the_discharge_before_a_sample_is_a_volume(self) -> None:
        with pytest.raises(ValidationError, match="is a volume"):
            FreshTest(
                "881204",
                FreshTestKind.SLUMP,
                TAKEN,
                slump=Quantity(4, "in"),
                discharged_before_sample=Quantity(1, "lb"),
            )

    def test_a_negative_discharge_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            FreshTest(
                "881204",
                FreshTestKind.SLUMP,
                TAKEN,
                slump=Quantity(4, "in"),
                discharged_before_sample=Quantity(-1, "yd3"),
            )


class CaseRecord:
    def test_the_ticket_number_is_normalised(self) -> None:
        result = FreshTest(" 881204 ", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4, "in"))
        assert result.ticket_number == "881204"

    def test_the_technician_is_normalised(self) -> None:
        result = FreshTest(
            "881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4, "in"), technician="tech 7"
        )
        assert result.technician == "TECH-7"

    def test_value_text_by_kind(self) -> None:
        slump = FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4.5, "in"))
        air = FreshTest("881204", FreshTestKind.AIR_PRESSURE, TAKEN, air=Percent(6.2))
        temp = FreshTest(
            "881204", FreshTestKind.TEMPERATURE, TAKEN, temperature=Temperature(78, "F")
        )
        weight = FreshTest(
            "881204",
            FreshTestKind.UNIT_WEIGHT,
            TAKEN,
            unit_weight=MassPerVolume(142.6, "lb", "ft3"),
        )
        assert slump.value_text == "4.50 in"
        assert air.value_text == "6.2%"
        assert temp.value_text == "78 degF"
        assert weight.value_text == "142.6 lb/ft3"

    def test_describe(self) -> None:
        result = FreshTest("881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4.5, "in"))
        assert result.describe() == "881204  slump  4.50 in  2024-06-12 08:05"

    def test_a_retest_says_so(self) -> None:
        result = FreshTest(
            "881204", FreshTestKind.SLUMP, TAKEN, slump=Quantity(4.5, "in"), is_retest=True
        )
        assert result.describe().endswith("retest")
