from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import MaterialClass
from slumpcone.materials.spec import Material
from slumpcone.mixdesign.chloride import check_chloride, chloride_content
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from tests.factories import (
    air_entrainer,
    cement,
    coarse,
    design,
    fine,
    fly_ash,
    proportions,
    water,
    water_reducer,
)


def assayed(**assays: float) -> MaterialCatalog:
    """The usual catalogue with chloride figures on the named materials."""
    from dataclasses import replace

    stock = MaterialCatalog()
    for material in (
        cement(),
        fly_ash(),
        coarse(),
        fine(),
        water(),
        air_entrainer(),
        water_reducer(),
    ):
        value = assays.get(material.code.replace("-", "_"))
        stock.add(
            material if value is None else replace(material, chloride_content=Percent(value))
        )
    return stock


FULLY = {"CEM_I": 0.010, "SCM_F": 0.005, "CA_57": 0.002, "FA_1": 0.004}


class CaseContributions:
    def test_every_charge_gets_one(self) -> None:
        result = chloride_content(proportions(), assayed(**FULLY))
        assert len(result.contributions) == 5

    def test_an_assayed_ingredient_contributes(self) -> None:
        result = chloride_content(proportions(), assayed(**FULLY))
        stone = next(c for c in result.contributions if c.material_code == "CA-57")
        assert stone.is_assayed
        assert stone.chloride.value == pytest.approx(1780 * 0.00002, abs=1e-6)

    def test_an_unassayed_ingredient_contributes_nothing(self) -> None:
        result = chloride_content(proportions(), assayed())
        assert result.total.is_zero()

    def test_which_classes_matter(self) -> None:
        result = chloride_content(proportions(), assayed(**FULLY))
        water_line = next(c for c in result.contributions if c.material_code == "W-1")
        assert not water_line.matters
        cement_line = next(c for c in result.contributions if c.material_code == "CEM-I")
        assert cement_line.matters

    def test_describe(self) -> None:
        result = chloride_content(proportions(), assayed(**FULLY))
        text = result.contributions[0].describe()
        assert "CEM-I" in text
        assert "0.010%" in text

    def test_describe_without_an_assay(self) -> None:
        result = chloride_content(proportions(), assayed())
        assert "not assayed" in result.contributions[0].describe()


class CaseContent:
    def test_the_total_and_the_share(self) -> None:
        result = chloride_content(proportions(), assayed(**FULLY))
        assert result.total.value == pytest.approx(0.1375, abs=1e-3)
        assert result.content.value == pytest.approx(0.0244, abs=1e-3)

    def test_more_binder_lowers_the_content_without_removing_chloride(self) -> None:
        lean = chloride_content(proportions(), assayed(**FULLY))
        rich = chloride_content(proportions(cementitious=800.0, sand=1100.0), assayed(**FULLY))
        assert rich.content < lean.content

    def test_completeness(self) -> None:
        assert chloride_content(proportions(), assayed(**FULLY)).is_complete
        partial = chloride_content(proportions(), assayed(CEM_I=0.010, SCM_F=0.005, FA_1=0.004))
        assert not partial.is_complete
        assert partial.unassayed == ("CA-57",)

    def test_water_with_no_assay_does_not_spoil_it(self) -> None:
        assert chloride_content(proportions(), assayed(**FULLY)).is_complete

    def test_describe(self) -> None:
        text = chloride_content(proportions(), assayed(**FULLY)).describe()
        assert "of the binder" in text
        assert "incomplete" not in text

    def test_describe_when_incomplete(self) -> None:
        text = chloride_content(proportions(), assayed(CEM_I=0.010)).describe()
        assert "incomplete" in text
        assert "CA-57" in text

    def test_a_mixture_with_no_binder_has_no_content(self) -> None:
        from slumpcone.mixdesign.proportions import Charge, Proportions
        from slumpcone.units.rate import MassPerVolume

        stock = assayed(**FULLY)
        odd = Proportions(
            (
                Charge("CEM-I", MaterialClass.CEMENT, MassPerVolume(0, "lb", "yd3")),
                Charge("W-1", MaterialClass.WATER, MassPerVolume(250, "lb", "yd3")),
            )
        )
        with pytest.raises(ValidationError, match="no chloride content"):
            _ = chloride_content(odd, stock).content


class CaseCheck:
    def test_a_clean_design(self) -> None:
        assert check_chloride(design(exposure=ExposureSet.parse("C1")), assayed(**FULLY)) == ()

    def test_an_incomplete_assay_is_a_finding(self) -> None:
        findings = check_chloride(design(exposure=ExposureSet.parse("C1")), assayed())
        assert any("no chloride assay" in finding for finding in findings)

    def test_over_the_limit(self) -> None:
        heavy = {"CEM_I": 1.5, "SCM_F": 1.5, "CA_57": 0.5, "FA_1": 0.5}
        findings = check_chloride(design(exposure=ExposureSet.parse("C2")), assayed(**heavy))
        assert any("allows 0.15%" in finding for finding in findings)

    def test_no_corrosion_class_still_has_the_c0_limit(self) -> None:
        heavy = {"CEM_I": 5.0, "SCM_F": 5.0, "CA_57": 5.0, "FA_1": 5.0}
        findings = check_chloride(design(exposure=ExposureSet()), assayed(**heavy))
        assert any("allows 1.00%" in finding for finding in findings)

    def test_a_material_not_in_the_catalogue(self) -> None:
        stock = MaterialCatalog()
        stock.add(
            Material(
                "W-1",
                "Water",
                MaterialClass.WATER,
                water_source=water().water_source,
            )
        )
        with pytest.raises(Exception, match="CEM-I"):
            check_chloride(design(), stock)


def test_a_metric_mixture_gives_the_same_share() -> None:
    customary = chloride_content(proportions(), assayed(**FULLY)).content
    metric = chloride_content(proportions().scaled_to("kg", "m3"), assayed(**FULLY)).content
    assert metric.value == pytest.approx(customary.value, abs=1e-6)
