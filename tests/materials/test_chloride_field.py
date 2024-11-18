from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import CementType, MaterialClass
from slumpcone.materials.spec import Material
from slumpcone.percent import Percent
from slumpcone.store.db import Database
from slumpcone.store.materials_repo import MaterialRepository
from slumpcone.store.migrations import migrate


def cement(**overrides: object) -> Material:
    fields: dict[str, object] = {
        "code": "CEM-I",
        "name": "Portland",
        "material_class": MaterialClass.CEMENT,
        "cement_type": CementType.TYPE_II,
        "specific_gravity": 3.15,
    }
    fields.update(overrides)
    return Material(**fields)  # type: ignore[arg-type]


@pytest.fixture()
def repo() -> MaterialRepository:
    database = Database.in_memory()
    migrate(database)
    return MaterialRepository(database)


class CaseField:
    def test_a_material_can_carry_an_assay(self) -> None:
        assert cement(chloride_content=Percent(0.012)).chloride_content == Percent(0.012)

    def test_no_assay_is_not_zero(self) -> None:
        assert cement().chloride_content is None
        assert not cement().has_chloride_assay
        assert cement(chloride_content=Percent(0.0)).has_chloride_assay

    @pytest.mark.parametrize("bad", [-0.1, 5.1])
    def test_an_impossible_assay_is_refused(self, bad: float) -> None:
        with pytest.raises(ValidationError, match="material assay"):
            cement(chloride_content=Percent(bad))

    def test_it_survives_the_round_trip(self, repo: MaterialRepository) -> None:
        repo.save(cement(chloride_content=Percent(0.012)))
        assert repo.get("CEM-I").chloride_content == Percent(0.012)

    def test_a_material_with_no_assay_round_trips_as_none(
        self, repo: MaterialRepository
    ) -> None:
        repo.save(cement())
        assert repo.get("CEM-I").chloride_content is None

    def test_the_column_was_added_by_a_migration(self, repo: MaterialRepository) -> None:
        assert "chloride_percent" in repo._db.column_names("material")

    def test_the_column_is_last_because_it_was_added(self, repo: MaterialRepository) -> None:
        columns = repo._db.column_names("material")
        assert columns[-1] == "chloride_percent"
