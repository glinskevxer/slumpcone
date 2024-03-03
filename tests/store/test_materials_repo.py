from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import NotFoundError
from slumpcone.materials.certification import Certificate, CertificateKind
from slumpcone.materials.kinds import (
    AdmixtureType,
    CementType,
    MaterialClass,
    ScmKind,
    WaterSource,
)
from slumpcone.materials.spec import Material
from slumpcone.percent import Percent
from slumpcone.store.db import Database
from slumpcone.store.materials_repo import MaterialRepository
from slumpcone.store.migrations import migrate
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


@pytest.fixture()
def repo() -> MaterialRepository:
    database = Database.in_memory()
    migrate(database)
    return MaterialRepository(database)


def cement() -> Material:
    return Material(
        "CEM-I",
        "Ashfield Type I/II",
        MaterialClass.CEMENT,
        supplier="Ashfield Cement",
        source="Ashfield mill",
        cement_type=CementType.TYPE_II,
        specific_gravity=3.15,
        notes="silo 1",
    )


def coarse() -> Material:
    return Material(
        "CA-57",
        "Number 57 limestone",
        MaterialClass.COARSE_AGGREGATE,
        specific_gravity=2.68,
        absorption=Percent(0.7),
        nominal_max_size=Quantity(1.0, "in"),
        dry_rodded_unit_weight=MassPerVolume(101.5, "lb", "ft3"),
    )


class CaseRoundTrip:
    def test_a_cement(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        assert repo.get("CEM-I") == cement()

    def test_an_aggregate_keeps_its_units(self, repo: MaterialRepository) -> None:
        repo.save(coarse())
        loaded = repo.get("CA-57")
        assert loaded.nominal_max_size is not None
        assert loaded.nominal_max_size.to("in").value == pytest.approx(1.0)
        assert loaded.dry_rodded_unit_weight is not None
        assert loaded.dry_rodded_unit_weight.value == pytest.approx(101.5)

    def test_a_fine_aggregate(self, repo: MaterialRepository) -> None:
        sand = Material(
            "FA-1",
            "Concrete sand",
            MaterialClass.FINE_AGGREGATE,
            specific_gravity=2.63,
            absorption=Percent(1.4),
            fineness_modulus=2.84,
        )
        repo.save(sand)
        assert repo.get("FA-1") == sand

    def test_an_admixture(self, repo: MaterialRepository) -> None:
        admix = Material(
            "AD-WR",
            "Water reducer",
            MaterialClass.ADMIXTURE,
            admixture_type=AdmixtureType.TYPE_A_WATER_REDUCING,
            solids_content=Percent(41.0),
            specific_gravity=1.2,
        )
        repo.save(admix)
        assert repo.get("AD-WR") == admix

    def test_an_scm(self, repo: MaterialRepository) -> None:
        ash = Material(
            "SCM-F",
            "Class F ash",
            MaterialClass.SCM,
            scm_kind=ScmKind.FLY_ASH_F,
            specific_gravity=2.35,
        )
        repo.save(ash)
        assert repo.get("SCM-F") == ash

    def test_water(self, repo: MaterialRepository) -> None:
        water = Material(
            "W-1", "Reclaimer water", MaterialClass.WATER, water_source=WaterSource.RECLAIMED
        )
        repo.save(water)
        assert repo.get("W-1") == water


class CaseQuerying:
    def test_save_is_an_upsert(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        repo.save(
            Material(
                "CEM-I",
                "Ashfield relabelled",
                MaterialClass.CEMENT,
                cement_type=CementType.TYPE_II,
                specific_gravity=3.16,
            )
        )
        assert repo.get("CEM-I").name == "Ashfield relabelled"
        assert len(repo.all()) == 1

    def test_save_all_in_one_go(self, repo: MaterialRepository) -> None:
        repo.save_all([cement(), coarse()])
        assert [m.code for m in repo.all()] == ["CA-57", "CEM-I"]

    def test_find_returns_none_when_absent(self, repo: MaterialRepository) -> None:
        assert repo.find("CEM-I") is None

    def test_get_names_what_is_missing(self, repo: MaterialRepository) -> None:
        with pytest.raises(NotFoundError, match="CEM-I"):
            repo.get("cem i")

    def test_of_class(self, repo: MaterialRepository) -> None:
        repo.save_all([cement(), coarse()])
        assert [m.code for m in repo.of_class(MaterialClass.CEMENT)] == ["CEM-I"]

    def test_delete(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        repo.delete("CEM-I")
        assert repo.all() == ()

    def test_delete_names_what_is_missing(self, repo: MaterialRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("CEM-I")


class CaseCertificates:
    def cert(self, reference: str = "MC-1") -> Certificate:
        return Certificate(
            "CEM-I",
            CertificateKind.MILL_CERTIFICATE,
            reference,
            date(2024, 4, 1),
            date(2024, 5, 16),
            issuer="Ashfield Cement",
            lot="LOT-7",
        )

    def test_round_trip(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        repo.save_certificate(self.cert())
        assert repo.certificates_for("CEM-I") == (self.cert(),)

    def test_the_material_has_to_be_on_file(self, repo: MaterialRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.save_certificate(self.cert())

    def test_saving_the_same_reference_updates_it(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        repo.save_certificate(self.cert())
        repo.save_certificate(
            Certificate(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 4, 1),
                date(2024, 6, 30),
            )
        )
        filed = repo.certificates_for("CEM-I")
        assert len(filed) == 1
        assert filed[0].expires == date(2024, 6, 30)

    def test_certificates_come_back_newest_first(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        repo.save_certificate(self.cert("MC-1"))
        repo.save_certificate(
            Certificate(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-2",
                date(2024, 6, 1),
                date(2024, 7, 15),
            )
        )
        assert [c.reference for c in repo.certificates_for("CEM-I")] == ["MC-2", "MC-1"]

    def test_deleting_a_material_takes_its_certificates(self, repo: MaterialRepository) -> None:
        repo.save(cement())
        repo.save_certificate(self.cert())
        repo.delete("CEM-I")
        assert repo.certificates_for("CEM-I") == ()

    def test_load_catalog_brings_back_everything(self, repo: MaterialRepository) -> None:
        repo.save_all([cement(), coarse()])
        repo.save_certificate(self.cert())
        catalog = repo.load_catalog()
        assert catalog.codes() == ("CA-57", "CEM-I")
        assert catalog.is_batchable("CEM-I", date(2024, 4, 10))
        assert not catalog.is_batchable("CA-57", date(2024, 4, 10))
