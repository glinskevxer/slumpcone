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


class CaseMaterialClass:
    def test_cement_and_scm_are_cementitious(self) -> None:
        assert MaterialClass.CEMENT.is_cementitious
        assert MaterialClass.SCM.is_cementitious
        assert not MaterialClass.COARSE_AGGREGATE.is_cementitious

    def test_both_aggregates_are_aggregates(self) -> None:
        assert MaterialClass.COARSE_AGGREGATE.is_aggregate
        assert MaterialClass.FINE_AGGREGATE.is_aggregate
        assert not MaterialClass.CEMENT.is_aggregate

    def test_admixture_and_water_are_metered_not_weighed(self) -> None:
        assert not MaterialClass.ADMIXTURE.is_batched_by_weight
        assert not MaterialClass.WATER.is_batched_by_weight
        assert MaterialClass.FIBER.is_batched_by_weight

    @pytest.mark.parametrize("written", ["cement", "CEMENT", " Cement ", "CEMENT"])
    def test_parse(self, written: str) -> None:
        assert MaterialClass.parse(written) is MaterialClass.CEMENT

    def test_parse_folds_separators(self) -> None:
        assert MaterialClass.parse("coarse aggregate") is MaterialClass.COARSE_AGGREGATE
        assert MaterialClass.parse("coarse-aggregate") is MaterialClass.COARSE_AGGREGATE

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="material class"):
            MaterialClass.parse("gravel-ish")

    def test_prints_its_own_value(self) -> None:
        assert str(MaterialClass.SCM) == "scm"


class CaseCementType:
    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("I", CementType.TYPE_I),
            ("Type I", CementType.TYPE_I),
            ("type v", CementType.TYPE_V),
            ("II/V", CementType.TYPE_II_V),
            ("IL", CementType.TYPE_IL),
            ("TYPE_III", CementType.TYPE_III),
        ],
    )
    def test_parse(self, written: str, expected: CementType) -> None:
        assert CementType.parse(written) is expected

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="cement type"):
            CementType.parse("Type IX")

    def test_blended_cements_are_c595(self) -> None:
        assert CementType.TYPE_IL.standard == "ASTM C595"
        assert CementType.TYPE_IL.is_blended
        assert CementType.TYPE_I.standard == "ASTM C150"
        assert not CementType.TYPE_I.is_blended

    def test_the_a_suffix_carries_air(self) -> None:
        assert CementType.TYPE_IA.is_air_entraining
        assert CementType.TYPE_IIIA.is_air_entraining
        assert not CementType.TYPE_III.is_air_entraining

    def test_sulfate_resisting_types(self) -> None:
        assert CementType.TYPE_V.is_sulfate_resisting
        assert CementType.TYPE_II.is_sulfate_resisting
        assert not CementType.TYPE_I.is_sulfate_resisting

    def test_high_early_types(self) -> None:
        assert CementType.TYPE_III.is_high_early
        assert not CementType.TYPE_I.is_high_early

    def test_prints_the_type_letter(self) -> None:
        assert str(CementType.TYPE_II_V) == "II/V"


class CaseScmKind:
    def test_standards(self) -> None:
        assert ScmKind.FLY_ASH_F.standard == "ASTM C618"
        assert ScmKind.SLAG_120.standard == "ASTM C989"
        assert ScmKind.SILICA_FUME.standard == "ASTM C1240"

    def test_families(self) -> None:
        assert ScmKind.FLY_ASH_C.is_fly_ash
        assert not ScmKind.SLAG_100.is_fly_ash
        assert ScmKind.SLAG_100.is_slag
        assert not ScmKind.SILICA_FUME.is_slag

    def test_class_c_ash_does_not_help_sulfate_resistance(self) -> None:
        assert not ScmKind.FLY_ASH_C.helps_sulfate_resistance
        assert ScmKind.FLY_ASH_F.helps_sulfate_resistance
        assert ScmKind.SLAG_120.helps_sulfate_resistance

    def test_parse(self) -> None:
        assert ScmKind.parse("fly ash f") is ScmKind.FLY_ASH_F
        assert ScmKind.parse("SILICA_FUME") is ScmKind.SILICA_FUME

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="scm kind"):
            ScmKind.parse("rice husk")


class CaseAdmixtureType:
    def test_standards(self) -> None:
        assert AdmixtureType.AIR_ENTRAINING.standard == "ASTM C260"
        assert AdmixtureType.TYPE_A_WATER_REDUCING.standard == "ASTM C494"
        assert AdmixtureType.TYPE_F_HIGH_RANGE.standard == "ASTM C494"
        assert AdmixtureType.HYDRATION_STABILIZING.standard == "ASTM C1798"

    def test_retarders(self) -> None:
        assert AdmixtureType.TYPE_B_RETARDING.retards_set
        assert AdmixtureType.TYPE_D_WATER_REDUCING_RETARDING.retards_set
        assert AdmixtureType.TYPE_G_HIGH_RANGE_RETARDING.retards_set
        assert AdmixtureType.HYDRATION_STABILIZING.retards_set
        assert not AdmixtureType.TYPE_A_WATER_REDUCING.retards_set

    def test_accelerators(self) -> None:
        assert AdmixtureType.TYPE_C_ACCELERATING.accelerates_set
        assert AdmixtureType.TYPE_E_WATER_REDUCING_ACCELERATING.accelerates_set
        assert not AdmixtureType.TYPE_B_RETARDING.accelerates_set

    def test_water_reducers(self) -> None:
        assert AdmixtureType.TYPE_A_WATER_REDUCING.reduces_water
        assert AdmixtureType.TYPE_G_HIGH_RANGE_RETARDING.reduces_water
        assert not AdmixtureType.AIR_ENTRAINING.reduces_water

    def test_high_range(self) -> None:
        assert AdmixtureType.TYPE_F_HIGH_RANGE.is_high_range
        assert not AdmixtureType.TYPE_A_WATER_REDUCING.is_high_range

    def test_parse(self) -> None:
        assert AdmixtureType.parse("type f") is AdmixtureType.TYPE_F_HIGH_RANGE
        assert AdmixtureType.parse("air entraining") is AdmixtureType.AIR_ENTRAINING

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="admixture type"):
            AdmixtureType.parse("type z")


class CaseWaterSource:
    def test_potable_needs_no_qualification(self) -> None:
        assert not WaterSource.POTABLE.needs_qualification
        assert WaterSource.RECLAIMED.needs_qualification
        assert WaterSource.NON_POTABLE.needs_qualification

    def test_recycled_sources_carry_solids(self) -> None:
        assert WaterSource.RECLAIMED.carries_solids
        assert WaterSource.WASH_WATER.carries_solids
        assert not WaterSource.POTABLE.carries_solids

    def test_parse(self) -> None:
        assert WaterSource.parse("wash water") is WaterSource.WASH_WATER

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="water source"):
            WaterSource.parse("seawater")
