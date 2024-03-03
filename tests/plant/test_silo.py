from __future__ import annotations

import pytest

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.percent import Percent
from slumpcone.plant.silo import Silo, SiloState
from slumpcone.units.quantity import Quantity


def silo(**overrides: object) -> Silo:
    fields: dict[str, object] = {
        "code": "SI-1",
        "name": "Cement silo one",
        "material_code": "CEM-I",
        "capacity": Quantity(200000, "lb"),
        "level": Quantity(120000, "lb"),
        "low_level": Quantity(30000, "lb"),
    }
    fields.update(overrides)
    return Silo(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_codes_are_normalised(self) -> None:
        built = silo(code=" si 1 ", material_code="cem i", name="  Cement   silo one ")
        assert built.code == "SI-1"
        assert built.material_code == "CEM-I"
        assert built.name == "Cement silo one"

    def test_capacity_and_level_are_masses(self) -> None:
        with pytest.raises(ValidationError, match="capacity is a mass"):
            silo(capacity=Quantity(1, "yd3"))
        with pytest.raises(ValidationError, match="level is a mass"):
            silo(level=Quantity(1, "yd3"))

    def test_capacity_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="capacity has to be positive"):
            silo(capacity=Quantity(0, "lb"))

    def test_a_negative_level_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            silo(level=Quantity(-1, "lb"))

    def test_a_level_above_capacity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="above the"):
            silo(level=Quantity(300000, "lb"))

    def test_a_low_level_mark_is_checked_too(self) -> None:
        with pytest.raises(ValidationError, match="low level mark is a mass"):
            silo(low_level=Quantity(1, "yd3"))
        with pytest.raises(ValidationError, match="cannot be negative"):
            silo(low_level=Quantity(-1, "lb"))
        with pytest.raises(ValidationError, match="above the capacity"):
            silo(low_level=Quantity(300000, "lb"))


class CaseLevels:
    def test_headroom(self) -> None:
        assert silo().headroom == Quantity(80000, "lb")

    def test_fill(self) -> None:
        assert silo().fill == Percent(60.0)

    def test_working(self) -> None:
        assert silo().state is SiloState.WORKING
        assert not silo().state.needs_a_delivery

    def test_low(self) -> None:
        assert silo(level=Quantity(30000, "lb")).state is SiloState.LOW
        assert silo(level=Quantity(30000, "lb")).state.needs_a_delivery

    def test_empty(self) -> None:
        assert silo(level=Quantity(0, "lb")).state is SiloState.EMPTY
        assert silo(level=Quantity(0, "lb")).state.needs_a_delivery

    def test_full(self) -> None:
        assert silo(level=Quantity(200000, "lb")).state is SiloState.FULL

    def test_a_silo_with_no_low_mark_never_reads_low(self) -> None:
        assert silo(level=Quantity(1, "lb"), low_level=None).state is SiloState.WORKING

    def test_state_prints_its_own_value(self) -> None:
        assert str(SiloState.LOW) == "low"


class CaseDrawing:
    def test_a_draw_lowers_the_level(self) -> None:
        assert silo().draw(Quantity(20000, "lb")).level == Quantity(100000, "lb")

    def test_the_original_is_untouched(self) -> None:
        original = silo()
        original.draw(Quantity(20000, "lb"))
        assert original.level == Quantity(120000, "lb")

    def test_can_draw(self) -> None:
        assert silo().can_draw(Quantity(120000, "lb"))
        assert not silo().can_draw(Quantity(120001, "lb"))

    def test_drawing_more_than_there_is_refuses(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            silo().draw(Quantity(130000, "lb"))
        assert caught.value.code == "SILO_SHORT"
        assert "SI-1" in caught.value.detail

    def test_a_negative_draw_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            silo().draw(Quantity(-1, "lb"))

    def test_a_draw_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="drawdown is a mass"):
            silo().draw(Quantity(1, "yd3"))
        with pytest.raises(ValidationError, match="drawdown is a mass"):
            silo().can_draw(Quantity(1, "yd3"))

    def test_a_draw_in_another_unit_converts(self) -> None:
        emptied = silo().draw(Quantity(60, "ton"))
        assert emptied.level.value == pytest.approx(0.0, abs=1e-6)


class CaseReceiving:
    def test_a_receipt_raises_the_level(self) -> None:
        assert silo().receive(Quantity(40000, "lb")).level == Quantity(160000, "lb")

    def test_filling_exactly_to_capacity_is_allowed(self) -> None:
        assert silo().receive(Quantity(80000, "lb")).state is SiloState.FULL

    def test_overfilling_refuses(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            silo().receive(Quantity(90000, "lb"))
        assert caught.value.code == "SILO_OVERFILL"

    def test_a_negative_receipt_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            silo().receive(Quantity(-1, "lb"))

    def test_a_receipt_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="receipt is a mass"):
            silo().receive(Quantity(1, "yd3"))


class CaseReconciling:
    def test_a_short_reading_reports_a_negative_correction(self) -> None:
        corrected, difference = silo().reconcile(Quantity(115000, "lb"))
        assert corrected.level == Quantity(115000, "lb")
        assert difference == Quantity(-5000, "lb")

    def test_a_long_reading_reports_a_positive_correction(self) -> None:
        _, difference = silo().reconcile(Quantity(125000, "lb"))
        assert difference == Quantity(5000, "lb")

    def test_a_measured_level_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="measured level is a mass"):
            silo().reconcile(Quantity(1, "yd3"))

    def test_a_negative_measured_level_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            silo().reconcile(Quantity(-1, "lb"))

    def test_a_measured_level_above_capacity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="above the capacity"):
            silo().reconcile(Quantity(300000, "lb"))


class CaseAssigning:
    def test_switching_material_empties_the_vessel(self) -> None:
        switched = silo().assign("cem iii")
        assert switched.material_code == "CEM-III"
        assert switched.state is SiloState.EMPTY

    def test_describe(self) -> None:
        line = silo().describe()
        assert "SI-1" in line
        assert "CEM-I" in line
        assert "120000 lb of 200000 lb" in line
        assert "60%" in line
