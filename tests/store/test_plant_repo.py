from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import NotFoundError
from slumpcone.materials.kinds import MaterialClass, WaterSource
from slumpcone.plant.plant import MixingMethod, Plant
from slumpcone.plant.scale import Scale
from slumpcone.plant.silo import Silo
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.store.plant_repo import PlantRepository
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


@pytest.fixture()
def repo() -> PlantRepository:
    database = Database.in_memory()
    migrate(database)
    return PlantRepository(database)


def scales() -> tuple[Scale, ...]:
    return (
        Scale(
            "SC-AGG",
            "Aggregate hopper scale",
            Quantity(12000, "lb"),
            Quantity(2, "lb"),
            (MaterialClass.COARSE_AGGREGATE, MaterialClass.FINE_AGGREGATE),
            date(2024, 3, 1),
        ),
        Scale(
            "SC-CEM",
            "Cement hopper scale",
            Quantity(6000, "lb"),
            Quantity(1, "lb"),
            (MaterialClass.CEMENT,),
            date(2024, 3, 1),
            calibration_days=90,
        ),
    )


def plant(**overrides: object) -> Plant:
    fields: dict[str, object] = {
        "code": "PL-1",
        "name": "Northmoor batch plant",
        "scales": scales(),
        "max_load": Quantity(11, "yd3"),
        "location": "Ashfield",
        "certification_expires": date(2025, 1, 31),
    }
    fields.update(overrides)
    return Plant(**fields)  # type: ignore[arg-type]


def silos() -> tuple[Silo, ...]:
    return (
        Silo(
            "SI-1",
            "Cement silo one",
            "CEM-I",
            Quantity(200000, "lb"),
            Quantity(120000, "lb"),
            Quantity(30000, "lb"),
        ),
        Silo("SI-2", "Ash silo", "SCM-F", Quantity(120000, "lb"), Quantity(40000, "lb")),
    )


class CaseRoundTrip:
    def test_a_plant_with_scales(self, repo: PlantRepository) -> None:
        repo.save(plant())
        assert repo.get("pl 1") == plant()

    def test_a_bare_plant(self, repo: PlantRepository) -> None:
        bare = Plant("PL-2", "Yard plant")
        repo.save(bare)
        assert repo.get("PL-2") == bare

    def test_the_metric_system_survives(self, repo: PlantRepository) -> None:
        metric = Plant(
            "PL-3",
            "Metric plant",
            unit_system=UnitSystem.METRIC,
            mixing_method=MixingMethod.CENTRAL_MIXED,
            water_source=WaterSource.RECLAIMED,
        )
        repo.save(metric)
        loaded = repo.get("PL-3")
        assert loaded.unit_system is UnitSystem.METRIC
        assert loaded.mixing_method is MixingMethod.CENTRAL_MIXED
        assert loaded.water_source is WaterSource.RECLAIMED

    def test_scale_details_survive(self, repo: PlantRepository) -> None:
        repo.save(plant())
        scale = repo.get("PL-1").scale("SC-CEM")
        assert scale.calibration_days == 90
        assert scale.weighs == (MaterialClass.CEMENT,)

    def test_get_names_what_is_missing(self, repo: PlantRepository) -> None:
        with pytest.raises(NotFoundError, match="PL-9"):
            repo.get("PL-9")

    def test_all_is_sorted(self, repo: PlantRepository) -> None:
        repo.save(plant())
        repo.save(Plant("PL-0", "Older plant"))
        assert [p.code for p in repo.all()] == ["PL-0", "PL-1"]


class CaseReplacement:
    def test_saving_again_replaces_the_scales(self, repo: PlantRepository) -> None:
        repo.save(plant())
        repo.save(plant(scales=scales()[:1]))
        assert repo.get("PL-1").scale_codes == ("SC-AGG",)

    def test_saving_again_updates_the_header(self, repo: PlantRepository) -> None:
        repo.save(plant())
        repo.save(plant(name="Northmoor plant renamed"))
        assert repo.get("PL-1").name == "Northmoor plant renamed"

    def test_delete_takes_the_scales_with_it(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        repo.delete("PL-1")
        assert repo.all() == ()
        assert repo._db.scalar("SELECT count(*) FROM plant_scale") == 0
        assert repo._db.scalar("SELECT count(*) FROM plant_silo") == 0

    def test_delete_names_what_is_missing(self, repo: PlantRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("PL-9")


class CaseSilos:
    def test_round_trip(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        assert repo.silos("PL-1") == silos()

    def test_one_by_code(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        assert repo.silo("PL-1", "si 2").material_code == "SCM-F"

    def test_an_unknown_silo_is_named(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        with pytest.raises(NotFoundError, match="SI-9"):
            repo.silo("PL-1", "SI-9")

    def test_saving_one_back_is_what_a_drawdown_does(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        drawn = repo.silo("PL-1", "SI-1").draw(Quantity(20000, "lb"))
        repo.save_silo("PL-1", drawn)
        assert repo.silo("PL-1", "SI-1").level == Quantity(100000, "lb")

    def test_saving_a_silo_needs_the_plant(self, repo: PlantRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.save_silo("PL-9", silos()[0])

    def test_silos_holding_a_material_across_plants(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        repo.save(Plant("PL-2", "Yard plant"), (silos()[0],))
        holding = repo.silos_holding("cem i")
        assert [code for code, _ in holding] == ["PL-1", "PL-2"]

    def test_saving_a_plant_again_replaces_its_silos(self, repo: PlantRepository) -> None:
        repo.save(plant(), silos())
        repo.save(plant(), silos()[:1])
        assert [s.code for s in repo.silos("PL-1")] == ["SI-1"]
