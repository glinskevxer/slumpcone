from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.cores import (
    AVERAGE_THRESHOLD,
    INDIVIDUAL_THRESHOLD,
    Core,
    CoreCondition,
    CoreInvestigation,
    investigate,
)
from slumpcone.units.quantity import Quantity

SPECIFIED = Quantity(4000, "psi")
AREA = 12.566370614359172


def core(code: str, strength: float, ratio: float = 2.0, **overrides: object) -> Core:
    diameter = 4.0
    from slumpcone.strength.breaks import length_diameter_correction

    load = strength * AREA / length_diameter_correction(ratio)
    fields: dict[str, object] = {
        "code": code,
        "diameter": Quantity(diameter, "in"),
        "length": Quantity(diameter * ratio, "in"),
        "max_load": Quantity(load, "lbf"),
    }
    fields.update(overrides)
    return Core(**fields)  # type: ignore[arg-type]


class CaseCondition:
    def test_which_conditions_match_service(self) -> None:
        assert CoreCondition.SOAKED.matches_service
        assert CoreCondition.AIR_DRIED.matches_service
        assert not CoreCondition.AS_RECEIVED.matches_service

    def test_it_prints_its_own_value(self) -> None:
        assert str(CoreCondition.AIR_DRIED) == "air dried"


class CaseCore:
    def test_the_dimensions_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="core diameter is a length"):
            core("C-1", 3600.0, diameter=Quantity(4, "lb"))
        with pytest.raises(ValidationError, match="core length has to be positive"):
            core("C-1", 3600.0, length=Quantity(0, "in"))

    def test_the_load_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="load is a force"):
            core("C-1", 3600.0, max_load=Quantity(1000, "lb"))
        with pytest.raises(ValidationError, match="load has to be positive"):
            core("C-1", 3600.0, max_load=Quantity(0, "lbf"))

    def test_a_full_length_core(self) -> None:
        built = core("C-1", 3600.0)
        assert built.length_diameter_ratio == pytest.approx(2.0)
        assert built.strength.value == pytest.approx(3600.0, abs=1.0)

    def test_a_short_core_is_corrected(self) -> None:
        built = core("C-1", 3600.0, ratio=1.25)
        assert built.strength.value == pytest.approx(3600.0, abs=1.0)

    def test_a_core_shorter_than_one_diameter(self) -> None:
        built = Core("C-1", Quantity(4, "in"), Quantity(3, "in"), Quantity(40000, "lbf"))
        assert not built.is_testable
        with pytest.raises(ValidationError, match="cannot be corrected"):
            _ = built.strength
        assert "too short" in built.describe()

    def test_describe(self) -> None:
        text = core("C-1", 3600.0).describe()
        assert "C-1" in text
        assert "L/D 2.00" in text
        assert "soaked" in text

    def test_reinforcement_is_flagged(self) -> None:
        assert (
            "contains reinforcement" in core("C-1", 3600.0, has_reinforcement=True).describe()
        )


class CaseInvestigation:
    def test_the_thresholds(self) -> None:
        found = investigate("Bay 4 slab", SPECIFIED, [core("C-1", 3600.0)])
        assert found.average_threshold == Quantity(3400, "psi")
        assert found.individual_threshold == Quantity(3000, "psi")
        assert AVERAGE_THRESHOLD.value == pytest.approx(85.0)
        assert INDIVIDUAL_THRESHOLD.value == pytest.approx(75.0)

    def test_an_adequate_set(self) -> None:
        found = investigate(
            "Bay 4 slab",
            SPECIFIED,
            [core("C-1", 3600.0), core("C-2", 3700.0), core("C-3", 3500.0)],
        )
        assert found.is_adequate
        assert found.findings() == ()

    def test_a_set_that_averages_low(self) -> None:
        found = investigate(
            "Bay 4 slab",
            SPECIFIED,
            [core("C-1", 3300.0), core("C-2", 3200.0), core("C-3", 3400.0)],
        )
        assert not found.is_adequate
        assert any("the average is" in finding for finding in found.findings())

    def test_a_good_average_with_one_low_core_still_fails(self) -> None:
        found = investigate(
            "Bay 4 slab",
            SPECIFIED,
            [core("C-1", 4200.0), core("C-2", 4200.0), core("C-3", 2800.0)],
        )
        assert found.average > found.average_threshold
        assert not found.is_adequate
        assert any("the lowest core is" in finding for finding in found.findings())

    def test_too_few_cores(self) -> None:
        found = investigate("Bay 4 slab", SPECIFIED, [core("C-1", 3600.0)])
        assert not found.has_enough_cores
        assert not found.is_adequate
        assert any("of 3 cores" in finding for finding in found.findings())

    def test_an_untestable_core_does_not_count(self) -> None:
        short = Core("C-3", Quantity(4, "in"), Quantity(3, "in"), Quantity(40000, "lbf"))
        found = investigate(
            "Bay 4 slab", SPECIFIED, [core("C-1", 3600.0), core("C-2", 3700.0), short]
        )
        assert len(found.testable) == 2
        assert not found.has_enough_cores

    def test_a_set_with_nothing_testable(self) -> None:
        short = Core("C-1", Quantity(4, "in"), Quantity(3, "in"), Quantity(40000, "lbf"))
        found = investigate("Bay 4 slab", SPECIFIED, [short])
        with pytest.raises(ValidationError, match="no core in this set"):
            _ = found.average
        with pytest.raises(ValidationError, match="no core in this set"):
            _ = found.lowest

    def test_reinforcement_and_conditioning_are_reported(self) -> None:
        found = investigate(
            "Bay 4 slab",
            SPECIFIED,
            [
                core("C-1", 3600.0, has_reinforcement=True),
                core("C-2", 3700.0, condition=CoreCondition.AS_RECEIVED),
                core("C-3", 3500.0),
            ],
        )
        findings = found.findings()
        assert any("contains reinforcement" in finding for finding in findings)
        assert any("was tested as received" in finding for finding in findings)

    def test_the_inputs_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            CoreInvestigation("Bay 4", Quantity(4000, "lb"), (core("C-1", 3600.0),))
        with pytest.raises(ValidationError, match="has to be positive"):
            CoreInvestigation("Bay 4", Quantity(0, "psi"), (core("C-1", 3600.0),))
        with pytest.raises(ValidationError, match="at least one core"):
            CoreInvestigation("Bay 4", SPECIFIED, ())

    def test_describe(self) -> None:
        found = investigate(
            "Bay 4 slab",
            SPECIFIED,
            [core("C-1", 3600.0), core("C-2", 3700.0), core("C-3", 3500.0)],
        )
        text = found.describe()
        assert "Bay 4 slab against 4000 psi: adequate" in text
        assert "C-1" in text
