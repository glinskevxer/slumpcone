from __future__ import annotations

from dataclasses import replace

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import ScmKind
from slumpcone.mixdesign.alkali import (
    POTASSIUM_FACTOR,
    PreventionLevel,
    ReactivityClass,
    StructureClass,
    alkali_loading,
    check_alkali,
    prevention_level,
    scm_counts_toward_prevention,
    sodium_equivalent,
)
from slumpcone.percent import Percent
from tests.factories import cement, class_c_ash, coarse, fine, fly_ash, proportions, water


def stock(
    cement_alkali: float | None = 0.60, ash_alkali: float | None = 1.20
) -> MaterialCatalog:
    catalog = MaterialCatalog()
    catalog.add(
        cement()
        if cement_alkali is None
        else replace(cement(), alkali_content=Percent(cement_alkali))
    )
    for material in (fly_ash(), class_c_ash()):
        catalog.add(
            material
            if ash_alkali is None
            else replace(material, alkali_content=Percent(ash_alkali))
        )
    catalog.add_all([coarse(), fine(), water()])
    return catalog


class CaseClasses:
    def test_parse(self) -> None:
        assert ReactivityClass.parse("r2") is ReactivityClass.R2
        assert StructureClass.parse("S4") is StructureClass.S4

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="reactivity class"):
            ReactivityClass.parse("R9")
        with pytest.raises(ValidationError, match="structure class"):
            StructureClass.parse("S9")

    def test_r0_is_not_reactive(self) -> None:
        assert not ReactivityClass.R0.is_reactive
        assert ReactivityClass.R1.is_reactive

    def test_they_print_their_own_values(self) -> None:
        assert str(ReactivityClass.R2) == "R2"
        assert str(StructureClass.S3) == "S3"
        assert str(PreventionLevel.X) == "X"


class CasePreventionLevel:
    def test_a_non_reactive_aggregate_needs_nothing(self) -> None:
        for structure in StructureClass:
            assert prevention_level(ReactivityClass.R0, structure) is PreventionLevel.NONE

    def test_the_same_aggregate_in_a_bigger_structure(self) -> None:
        mild = prevention_level(ReactivityClass.R1, StructureClass.S1)
        severe = prevention_level(ReactivityClass.R1, StructureClass.S4)
        assert mild is PreventionLevel.NONE
        assert severe is PreventionLevel.X

    def test_a_more_reactive_aggregate_in_the_same_structure(self) -> None:
        assert prevention_level(ReactivityClass.R3, StructureClass.S1) is PreventionLevel.W

    def test_the_worst_corner(self) -> None:
        assert prevention_level(ReactivityClass.R3, StructureClass.S4) is PreventionLevel.Z

    def test_the_alkali_limits_tighten(self) -> None:
        limits = [
            PreventionLevel.V.alkali_limit,
            PreventionLevel.X.alkali_limit,
            PreventionLevel.Y.alkali_limit,
        ]
        values = [limit.value for limit in limits if limit is not None]
        assert values == sorted(values, reverse=True)

    def test_the_hardest_level_has_no_alkali_route(self) -> None:
        assert PreventionLevel.Z.alkali_limit is None
        assert PreventionLevel.Z.minimum_replacement == Percent(50.0)

    def test_replacement_rises_with_the_level(self) -> None:
        assert PreventionLevel.V.minimum_replacement == Percent(0.0)
        assert PreventionLevel.W.minimum_replacement == Percent(20.0)
        assert PreventionLevel.Y.minimum_replacement == Percent(35.0)


class CaseEquivalent:
    def test_the_factor(self) -> None:
        assert pytest.approx(0.658) == POTASSIUM_FACTOR

    def test_the_equivalent(self) -> None:
        assert sodium_equivalent(Percent(0.20), Percent(0.60)).value == pytest.approx(
            0.5948, abs=1e-4
        )

    def test_potassium_alone(self) -> None:
        assert sodium_equivalent(Percent(0.0), Percent(1.0)).value == pytest.approx(0.658)


class CaseLoading:
    def test_it_adds_up_the_cementitious_materials(self) -> None:
        loading = alkali_loading(proportions(), stock())
        assert loading.is_complete
        assert loading.total.value == pytest.approx(470 * 0.006 + 94 * 0.012, abs=1e-6)

    def test_aggregate_does_not_contribute(self) -> None:
        loading = alkali_loading(proportions(), stock())
        assert [code for code, _ in loading.per_material] == ["CEM-I", "SCM-F"]

    def test_a_missing_assay_is_reported(self) -> None:
        loading = alkali_loading(proportions(), stock(cement_alkali=None))
        assert not loading.is_complete
        assert loading.unassayed == ("CEM-I",)
        assert "incomplete" in loading.describe()

    def test_describe(self) -> None:
        assert "alkali loading is" in alkali_loading(proportions(), stock()).describe()


class CaseScmCredit:
    def test_class_c_ash_does_not_count(self) -> None:
        assert not scm_counts_toward_prevention(ScmKind.FLY_ASH_C)

    def test_everything_else_does(self) -> None:
        assert scm_counts_toward_prevention(ScmKind.FLY_ASH_F)
        assert scm_counts_toward_prevention(ScmKind.SLAG_120)


class CaseCheck:
    def test_a_non_reactive_aggregate_needs_nothing(self) -> None:
        assert check_alkali(proportions(), stock(), ReactivityClass.R0, StructureClass.S4) == ()

    def test_a_loading_inside_the_limit(self) -> None:
        findings = check_alkali(
            proportions(),
            stock(cement_alkali=0.30, ash_alkali=0.40),
            ReactivityClass.R1,
            StructureClass.S2,
        )
        assert findings == ()

    def test_a_loading_over_the_limit(self) -> None:
        findings = check_alkali(
            proportions(scm=0.0, cementitious=564.0),
            stock(cement_alkali=1.0),
            ReactivityClass.R2,
            StructureClass.S3,
        )
        assert any("alkali loading is" in finding for finding in findings)

    def test_a_missing_assay(self) -> None:
        findings = check_alkali(
            proportions(), stock(cement_alkali=None), ReactivityClass.R2, StructureClass.S3
        )
        assert any("no alkali assay" in finding for finding in findings)

    def test_too_little_replacement(self) -> None:
        findings = check_alkali(
            proportions(scm=50.0), stock(), ReactivityClass.R3, StructureClass.S4
        )
        assert any("needs 50% replacement" in finding for finding in findings)

    def test_class_c_ash_does_not_earn_the_credit(self) -> None:
        findings = check_alkali(
            proportions(scm=200.0, scm_code="SCM-C"),
            stock(),
            ReactivityClass.R3,
            StructureClass.S3,
        )
        assert any("that counts" in finding for finding in findings)

    def test_enough_class_f_ash_does(self) -> None:
        findings = check_alkali(
            proportions(scm=200.0, sand=1160.0),
            stock(cement_alkali=0.30, ash_alkali=0.20),
            ReactivityClass.R2,
            StructureClass.S2,
        )
        assert findings == ()


def test_the_alkali_field_survives_the_store() -> None:
    from slumpcone.store.db import Database
    from slumpcone.store.materials_repo import MaterialRepository
    from slumpcone.store.migrations import migrate

    database = Database.in_memory()
    migrate(database)
    repo = MaterialRepository(database)
    repo.save(replace(cement(), alkali_content=Percent(0.60)))
    assert repo.get("CEM-I").alkali_content == Percent(0.60)


def test_an_impossible_alkali_assay_is_refused() -> None:
    with pytest.raises(ValidationError, match="mill certificate"):
        replace(cement(), alkali_content=Percent(9.0))


def test_the_loading_scales_with_the_cement_content() -> None:
    lean = alkali_loading(proportions(cementitious=470.0, scm=0.0), stock()).total
    rich = alkali_loading(proportions(cementitious=750.0, scm=0.0), stock()).total
    assert rich > lean
    assert rich.to("lb").value == pytest.approx(750 * 0.006, abs=1e-6)


def test_a_quantity_limit_is_a_weight_per_unit_volume() -> None:
    limit = PreventionLevel.X.alkali_limit
    assert limit is not None
    assert limit.unit == "lb"
