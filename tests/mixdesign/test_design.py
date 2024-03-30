from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import COMMON_TEST_AGES, MixDesign, default_slump_band
from slumpcone.mixdesign.proportions import Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def rate(value: float) -> MassPerVolume:
    return MassPerVolume(value, "lb", "yd3")


def proportions(air: float = 6.0) -> Proportions:
    return Proportions(
        (
            Charge("CEM-I", MaterialClass.CEMENT, rate(470)),
            Charge("SCM-F", MaterialClass.SCM, rate(94)),
            Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1780)),
            Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1255)),
            Charge("W-1", MaterialClass.WATER, rate(254)),
        ),
        design_air=Percent(air),
    )


def design(**overrides: object) -> MixDesign:
    fields: dict[str, object] = {
        "code": "4000P-57",
        "name": "4000 psi paving mix",
        "proportions": proportions(),
        "specified_strength": Quantity(4000, "psi"),
        "nominal_max_size": Quantity(1.0, "in"),
        "slump_target": Quantity(4.0, "in"),
        "exposure": ExposureSet.parse("F2 S1"),
    }
    fields.update(overrides)
    return MixDesign(**fields)  # type: ignore[arg-type]


class CaseDefaultSlumpBand:
    def test_a_low_slump_gets_an_inch(self) -> None:
        band = default_slump_band(Quantity(3.0, "in"))
        assert band.low == pytest.approx(2.0)
        assert band.high == pytest.approx(4.0)

    def test_a_higher_slump_gets_an_inch_and_a_half(self) -> None:
        band = default_slump_band(Quantity(5.0, "in"))
        assert band.low == pytest.approx(3.5)
        assert band.high == pytest.approx(6.5)

    def test_the_common_ages_are_the_ones_people_specify(self) -> None:
        assert 28 in COMMON_TEST_AGES
        assert 56 in COMMON_TEST_AGES


class CaseConstruction:
    def test_code_and_name_are_normalised(self) -> None:
        built = design(code=" 4000p 57 ", name="  4000 psi   paving mix ")
        assert built.code == "4000P-57"
        assert built.name == "4000 psi paving mix"

    def test_plant_code_is_normalised(self) -> None:
        assert design(plant_code="pl 1").plant_code == "PL-1"

    def test_strength_has_to_be_a_pressure(self) -> None:
        with pytest.raises(ValidationError, match="specified strength is a pressure"):
            design(specified_strength=Quantity(4000, "lb"))

    def test_strength_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            design(specified_strength=Quantity(0, "psi"))

    def test_nominal_size_has_to_be_a_length(self) -> None:
        with pytest.raises(ValidationError, match="nominal maximum size is a length"):
            design(nominal_max_size=Quantity(1, "lb"))

    def test_nominal_size_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            design(nominal_max_size=Quantity(0, "in"))

    def test_slump_has_to_be_a_length(self) -> None:
        with pytest.raises(ValidationError, match="slump is a length"):
            design(slump_target=Quantity(4, "lb"))

    def test_a_negative_slump_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            design(slump_target=Quantity(-1, "in"))

    def test_test_age_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="test age has to be positive"):
            design(test_age_days=0)

    def test_revision_starts_at_one(self) -> None:
        with pytest.raises(ValidationError, match="revision number starts at one"):
            design(revision=0)


class CaseDefaults:
    def test_the_slump_band_is_filled_in(self) -> None:
        assert design().slump_tolerance().high == pytest.approx(5.5)

    def test_an_explicit_slump_band_is_kept(self) -> None:
        band = Band.at_most(5.0)
        assert design(slump_band=band).slump_tolerance() is band

    def test_an_air_band_follows_the_design_air(self) -> None:
        band = design().air_tolerance()
        assert band is not None
        assert band.low == pytest.approx(4.5)
        assert band.high == pytest.approx(7.5)

    def test_a_mix_with_no_design_air_gets_no_band(self) -> None:
        assert design(proportions=proportions(air=0.0)).air_tolerance() is None

    def test_an_explicit_air_band_is_kept(self) -> None:
        band = Band.between(5.0, 8.0)
        assert design(air_band=band).air_tolerance() is band


class CaseDerived:
    def test_identity_carries_the_revision(self) -> None:
        assert design().identity == "4000P-57 r1"

    def test_ratio_and_cementitious(self) -> None:
        assert design().water_cementitious_ratio == pytest.approx(0.4504, abs=1e-4)
        assert design().cementitious == Quantity(564, "lb")

    def test_air_entrainment_flag(self) -> None:
        assert design().is_air_entrained
        assert not design(proportions=proportions(air=0.0)).is_air_entrained

    def test_design_air(self) -> None:
        assert design().design_air == Percent(6.0)

    def test_describe(self) -> None:
        line = design().describe()
        assert "4000P-57 r1" in line
        assert "4000 psi at 28 d" in line
        assert "w/cm 0.450" in line
        assert "F2 S1 W0 C0" in line


class CaseRevision:
    def test_revise_bumps_the_number(self) -> None:
        revised = design().revise(proportions(air=5.0))
        assert revised.revision == 2
        assert revised.identity == "4000P-57 r2"

    def test_revise_keeps_everything_else(self) -> None:
        revised = design().revise(proportions(air=5.0))
        assert revised.specified_strength == design().specified_strength
        assert revised.exposure == design().exposure

    def test_revise_takes_a_note(self) -> None:
        assert design().revise(proportions(), notes="sand FM moved").notes == "sand FM moved"

    def test_revise_keeps_the_old_note_when_none_is_given(self) -> None:
        assert design(notes="original").revise(proportions()).notes == "original"
