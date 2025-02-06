from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import ScmKind
from slumpcone.mixdesign.masscrete import (
    MASS_THRESHOLD,
    MAX_DIFFERENTIAL,
    MAX_PEAK,
    RISE_PER_CWT,
    ThermalCheck,
    check_thermal,
    estimate_heat,
    heat_share,
    is_mass_concrete,
)
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature, TemperatureDelta
from tests.factories import catalog, proportions

PLACED = Temperature(70.0, "F")


class CaseHeatShare:
    def test_slag_gives_off_less(self) -> None:
        assert heat_share(ScmKind.SLAG_120) < 1.0

    def test_class_f_ash_gives_off_least(self) -> None:
        assert heat_share(ScmKind.FLY_ASH_F) < heat_share(ScmKind.FLY_ASH_C)

    def test_silica_fume_gives_off_more_than_cement(self) -> None:
        assert heat_share(ScmKind.SILICA_FUME) > 1.0

    def test_every_kind_has_a_share(self) -> None:
        for kind in ScmKind:
            assert heat_share(kind) > 0.0


class CaseMassConcrete:
    def test_a_slab_is_not_mass_concrete(self) -> None:
        assert not is_mass_concrete(Quantity(8, "in"))

    def test_a_footing_is(self) -> None:
        assert is_mass_concrete(Quantity(48, "in"))

    def test_the_threshold_itself(self) -> None:
        assert is_mass_concrete(MASS_THRESHOLD)
        assert Quantity(36, "in") == MASS_THRESHOLD

    def test_a_non_length_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a length"):
            is_mass_concrete(Quantity(48, "lb"))


class CaseEstimate:
    def test_a_plain_cement_mixture(self) -> None:
        plain = proportions(scm=0.0, cementitious=564.0)
        estimate = estimate_heat(plain, catalog())
        assert estimate.cement_equivalent == Quantity(564, "lb")
        assert estimate.rise.value == pytest.approx(564 / 100.0 * RISE_PER_CWT)

    def test_replacement_lowers_the_rise(self) -> None:
        plain = estimate_heat(proportions(scm=0.0), catalog()).rise
        blended = estimate_heat(proportions(scm=200.0), catalog()).rise
        assert blended < plain

    def test_slag_lowers_it_less_than_class_f_ash(self) -> None:
        ash = estimate_heat(proportions(scm=200.0, scm_code="SCM-F"), catalog()).rise
        slag = estimate_heat(proportions(scm=200.0, scm_code="SCM-SL"), catalog()).rise
        assert ash < slag

    def test_an_scm_that_is_not_in_the_catalogue_is_named(self) -> None:
        from slumpcone.materials.catalog import MaterialCatalog
        from tests.factories import cement, coarse, fine, water

        thin = MaterialCatalog()
        thin.add_all([cement(), coarse(), fine(), water()])
        with pytest.raises(Exception, match="SCM-F"):
            estimate_heat(proportions(), thin)

    def test_describe(self) -> None:
        text = estimate_heat(proportions(), catalog()).describe()
        assert "cement equivalent" in text
        assert "adiabatic rise" in text


class CasePeak:
    def test_the_peak_rises_from_the_placement_temperature(self) -> None:
        estimate = estimate_heat(proportions(scm=0.0), catalog())
        assert estimate.peak_from(PLACED) > PLACED

    def test_retaining_less_keeps_it_cooler(self) -> None:
        estimate = estimate_heat(proportions(scm=0.0), catalog())
        assert estimate.peak_from(PLACED, 0.5) < estimate.peak_from(PLACED, 1.0)

    def test_retaining_nothing_leaves_it_where_it_started(self) -> None:
        estimate = estimate_heat(proportions(), catalog())
        assert estimate.peak_from(PLACED, 0.0) == PLACED

    def test_a_silly_retained_share(self) -> None:
        estimate = estimate_heat(proportions(), catalog())
        with pytest.raises(ValidationError, match="between nothing and all"):
            estimate.peak_from(PLACED, 1.5)


class CaseThermalCheck:
    def test_a_cool_placement_passes(self) -> None:
        check = ThermalCheck(Temperature(120, "F"), Temperature(100, "F"))
        assert check.conforms
        assert check.binding_limit == "none"

    def test_a_hot_middle_fails_on_the_peak(self) -> None:
        check = ThermalCheck(Temperature(170, "F"), Temperature(150, "F"))
        assert check.peak_is_too_high
        assert check.binding_limit == "peak temperature"

    def test_a_cold_surface_fails_on_the_differential(self) -> None:
        check = ThermalCheck(Temperature(140, "F"), Temperature(80, "F"))
        assert check.differential_is_too_high
        assert check.binding_limit == "differential"

    def test_both_at_once(self) -> None:
        check = ThermalCheck(Temperature(180, "F"), Temperature(80, "F"))
        assert check.binding_limit == "both"
        assert not check.conforms

    def test_the_limits(self) -> None:
        assert MAX_PEAK.fahrenheit == pytest.approx(160.0)
        assert MAX_DIFFERENTIAL.value == pytest.approx(35.0)

    def test_the_limits_can_be_moved(self) -> None:
        check = ThermalCheck(
            Temperature(150, "F"),
            Temperature(100, "F"),
            max_peak=Temperature(140, "F"),
            max_differential=TemperatureDelta(60, "F"),
        )
        assert check.binding_limit == "peak temperature"

    def test_describe(self) -> None:
        text = ThermalCheck(Temperature(140, "F"), Temperature(80, "F")).describe()
        assert "peak 140 degF" in text
        assert "limit binding: differential" in text


class CaseWholeCheck:
    def test_a_heavy_replacement_mixture_passes_where_a_plain_one_does_not(self) -> None:
        hot_day = Temperature(110, "F")
        surface = Temperature(135, "F")
        plain = check_thermal(
            proportions(scm=0.0, cementitious=1000.0, sand=900.0),
            catalog(),
            hot_day,
            surface,
        )
        blended = check_thermal(
            proportions(scm=500.0, cementitious=1000.0, sand=900.0),
            catalog(),
            hot_day,
            surface,
        )
        assert not plain.conforms
        assert plain.binding_limit == "peak temperature"
        assert blended.conforms

    def test_retaining_less_helps(self) -> None:
        hot = check_thermal(
            proportions(scm=0.0, cementitious=1000.0, sand=900.0),
            catalog(),
            PLACED,
            Temperature(90, "F"),
        )
        cooler = check_thermal(
            proportions(scm=0.0, cementitious=1000.0, sand=900.0),
            catalog(),
            PLACED,
            Temperature(90, "F"),
            retained=0.4,
        )
        assert hot.peak > cooler.peak
