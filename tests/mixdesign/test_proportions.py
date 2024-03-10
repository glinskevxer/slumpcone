from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def rate(value: float) -> MassPerVolume:
    return MassPerVolume(value, "lb", "yd3")


def charges() -> tuple[Charge, ...]:
    return (
        Charge("CEM-I", MaterialClass.CEMENT, rate(470)),
        Charge("SCM-F", MaterialClass.SCM, rate(94)),
        Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1780)),
        Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1240)),
        Charge("W-1", MaterialClass.WATER, rate(254)),
    )


def proportions(**overrides: object) -> Proportions:
    fields: dict[str, object] = {
        "charges": charges(),
        "admixtures": (
            AdmixtureCharge("AD-AE", Quantity(1.2, "floz")),
            AdmixtureCharge("AD-WR", Quantity(4.0, "floz")),
        ),
        "design_air": Percent(6.0),
    }
    fields.update(overrides)
    return Proportions(**fields)  # type: ignore[arg-type]


class CaseCharge:
    def test_code_is_normalised(self) -> None:
        assert Charge(" cem i ", MaterialClass.CEMENT, rate(470)).material_code == "CEM-I"

    def test_an_admixture_cannot_be_a_charge(self) -> None:
        with pytest.raises(ValidationError, match="dosed against the binder"):
            Charge("AD-1", MaterialClass.ADMIXTURE, rate(1))

    def test_a_negative_charge_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            Charge("CEM-I", MaterialClass.CEMENT, rate(-1))

    def test_for_volume(self) -> None:
        charge = Charge("CEM-I", MaterialClass.CEMENT, rate(470))
        assert charge.for_volume(Quantity(9, "yd3")) == Quantity(4230, "lb")

    def test_text(self) -> None:
        assert str(Charge("CEM-I", MaterialClass.CEMENT, rate(470))) == "CEM-I 470.0 lb/yd3"


class CaseAdmixtureCharge:
    def test_dose_has_to_be_a_volume(self) -> None:
        with pytest.raises(ValidationError, match="dose is a volume"):
            AdmixtureCharge("AD-1", Quantity(1, "lb"))

    def test_a_negative_dose_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            AdmixtureCharge("AD-1", Quantity(-1, "floz"))

    def test_the_charge_follows_the_binder(self) -> None:
        dose = AdmixtureCharge("AD-WR", Quantity(4.0, "floz"))
        assert dose.for_cementitious(Quantity(564, "lb")).value == pytest.approx(22.56)

    def test_cementitious_has_to_be_a_mass(self) -> None:
        with pytest.raises(ValidationError, match="content is a mass"):
            AdmixtureCharge("AD-1", Quantity(1, "floz")).for_cementitious(Quantity(1, "yd3"))

    def test_text(self) -> None:
        assert str(AdmixtureCharge("AD-WR", Quantity(4.0, "floz"))) == "AD-WR 4.0 floz/cwt"


class CaseConstruction:
    def test_no_charges_at_all(self) -> None:
        with pytest.raises(ValidationError, match="at least one charge"):
            Proportions(())

    def test_a_repeated_material(self) -> None:
        with pytest.raises(ValidationError, match="twice in the proportions"):
            Proportions((*charges(), charges()[0]))

    def test_a_repeated_admixture(self) -> None:
        dose = AdmixtureCharge("AD-AE", Quantity(1.2, "floz"))
        with pytest.raises(ValidationError, match="twice in the admixtures"):
            proportions(admixtures=(dose, dose))

    def test_mixed_volume_units_are_refused(self) -> None:
        odd = (*charges(), Charge("X", MaterialClass.FIBER, MassPerVolume(1, "lb", "m3")))
        with pytest.raises(ValidationError, match="same volume"):
            Proportions(odd)

    def test_no_water_line(self) -> None:
        with pytest.raises(ValidationError, match="water line"):
            Proportions(charges()[:4])

    def test_no_cementitious(self) -> None:
        with pytest.raises(ValidationError, match="cementitious material"):
            Proportions(charges()[2:])

    def test_a_silly_design_air(self) -> None:
        with pytest.raises(ValidationError, match="not a concrete"):
            proportions(design_air=Percent(45.0))


class CaseTotals:
    mix = proportions()

    def test_units(self) -> None:
        assert self.mix.mass_unit == "lb"
        assert self.mix.volume_unit == "yd3"

    def test_cementitious(self) -> None:
        assert self.mix.cementitious == rate(564)
        assert self.mix.cement == rate(470)
        assert self.mix.supplementary == rate(94)

    def test_water(self) -> None:
        assert self.mix.water == rate(254)

    def test_aggregates(self) -> None:
        assert self.mix.coarse_aggregate == rate(1780)
        assert self.mix.fine_aggregate == rate(1240)
        assert self.mix.total_aggregate == rate(3020)

    def test_water_cementitious_ratio(self) -> None:
        assert self.mix.water_cementitious_ratio == pytest.approx(0.4504, abs=1e-4)

    def test_replacement(self) -> None:
        assert self.mix.supplementary_replacement.value == pytest.approx(16.67, abs=0.01)

    def test_fine_fraction(self) -> None:
        assert self.mix.fine_aggregate_fraction.value == pytest.approx(41.06, abs=0.01)

    def test_charge_lookup(self) -> None:
        assert self.mix.charge("cem i").content == rate(470)

    def test_charge_lookup_names_what_is_missing(self) -> None:
        with pytest.raises(ValidationError, match="not in these proportions"):
            self.mix.charge("CEM-III")

    def test_of_class(self) -> None:
        assert len(self.mix.of_class(MaterialClass.CEMENT)) == 1

    def test_a_mix_with_no_sand_reports_a_zero_fraction(self) -> None:
        without_sand = Proportions(tuple(c for c in charges() if c.material_code != "FA-1"))
        assert without_sand.fine_aggregate_fraction == Percent(0.0)


class CaseScaling:
    mix = proportions()

    def test_batch_weights(self) -> None:
        weights = self.mix.batch_weights(Quantity(9, "yd3"))
        assert weights["CEM-I"] == Quantity(4230, "lb")
        assert weights["W-1"] == Quantity(2286, "lb")

    def test_admixture_charges_follow_the_binder(self) -> None:
        charges_out = self.mix.admixture_charges(Quantity(9, "yd3"))
        assert charges_out["AD-AE"].value == pytest.approx(60.912, abs=1e-3)
        assert charges_out["AD-WR"].value == pytest.approx(203.04, abs=1e-2)

    def test_scaled_to_metric(self) -> None:
        metric = self.mix.scaled_to("kg", "m3")
        assert metric.volume_unit == "m3"
        assert metric.cementitious.value == pytest.approx(334.61, abs=0.01)
        assert metric.water_cementitious_ratio == pytest.approx(
            self.mix.water_cementitious_ratio
        )
