from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import NotFoundError, RuleViolationError, ValidationError
from slumpcone.materials.kinds import MaterialClass, WaterSource
from slumpcone.plant.plant import MixingMethod, Plant
from slumpcone.plant.scale import Scale
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem

DAY = date(2024, 5, 1)


def agg_scale(code: str = "SC-AGG", capacity: float = 12000.0) -> Scale:
    return Scale(
        code,
        "Aggregate hopper scale",
        Quantity(capacity, "lb"),
        Quantity(2, "lb"),
        (MaterialClass.COARSE_AGGREGATE, MaterialClass.FINE_AGGREGATE),
        date(2024, 3, 1),
    )


def cement_scale() -> Scale:
    return Scale(
        "SC-CEM",
        "Cement hopper scale",
        Quantity(6000, "lb"),
        Quantity(1, "lb"),
        (MaterialClass.CEMENT, MaterialClass.SCM),
        date(2024, 3, 1),
    )


def plant(**overrides: object) -> Plant:
    fields: dict[str, object] = {
        "code": "PL-1",
        "name": "Northmoor batch plant",
        "scales": (agg_scale(), cement_scale()),
        "max_load": Quantity(11, "yd3"),
    }
    fields.update(overrides)
    return Plant(**fields)  # type: ignore[arg-type]


class CaseMixingMethod:
    def test_parse(self) -> None:
        assert MixingMethod.parse("central mixed") is MixingMethod.CENTRAL_MIXED
        assert MixingMethod.parse("TRUCK-MIXED") is MixingMethod.TRUCK_MIXED

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="mixing method"):
            MixingMethod.parse("hand mixed")

    def test_central_mixing_does_not_happen_in_the_drum(self) -> None:
        assert not MixingMethod.CENTRAL_MIXED.mixes_in_the_drum
        assert MixingMethod.TRUCK_MIXED.mixes_in_the_drum
        assert MixingMethod.SHRINK_MIXED.mixes_in_the_drum

    def test_required_revolutions(self) -> None:
        assert MixingMethod.TRUCK_MIXED.required_mixing_revolutions == 70
        assert MixingMethod.SHRINK_MIXED.required_mixing_revolutions == 30
        assert MixingMethod.CENTRAL_MIXED.required_mixing_revolutions == 0

    def test_prints_its_own_value(self) -> None:
        assert str(MixingMethod.SHRINK_MIXED) == "shrink_mixed"


class CaseConstruction:
    def test_defaults(self) -> None:
        built = Plant("PL-1", "Northmoor")
        assert built.unit_system is UnitSystem.CUSTOMARY
        assert built.mixing_method is MixingMethod.TRUCK_MIXED
        assert built.water_source is WaterSource.POTABLE
        assert built.scales == ()

    def test_code_and_name_are_normalised(self) -> None:
        built = plant(code=" pl 1 ", name="  Northmoor   batch plant ", location="  Ashfield ")
        assert built.code == "PL-1"
        assert built.name == "Northmoor batch plant"
        assert built.location == "Ashfield"

    def test_a_repeated_scale_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="appears twice"):
            plant(scales=(agg_scale(), agg_scale()))

    def test_max_load_has_to_be_a_volume(self) -> None:
        with pytest.raises(ValidationError, match="load size is a volume"):
            plant(max_load=Quantity(11, "lb"))

    def test_max_load_has_to_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            plant(max_load=Quantity(0, "yd3"))


class CaseScales:
    def test_scale_codes_are_sorted(self) -> None:
        assert plant().scale_codes == ("SC-AGG", "SC-CEM")

    def test_scale_by_code(self) -> None:
        assert plant().scale("sc cem").code == "SC-CEM"

    def test_an_unknown_scale_is_named(self) -> None:
        with pytest.raises(NotFoundError, match="SC-WATER"):
            plant().scale("SC-WATER")

    def test_scale_for_a_class(self) -> None:
        assert plant().scale_for(MaterialClass.CEMENT).code == "SC-CEM"

    def test_the_smallest_capable_scale_wins(self) -> None:
        built = plant(scales=(agg_scale(), agg_scale("SC-AGG2", 6000.0)))
        assert built.scale_for(MaterialClass.COARSE_AGGREGATE).code == "SC-AGG2"

    def test_no_scale_for_a_class(self) -> None:
        with pytest.raises(NotFoundError, match="admixture"):
            plant().scale_for(MaterialClass.ADMIXTURE)

    def test_has_scale_for(self) -> None:
        assert plant().has_scale_for(MaterialClass.SCM)
        assert not plant().has_scale_for(MaterialClass.ADMIXTURE)


class CaseOperability:
    def test_a_plant_with_current_scales_can_run(self) -> None:
        assert plant().is_operable(DAY)
        assert plant().blocking_reasons(DAY) == ()
        plant().require_operable(DAY)

    def test_an_overdue_scale_stops_it(self) -> None:
        late = date(2024, 10, 1)
        assert plant().overdue_scales(late) != ()
        assert not plant().is_operable(late)
        with pytest.raises(RuleViolationError) as caught:
            plant().require_operable(late)
        assert caught.value.code == "PLANT_NOT_OPERABLE"
        assert "SC-AGG" in caught.value.detail

    def test_an_expired_plant_certification_stops_it(self) -> None:
        built = plant(certification_expires=date(2024, 4, 1))
        reasons = built.blocking_reasons(DAY)
        assert len(reasons) == 1
        assert "certification expired" in reasons[0]

    def test_certification_covers_the_day_it_expires(self) -> None:
        assert plant(certification_expires=DAY).is_operable(DAY)

    def test_both_reasons_are_reported_together(self) -> None:
        built = plant(certification_expires=date(2024, 4, 1))
        assert len(built.blocking_reasons(date(2024, 10, 1))) == 3

    def test_describe(self) -> None:
        line = plant(location="Ashfield").describe()
        assert "PL-1" in line
        assert "at Ashfield" in line
        assert "customary" in line
        assert "2 scales" in line
