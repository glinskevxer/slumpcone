from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.units.dimension import Dimension
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem
from slumpcone.units.temperature import Temperature


class CaseParse:
    @pytest.mark.parametrize("text", ["customary", "US", " imperial ", "English"])
    def test_customary_spellings(self, text: str) -> None:
        assert UnitSystem.parse(text) is UnitSystem.CUSTOMARY

    @pytest.mark.parametrize("text", ["metric", "SI", " si "])
    def test_metric_spellings(self, text: str) -> None:
        assert UnitSystem.parse(text) is UnitSystem.METRIC

    def test_unknown_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="unit system"):
            UnitSystem.parse("cgs")

    def test_prints_its_own_name(self) -> None:
        assert str(UnitSystem.METRIC) == "metric"


class CaseCustomary:
    system = UnitSystem.CUSTOMARY

    def test_units(self) -> None:
        assert self.system.mass == "lb"
        assert self.system.small_mass == "oz"
        assert self.system.volume == "yd3"
        assert self.system.small_volume == "floz"
        assert self.system.water_volume == "gal"
        assert self.system.length == "in"
        assert self.system.pressure == "psi"
        assert self.system.temperature == "F"


class CaseMetric:
    system = UnitSystem.METRIC

    def test_units(self) -> None:
        assert self.system.mass == "kg"
        assert self.system.small_mass == "g"
        assert self.system.volume == "m3"
        assert self.system.small_volume == "mL"
        assert self.system.water_volume == "L"
        assert self.system.length == "mm"
        assert self.system.pressure == "MPa"
        assert self.system.temperature == "C"


class CaseConversion:
    def test_preferred_by_dimension(self) -> None:
        assert UnitSystem.CUSTOMARY.preferred(Dimension.PRESSURE) == "psi"
        assert UnitSystem.METRIC.preferred(Dimension.VOLUME) == "m3"
        assert UnitSystem.METRIC.preferred(Dimension.TIME) == "min"

    def test_convert_restates_a_quantity(self) -> None:
        result = UnitSystem.METRIC.convert(Quantity(4000, "psi"))
        assert result.unit == "MPa"
        assert result.value == pytest.approx(27.579, abs=1e-3)

    def test_convert_temperature(self) -> None:
        reading = UnitSystem.CUSTOMARY.convert_temperature(Temperature(20, "C"))
        assert reading == Temperature(68, "F")
