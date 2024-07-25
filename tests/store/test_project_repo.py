from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.project.project import Project, SpecifiedClass
from slumpcone.project.submittal import Submittal, SubmittalBasis, SubmittalStatus
from slumpcone.spec.exposure import ExposureSet
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.store.project_repo import ProjectRepository
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem

DAY = date(2024, 6, 12)


@pytest.fixture()
def repo() -> ProjectRepository:
    database = Database.in_memory()
    migrate(database)
    return ProjectRepository(database)


def a_class(code: str = "SLAB", **overrides: object) -> SpecifiedClass:
    fields: dict[str, object] = {
        "code": code,
        "specified_strength": Quantity(4000, "psi"),
        "exposure": ExposureSet.parse("F2 S1"),
        "slump_band": Band.symmetric(4.0, 1.0),
        "air_band": Band.between(4.5, 7.5),
        "max_water_cementitious": 0.44,
        "min_cementitious": Quantity(560, "lb"),
        "nominal_max_size": Quantity(1.0, "in"),
        "description": "paving slab",
    }
    fields.update(overrides)
    return SpecifiedClass(**fields)  # type: ignore[arg-type]


def project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "code": "P-2024-118",
        "name": "Route 9 shoulder widening",
        "classes": (a_class(), a_class("FOOTING")),
        "owner": "County highways",
        "specifier": "Harlow Engineering",
        "started_on": date(2024, 5, 1),
        "finished_on": date(2024, 11, 30),
        "notes": "night work only",
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


def submittal(reference: str = "SUB-118-03", **overrides: object) -> Submittal:
    fields: dict[str, object] = {
        "reference": reference,
        "project_code": "P-2024-118",
        "class_code": "SLAB",
        "mix_code": "4000P-57",
        "mix_revision": 1,
        "submitted_on": date(2024, 4, 2),
        "basis": SubmittalBasis.TRIAL_BATCH,
        "required_average": Quantity(5200, "psi"),
    }
    fields.update(overrides)
    return Submittal(**fields)  # type: ignore[arg-type]


class CaseProjects:
    def test_round_trip(self, repo: ProjectRepository) -> None:
        repo.save(project())
        loaded = repo.get("p 2024 118")
        assert loaded.name == "Route 9 shoulder widening"
        assert loaded.owner == "County highways"
        assert loaded.specifier == "Harlow Engineering"
        assert loaded.started_on == date(2024, 5, 1)
        assert loaded.finished_on == date(2024, 11, 30)
        assert loaded.notes == "night work only"

    def test_the_classes_come_back_in_code_order(self, repo: ProjectRepository) -> None:
        repo.save(project())
        assert [entry.code for entry in repo.get("P-2024-118").classes] == ["FOOTING", "SLAB"]

    def test_a_bare_project_round_trips(self, repo: ProjectRepository) -> None:
        bare = Project("P-1", "Small job")
        repo.save(bare)
        loaded = repo.get("P-1")
        assert loaded.classes == ()
        assert loaded.owner is None
        assert loaded.unit_system is UnitSystem.CUSTOMARY

    def test_the_class_bands_survive(self, repo: ProjectRepository) -> None:
        repo.save(project())
        entry = repo.get("P-2024-118").specified_class("SLAB")
        assert entry.slump_band is not None
        assert entry.slump_band.high == pytest.approx(5.0)
        assert entry.air_band is not None
        assert entry.air_band.low == pytest.approx(4.5)
        assert entry.min_cementitious == Quantity(560, "lb")

    def test_saving_again_replaces_the_classes(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save(project(classes=(a_class(),)))
        assert repo.get("P-2024-118").class_codes == ("SLAB",)

    def test_an_unknown_project_is_named(self, repo: ProjectRepository) -> None:
        with pytest.raises(NotFoundError, match="P-9"):
            repo.get("P-9")

    def test_all_is_sorted(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save(Project("P-2023-004", "Older job"))
        assert [p.code for p in repo.all()] == ["P-2023-004", "P-2024-118"]

    def test_open_on(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save(Project("P-2023-004", "Older job", finished_on=date(2023, 12, 31)))
        assert [p.code for p in repo.open_on(DAY)] == ["P-2024-118"]

    def test_delete_takes_the_classes(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.delete("P-2024-118")
        assert repo.all() == ()
        assert repo._db.scalar("SELECT count(*) FROM project_class") == 0

    def test_delete_names_what_is_missing(self, repo: ProjectRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("P-9")


class CaseSubmittals:
    def test_round_trip(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal())
        assert repo.submittal("sub 118 03") == submittal()

    def test_save_is_an_upsert(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal())
        repo.save_submittal(submittal().approve(date(2024, 4, 10), reviewer="County"))
        loaded = repo.submittal("SUB-118-03")
        assert loaded.status is SubmittalStatus.APPROVED
        assert loaded.reviewer == "County"

    def test_an_unknown_submittal_is_named(self, repo: ProjectRepository) -> None:
        with pytest.raises(NotFoundError, match="SUB-9"):
            repo.submittal("SUB-9")

    def test_submittals_for_a_project(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal())
        repo.save_submittal(submittal("SUB-118-04", class_code="FOOTING"))
        assert len(repo.submittals_for("P-2024-118")) == 2

    def test_approved_mixes_only_lists_valid_ones(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal())
        assert repo.approved_mixes("P-2024-118", "SLAB", DAY) == ()
        repo.save_submittal(submittal().approve(date(2024, 4, 10)))
        assert len(repo.approved_mixes("P-2024-118", "SLAB", DAY)) == 1

    def test_an_expired_approval_drops_out(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal().approve(date(2024, 4, 10), days=30))
        assert repo.approved_mixes("P-2024-118", "SLAB", DAY) == ()

    def test_require_approval(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal().approve(date(2024, 4, 10)))
        found = repo.require_approval("P-2024-118", "SLAB", "4000p 57", 1, DAY)
        assert found.reference == "SUB-118-03"

    def test_require_approval_refuses_the_wrong_revision(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal().approve(date(2024, 4, 10)))
        with pytest.raises(ConflictError, match="4000P-57 r2"):
            repo.require_approval("P-2024-118", "SLAB", "4000P-57", 2, DAY)

    def test_require_approval_refuses_another_class(self, repo: ProjectRepository) -> None:
        repo.save(project())
        repo.save_submittal(submittal().approve(date(2024, 4, 10)))
        with pytest.raises(ConflictError):
            repo.require_approval("P-2024-118", "FOOTING", "4000P-57", 1, DAY)
