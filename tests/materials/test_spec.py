from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import (
    AdmixtureType,
    CementType,
    MaterialClass,
    ScmKind,
    WaterSource,
)
from slumpcone.materials.spec import Material
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


def cement(**overrides: object) -> Material:
    fields: dict[str, object] = {
        "code": "CEM-I",
        "name": "Ashfield Type I/II",
        "material_class": MaterialClass.CEMENT,
        "cement_type": CementType.TYPE_II,
        "specific_gravity": 3.15,
    }
    fields.update(overrides)
    return Material(**fields)  # type: ignore[arg-type]


def coarse(**overrides: object) -> Material:
    fields: dict[str, object] = {
        "code": "CA-57",
        "name": "Number 57 limestone",
        "material_class": MaterialClass.COARSE_AGGREGATE,
        "specific_gravity": 2.68,
        "absorption": Percent(0.7),
        "nominal_max_size": Quantity(1.0, "in"),
    }
    fields.update(overrides)
    return Material(**fields)  # type: ignore[arg-type]


def fine(**overrides: object) -> Material:
    fields: dict[str, object] = {
        "code": "FA-1",
        "name": "Concrete sand",
        "material_class": MaterialClass.FINE_AGGREGATE,
        "specific_gravity": 2.63,
        "absorption": Percent(1.4),
        "fineness_modulus": 2.75,
    }
    fields.update(overrides)
    return Material(**fields)  # type: ignore[arg-type]


class CaseNormalisation:
    def test_code_is_normalised(self) -> None:
        assert cement(code=" cem i ").code == "CEM-I"

    def test_name_whitespace_collapses(self) -> None:
        assert cement(name="  Ashfield   Type I/II ").name == "Ashfield Type I/II"


class CaseRequiredFields:
    def test_cement_needs_a_type(self) -> None:
        with pytest.raises(ValidationError, match="cement needs a type"):
            Material("CEM-I", "Ashfield", MaterialClass.CEMENT)

    def test_scm_needs_a_kind(self) -> None:
        with pytest.raises(ValidationError, match="scm needs a kind"):
            Material("FA-F", "Class F ash", MaterialClass.SCM)

    def test_admixture_needs_a_type(self) -> None:
        with pytest.raises(ValidationError, match="admixture needs a type"):
            Material("AD-1", "Water reducer", MaterialClass.ADMIXTURE)

    def test_water_needs_a_source(self) -> None:
        with pytest.raises(ValidationError, match="water needs a source"):
            Material("W-1", "City water", MaterialClass.WATER)

    def test_aggregate_needs_a_specific_gravity(self) -> None:
        with pytest.raises(ValidationError, match="bulk specific gravity"):
            Material(
                "CA-57",
                "Number 57",
                MaterialClass.COARSE_AGGREGATE,
                absorption=Percent(0.7),
                nominal_max_size=Quantity(1.0, "in"),
            )

    def test_aggregate_needs_an_absorption(self) -> None:
        with pytest.raises(ValidationError, match="absorption"):
            Material(
                "CA-57",
                "Number 57",
                MaterialClass.COARSE_AGGREGATE,
                specific_gravity=2.68,
                nominal_max_size=Quantity(1.0, "in"),
            )

    def test_fine_aggregate_needs_a_fineness_modulus(self) -> None:
        with pytest.raises(ValidationError, match="fineness modulus"):
            Material(
                "FA-1",
                "Sand",
                MaterialClass.FINE_AGGREGATE,
                specific_gravity=2.63,
                absorption=Percent(1.4),
            )

    def test_coarse_aggregate_needs_a_nominal_maximum_size(self) -> None:
        with pytest.raises(ValidationError, match="nominal maximum size"):
            Material(
                "CA-57",
                "Number 57",
                MaterialClass.COARSE_AGGREGATE,
                specific_gravity=2.68,
                absorption=Percent(0.7),
            )


class CaseForbiddenFields:
    def test_only_a_cement_carries_a_cement_type(self) -> None:
        with pytest.raises(ValidationError, match="only a cement"):
            coarse(cement_type=CementType.TYPE_I)

    def test_only_an_scm_carries_an_scm_kind(self) -> None:
        with pytest.raises(ValidationError, match="only an scm"):
            cement(scm_kind=ScmKind.FLY_ASH_F)

    def test_only_an_admixture_carries_an_admixture_type(self) -> None:
        with pytest.raises(ValidationError, match="only an admixture"):
            cement(admixture_type=AdmixtureType.TYPE_A_WATER_REDUCING)

    def test_only_water_carries_a_water_source(self) -> None:
        with pytest.raises(ValidationError, match="only water"):
            cement(water_source=WaterSource.POTABLE)

    def test_a_fineness_modulus_belongs_to_a_fine_aggregate(self) -> None:
        with pytest.raises(ValidationError, match="fine aggregate"):
            coarse(fineness_modulus=2.75)


class CaseRanges:
    @pytest.mark.parametrize("bad", [0.5, 6.0])
    def test_specific_gravity_range(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="specific gravity"):
            cement(specific_gravity=bad)

    @pytest.mark.parametrize("bad", [1.0, 5.0])
    def test_fineness_modulus_range(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="fineness modulus"):
            fine(fineness_modulus=bad)

    def test_absorption_range(self) -> None:
        with pytest.raises(ValidationError, match="absorption"):
            coarse(absorption=Percent(45.0))

    def test_solids_content_range(self) -> None:
        with pytest.raises(ValidationError, match="solids content"):
            Material(
                "AD-1",
                "Water reducer",
                MaterialClass.ADMIXTURE,
                admixture_type=AdmixtureType.TYPE_A_WATER_REDUCING,
                solids_content=Percent(0.0),
            )

    def test_nominal_maximum_size_is_positive(self) -> None:
        with pytest.raises(ValidationError, match="positive"):
            coarse(nominal_max_size=Quantity(0.0, "in"))


class CaseDerived:
    def test_cementitious_flag(self) -> None:
        assert cement().is_cementitious
        assert not coarse().is_cementitious

    def test_aggregate_flag(self) -> None:
        assert coarse().is_aggregate
        assert fine().is_aggregate
        assert not cement().is_aggregate

    def test_absolute_density_follows_the_specific_gravity(self) -> None:
        density = cement().absolute_density
        assert density.units == "lb/ft3"
        assert density.value == pytest.approx(196.65, abs=0.01)

    def test_absolute_density_needs_a_specific_gravity(self) -> None:
        water = Material(
            "W-1", "City water", MaterialClass.WATER, water_source=WaterSource.POTABLE
        )
        with pytest.raises(ValidationError, match="no absolute volume"):
            _ = water.absolute_density

    def test_describe_names_the_cement_type(self) -> None:
        assert "cement II" in cement().describe()

    def test_describe_names_the_scm_kind(self) -> None:
        ash = Material(
            "SCM-F",
            "Class F ash",
            MaterialClass.SCM,
            scm_kind=ScmKind.FLY_ASH_F,
            specific_gravity=2.35,
        )
        assert "fly_ash_f" in ash.describe()

    def test_describe_names_the_admixture_type(self) -> None:
        admix = Material(
            "AD-1",
            "Water reducer",
            MaterialClass.ADMIXTURE,
            admixture_type=AdmixtureType.TYPE_A_WATER_REDUCING,
        )
        assert "type_a" in admix.describe()

    def test_describe_falls_back_to_the_class(self) -> None:
        assert "coarse_aggregate" in coarse().describe()
