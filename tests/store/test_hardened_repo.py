from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.store.db import Database
from slumpcone.store.hardened_repo import HardenedRepository
from slumpcone.store.migrations import migrate
from slumpcone.strength.cores import Core, CoreCondition
from slumpcone.strength.flexural import FlexuralBreak
from slumpcone.units.quantity import Quantity

TESTED = datetime(2024, 7, 10, 10, 15)
SPECIFIED = Quantity(4000, "psi")


@pytest.fixture()
def repo() -> HardenedRepository:
    database = Database.in_memory()
    migrate(database)
    return HardenedRepository(database)


def beam(code: str = "B-4471-A", distance: float = 9.0) -> FlexuralBreak:
    return FlexuralBreak(
        code,
        Quantity(18.0, "in"),
        Quantity(6.0, "in"),
        Quantity(6.0, "in"),
        Quantity(6200, "lbf"),
        Quantity(distance, "in"),
    )


def core(code: str = "C-1", strength: float = 3600.0) -> Core:
    from slumpcone.strength.breaks import length_diameter_correction

    load = strength * 12.566370614359172 / length_diameter_correction(2.0)
    return Core(code, Quantity(4, "in"), Quantity(8, "in"), Quantity(load, "lbf"))


class CaseBeams:
    def test_round_trip(self, repo: HardenedRepository) -> None:
        repo.save_beam(beam(), "S-4471", "4000P-57", TESTED)
        loaded = repo.beam("b 4471 a")
        assert loaded.specimen_code == "B-4471-A"
        assert loaded.span == Quantity(18, "in")
        assert loaded.modulus_of_rupture.value == pytest.approx(516.7, abs=1.0)

    def test_a_beam_breaks_once(self, repo: HardenedRepository) -> None:
        repo.save_beam(beam(), "S-4471", "4000P-57", TESTED)
        with pytest.raises(ConflictError, match="B-4471-A"):
            repo.save_beam(beam(), "S-4471", "4000P-57", TESTED)

    def test_an_unknown_beam(self, repo: HardenedRepository) -> None:
        with pytest.raises(NotFoundError, match="B-9"):
            repo.beam("B-9")

    def test_beams_in_a_set(self, repo: HardenedRepository) -> None:
        repo.save_beam(beam("B-4471-B"), "S-4471", "4000P-57", TESTED)
        repo.save_beam(beam("B-4471-A"), "S-4471", "4000P-57", TESTED)
        assert [entry.specimen_code for entry in repo.beams_in("S-4471")] == [
            "B-4471-A",
            "B-4471-B",
        ]

    def test_beams_for_a_mix(self, repo: HardenedRepository) -> None:
        repo.save_beam(beam("B-1"), "S-1", "4000P-57", TESTED)
        repo.save_beam(beam("B-2"), "S-2", "3000W-67", TESTED)
        assert [entry.specimen_code for entry in repo.beams_for_mix("4000p 57")] == ["B-1"]

    def test_a_discarded_beam_still_stores(self, repo: HardenedRepository) -> None:
        repo.save_beam(beam("B-1", distance=4.0), "S-1", "4000P-57", TESTED)
        assert not repo.beam("B-1").is_usable


class CaseCores:
    def test_round_trip(self, repo: HardenedRepository) -> None:
        repo.save_core(core(), "Bay 4 slab", SPECIFIED, TESTED)
        loaded = repo.core("C-1")
        assert loaded.strength.value == pytest.approx(3600.0, abs=5.0)
        assert loaded.condition is CoreCondition.SOAKED

    def test_the_conditioning_and_reinforcement_survive(self, repo: HardenedRepository) -> None:
        odd = Core(
            "C-2",
            Quantity(4, "in"),
            Quantity(8, "in"),
            Quantity(45000, "lbf"),
            CoreCondition.AS_RECEIVED,
            has_reinforcement=True,
        )
        repo.save_core(odd, "Bay 4 slab", SPECIFIED, TESTED)
        loaded = repo.core("C-2")
        assert loaded.condition is CoreCondition.AS_RECEIVED
        assert loaded.has_reinforcement

    def test_a_core_is_filed_once(self, repo: HardenedRepository) -> None:
        repo.save_core(core(), "Bay 4 slab", SPECIFIED, TESTED)
        with pytest.raises(ConflictError, match="C-1"):
            repo.save_core(core(), "Bay 4 slab", SPECIFIED, TESTED)

    def test_an_unknown_core(self, repo: HardenedRepository) -> None:
        with pytest.raises(NotFoundError, match="C-9"):
            repo.core("C-9")

    def test_locations(self, repo: HardenedRepository) -> None:
        repo.save_core(core("C-1"), "Bay 4 slab", SPECIFIED, TESTED)
        repo.save_core(core("C-2"), "Bay 2 wall", SPECIFIED, TESTED)
        assert repo.locations() == ("Bay 2 wall", "Bay 4 slab")

    def test_an_investigation(self, repo: HardenedRepository) -> None:
        for index, strength in enumerate((3600.0, 3700.0, 3500.0)):
            repo.save_core(core(f"C-{index}", strength), "Bay 4 slab", SPECIFIED, TESTED)
        found = repo.investigation("Bay 4 slab")
        assert found.has_enough_cores
        assert found.is_adequate

    def test_an_investigation_that_fails(self, repo: HardenedRepository) -> None:
        for index, strength in enumerate((3600.0, 3700.0, 2800.0)):
            repo.save_core(core(f"C-{index}", strength), "Bay 4 slab", SPECIFIED, TESTED)
        assert not repo.investigation("Bay 4 slab").is_adequate

    def test_a_location_with_no_cores(self, repo: HardenedRepository) -> None:
        with pytest.raises(NotFoundError, match="Bay 9"):
            repo.investigation("Bay 9")

    def test_delete(self, repo: HardenedRepository) -> None:
        repo.save_core(core(), "Bay 4 slab", SPECIFIED, TESTED)
        repo.delete_core("C-1")
        assert repo.locations() == ()

    def test_deleting_an_unknown_core(self, repo: HardenedRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete_core("C-9")
