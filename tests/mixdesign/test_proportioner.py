from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.proportioner import ProportioningRequest, proportion
from slumpcone.mixdesign.tables import ExposureSeverity
from slumpcone.mixdesign.volumes import check_yield
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from tests.factories import cement, coarse, fine, fly_ash, gravities, water


def request_for(**overrides: object) -> ProportioningRequest:
    fields: dict[str, object] = {
        "required_average_strength": Quantity(4800, "psi"),
        "slump_target": Quantity(4.0, "in"),
        "cement": cement(),
        "coarse": coarse(),
        "fine": fine(),
        "water": water(),
        "air_entrained": True,
        "severity": ExposureSeverity.MODERATE,
    }
    fields.update(overrides)
    return ProportioningRequest(**fields)  # type: ignore[arg-type]


class CaseRequest:
    def test_the_classes_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="not a coarse aggregate"):
            request_for(coarse=fine())
        with pytest.raises(ValidationError, match="not a fine aggregate"):
            request_for(fine=coarse())
        with pytest.raises(ValidationError, match="not a cement"):
            request_for(cement=fly_ash())
        with pytest.raises(ValidationError, match="not an scm"):
            request_for(scm=cement())

    def test_the_coarse_aggregate_needs_a_dry_rodded_weight(self) -> None:
        bare = coarse()
        stripped = type(bare)(
            bare.code,
            bare.name,
            MaterialClass.COARSE_AGGREGATE,
            specific_gravity=bare.specific_gravity,
            absorption=bare.absorption,
            nominal_max_size=bare.nominal_max_size,
        )
        with pytest.raises(ValidationError, match="dry rodded unit weight"):
            request_for(coarse=stripped)

    def test_a_replacement_with_no_scm_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no scm"):
            request_for(scm_replacement=Percent(20.0))

    def test_a_silly_replacement_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="share of the binder"):
            request_for(scm=fly_ash(), scm_replacement=Percent(120.0))


class CaseProportion:
    def test_it_produces_a_usable_mixture(self) -> None:
        result = proportion(request_for())
        codes = [charge.material_code for charge in result.proportions.charges]
        assert codes == ["CEM-I", "CA-57", "FA-1", "W-1"]

    def test_the_mixture_closes_on_a_cubic_yard(self) -> None:
        result = proportion(request_for())
        assert check_yield(result.proportions, gravities()).conforms

    def test_the_water_comes_off_the_table(self) -> None:
        result = proportion(request_for())
        assert result.proportions.water.value == pytest.approx(295.0)

    def test_the_ratio_comes_off_the_strength_table(self) -> None:
        result = proportion(request_for())
        assert result.water_cementitious == pytest.approx(0.416, abs=1e-3)

    def test_the_air_comes_off_the_severity(self) -> None:
        assert proportion(request_for()).air == Percent(4.5)

    def test_a_plain_mixture_takes_the_entrapped_air(self) -> None:
        result = proportion(request_for(air_entrained=False))
        assert result.air == Percent(1.5)

    def test_a_specification_limit_can_tighten_the_ratio(self) -> None:
        result = proportion(request_for(max_water_cementitious=0.35))
        assert result.water_cementitious == pytest.approx(0.35)
        assert any("governs" in step for step in result.steps)

    def test_a_looser_specification_limit_does_nothing(self) -> None:
        loose = proportion(request_for(max_water_cementitious=0.60))
        plain = proportion(request_for())
        assert loose.water_cementitious == pytest.approx(plain.water_cementitious)

    def test_a_cementitious_floor_drops_the_ratio(self) -> None:
        result = proportion(request_for(min_cementitious=Quantity(900, "lb")))
        assert result.proportions.cementitious.value == pytest.approx(900.0)
        assert result.water_cementitious < 0.416
        assert any("floor raises the content" in step for step in result.steps)

    def test_a_low_floor_changes_nothing(self) -> None:
        result = proportion(request_for(min_cementitious=Quantity(400, "lb")))
        assert result.water_cementitious == pytest.approx(0.416, abs=1e-3)


class CaseReplacement:
    def test_an_scm_splits_the_binder(self) -> None:
        result = proportion(request_for(scm=fly_ash(), scm_replacement=Percent(20.0)))
        codes = [charge.material_code for charge in result.proportions.charges]
        assert codes == ["CEM-I", "SCM-F", "CA-57", "FA-1", "W-1"]
        assert result.proportions.supplementary_replacement.value == pytest.approx(20.0)

    def test_the_total_binder_is_unchanged(self) -> None:
        plain = proportion(request_for())
        blended = proportion(request_for(scm=fly_ash(), scm_replacement=Percent(20.0)))
        assert blended.proportions.cementitious.value == pytest.approx(
            plain.proportions.cementitious.value
        )

    def test_a_blended_mixture_still_closes(self) -> None:
        result = proportion(request_for(scm=fly_ash(), scm_replacement=Percent(25.0)))
        assert check_yield(result.proportions, gravities()).conforms

    def test_a_zero_replacement_leaves_the_scm_out(self) -> None:
        result = proportion(request_for(scm=fly_ash(), scm_replacement=Percent(0.0)))
        codes = [charge.material_code for charge in result.proportions.charges]
        assert "SCM-F" not in codes


class CaseWorking:
    def test_the_steps_read_in_order(self) -> None:
        steps = proportion(request_for()).steps
        assert "water demand" in steps[0]
        assert "air is" in steps[1]
        assert "ratio from strength" in steps[2]
        assert "sand fills the remaining" in steps[-1]

    def test_describe_joins_them(self) -> None:
        text = proportion(request_for()).describe()
        assert text.count("\n") >= 4

    def test_an_over_full_mixture_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="over full before any sand"):
            proportion(
                request_for(
                    required_average_strength=Quantity(2000, "psi"),
                    min_cementitious=Quantity(2600, "lb"),
                )
            )
