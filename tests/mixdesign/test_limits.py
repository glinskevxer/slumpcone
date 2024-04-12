from __future__ import annotations

import pytest

from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import CementType, MaterialClass, ScmKind
from slumpcone.materials.spec import Material
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.limits import (
    LimitFinding,
    check_air,
    check_closure,
    check_design,
    check_ratio,
    check_replacement,
    check_strength,
    check_sulfate_cement,
    is_conforming,
)
from slumpcone.mixdesign.proportions import Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def rate(value: float) -> MassPerVolume:
    return MassPerVolume(value, "lb", "yd3")


def catalog(cement_type: CementType = CementType.TYPE_II) -> MaterialCatalog:
    stock = MaterialCatalog()
    stock.add_all(
        [
            Material(
                "CEM-I",
                "Portland",
                MaterialClass.CEMENT,
                cement_type=cement_type,
                specific_gravity=3.15,
            ),
            Material(
                "SCM-F",
                "Class F ash",
                MaterialClass.SCM,
                scm_kind=ScmKind.FLY_ASH_F,
                specific_gravity=2.35,
            ),
            Material(
                "SCM-C",
                "Class C ash",
                MaterialClass.SCM,
                scm_kind=ScmKind.FLY_ASH_C,
                specific_gravity=2.60,
            ),
            Material(
                "SCM-SL",
                "Grade 120 slag",
                MaterialClass.SCM,
                scm_kind=ScmKind.SLAG_120,
                specific_gravity=2.90,
            ),
            Material(
                "CA-57",
                "Number 57",
                MaterialClass.COARSE_AGGREGATE,
                specific_gravity=2.68,
                absorption=Percent(0.7),
                nominal_max_size=Quantity(1.0, "in"),
            ),
            Material(
                "FA-1",
                "Sand",
                MaterialClass.FINE_AGGREGATE,
                specific_gravity=2.63,
                absorption=Percent(1.4),
                fineness_modulus=2.84,
            ),
            Material("W-1", "Water", MaterialClass.WATER, water_source=None)
            if False
            else Material(
                "W-1",
                "Water",
                MaterialClass.WATER,
                water_source=__import__(
                    "slumpcone.materials.kinds", fromlist=["WaterSource"]
                ).WaterSource.POTABLE,
            ),
        ]
    )
    return stock


def proportions(
    *, water: float = 250.0, ash: float = 94.0, ash_code: str = "SCM-F", air: float = 6.0
) -> Proportions:
    return Proportions(
        (
            Charge("CEM-I", MaterialClass.CEMENT, rate(564 - ash)),
            Charge(ash_code, MaterialClass.SCM, rate(ash)),
            Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1780)),
            Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1255)),
            Charge("W-1", MaterialClass.WATER, rate(water)),
        ),
        design_air=Percent(air),
    )


def design(**overrides: object) -> MixDesign:
    fields: dict[str, object] = {
        "code": "4000P-57",
        "name": "Paving mix",
        "proportions": proportions(),
        "specified_strength": Quantity(4500, "psi"),
        "nominal_max_size": Quantity(1.0, "in"),
        "slump_target": Quantity(4.0, "in"),
        "exposure": ExposureSet.parse("F2 S1"),
    }
    fields.update(overrides)
    return MixDesign(**fields)  # type: ignore[arg-type]


class CaseFinding:
    def test_describe_with_a_source(self) -> None:
        assert LimitFinding("A", "b", "F3").describe() == "A: b [F3]"

    def test_describe_without_one(self) -> None:
        assert str(LimitFinding("A", "b")) == "A: b"


class CaseRatio:
    def test_inside_the_limit(self) -> None:
        assert check_ratio(design()) == ()

    def test_above_the_limit_names_the_class(self) -> None:
        findings = check_ratio(design(proportions=proportions(water=300.0)))
        assert findings[0].code == "WCM_ABOVE_LIMIT"
        assert findings[0].governing == "F2"

    def test_no_limit_at_all(self) -> None:
        assert check_ratio(design(exposure=ExposureSet())) == ()


class CaseStrength:
    def test_at_the_floor(self) -> None:
        assert check_strength(design()) == ()

    def test_below_the_floor(self) -> None:
        findings = check_strength(design(specified_strength=Quantity(3000, "psi")))
        assert findings[0].code == "STRENGTH_BELOW_FLOOR"
        assert "4500 psi" in findings[0].detail


class CaseAir:
    def test_at_the_requirement(self) -> None:
        assert check_air(design()) == ()

    def test_below_the_requirement(self) -> None:
        findings = check_air(design(proportions=proportions(air=4.5)))
        assert findings[0].code == "AIR_BELOW_REQUIREMENT"

    def test_missing_entirely(self) -> None:
        findings = check_air(design(proportions=proportions(air=0.0)))
        assert findings[0].code == "AIR_MISSING"

    def test_no_freeze_thaw_class_means_no_requirement(self) -> None:
        assert (
            check_air(
                design(exposure=ExposureSet.parse("S1"), proportions=proportions(air=0.0))
            )
            == ()
        )


class CaseReplacement:
    def test_only_f3_caps_replacement(self) -> None:
        assert check_replacement(design(), catalog()) == ()

    def test_fly_ash_over_its_cap(self) -> None:
        heavy = design(exposure=ExposureSet.parse("F3"), proportions=proportions(ash=200.0))
        findings = check_replacement(heavy, catalog())
        assert findings[0].code == "REPLACEMENT_ABOVE_CAP"
        assert "fly_ash" in findings[0].detail

    def test_slag_has_a_looser_cap(self) -> None:
        slag = design(
            exposure=ExposureSet.parse("F3"),
            proportions=proportions(ash=200.0, ash_code="SCM-SL"),
        )
        assert check_replacement(slag, catalog()) == ()

    def test_the_total_cap_can_fire_on_its_own(self) -> None:
        both = Proportions(
            (
                Charge("CEM-I", MaterialClass.CEMENT, rate(264)),
                Charge("SCM-F", MaterialClass.SCM, rate(140)),
                Charge("SCM-SL", MaterialClass.SCM, rate(160)),
                Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1780)),
                Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1255)),
                Charge("W-1", MaterialClass.WATER, rate(254)),
            ),
            design_air=Percent(6.0),
        )
        findings = check_replacement(
            design(exposure=ExposureSet.parse("F3"), proportions=both), catalog()
        )
        assert any("total replacement" in f.detail for f in findings)


class CaseSulfate:
    def test_no_sulfate_class_means_no_check(self) -> None:
        assert check_sulfate_cement(design(exposure=ExposureSet()), catalog()) == ()

    def test_a_type_one_cement_in_a_sulfate_class(self) -> None:
        findings = check_sulfate_cement(design(), catalog(CementType.TYPE_I))
        assert findings[0].code == "CEMENT_NOT_SULFATE_RESISTING"

    def test_class_c_ash_in_a_sulfate_class(self) -> None:
        findings = check_sulfate_cement(
            design(proportions=proportions(ash_code="SCM-C")), catalog()
        )
        assert findings[0].code == "SCM_NOT_SULFATE_RESISTING"

    def test_a_conforming_system_passes(self) -> None:
        assert check_sulfate_cement(design(), catalog()) == ()


class CaseClosure:
    def test_a_closing_design(self) -> None:
        assert check_closure(design(), catalog()) == ()

    def test_a_short_design(self) -> None:
        short = Proportions(
            (
                Charge("CEM-I", MaterialClass.CEMENT, rate(470)),
                Charge("SCM-F", MaterialClass.SCM, rate(94)),
                Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1400)),
                Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1000)),
                Charge("W-1", MaterialClass.WATER, rate(254)),
            ),
            design_air=Percent(6.0),
        )
        findings = check_closure(design(proportions=short), catalog())
        assert findings[0].code == "YIELD_DOES_NOT_CLOSE"


class CaseWholeDesign:
    def test_a_conforming_design(self) -> None:
        assert check_design(design(), catalog()) == ()
        assert is_conforming(design(), catalog())

    def test_several_rules_at_once(self) -> None:
        broken = design(
            specified_strength=Quantity(3000, "psi"),
            proportions=proportions(water=320.0, air=3.0),
        )
        codes = [f.code for f in check_design(broken, catalog())]
        assert "WCM_ABOVE_LIMIT" in codes
        assert "STRENGTH_BELOW_FLOOR" in codes
        assert "AIR_BELOW_REQUIREMENT" in codes
        assert not is_conforming(broken, catalog())

    def test_a_half_inch_aggregate_takes_a_different_air_row(self) -> None:
        smaller = design(nominal_max_size=Quantity(0.5, "in"), proportions=proportions(air=6.0))
        assert check_air(smaller)[0].code == "AIR_BELOW_REQUIREMENT"

    def test_an_oversize_aggregate_falls_back_to_the_last_row(self) -> None:
        big = design(nominal_max_size=Quantity(4.0, "in"))
        assert check_air(big) == ()


@pytest.mark.parametrize("water", [200.0, 250.0])
def test_a_lower_ratio_never_produces_a_finding(water: float) -> None:
    assert check_ratio(design(proportions=proportions(water=water))) == ()
