from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import ConflictError, NotFoundError, RuleViolationError
from slumpcone.materials.catalog import MaterialCatalog, required_certificates
from slumpcone.materials.certification import Certificate, CertificateKind
from slumpcone.materials.kinds import (
    AdmixtureType,
    CementType,
    MaterialClass,
    WaterSource,
)
from slumpcone.materials.spec import Material
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

DAY = date(2024, 6, 12)


def cement() -> Material:
    return Material(
        "CEM-I",
        "Ashfield Type I/II",
        MaterialClass.CEMENT,
        cement_type=CementType.TYPE_II,
        specific_gravity=3.15,
    )


def coarse() -> Material:
    return Material(
        "CA-57",
        "Number 57 limestone",
        MaterialClass.COARSE_AGGREGATE,
        specific_gravity=2.68,
        absorption=Percent(0.7),
        nominal_max_size=Quantity(1.0, "in"),
    )


def water(source: WaterSource) -> Material:
    return Material("W-1", "Plant water", MaterialClass.WATER, water_source=source)


def cert(
    code: str, kind: CertificateKind, ref: str, issued: date, expires: date
) -> Certificate:
    return Certificate(code, kind, ref, issued, expires)


def stocked() -> MaterialCatalog:
    catalog = MaterialCatalog()
    catalog.add_all([cement(), coarse()])
    return catalog


class CaseRequiredCertificates:
    def test_cement_needs_a_mill_certificate(self) -> None:
        assert required_certificates(cement()) == (CertificateKind.MILL_CERTIFICATE,)

    def test_aggregate_needs_two(self) -> None:
        assert required_certificates(coarse()) == (
            CertificateKind.SOURCE_APPROVAL,
            CertificateKind.GRADATION,
        )

    def test_potable_water_needs_nothing(self) -> None:
        assert required_certificates(water(WaterSource.POTABLE)) == ()

    def test_reclaimed_water_needs_a_qualification(self) -> None:
        assert required_certificates(water(WaterSource.RECLAIMED)) == (
            CertificateKind.WATER_QUALIFICATION,
        )

    def test_an_admixture_needs_a_conformance_letter(self) -> None:
        admix = Material(
            "AD-1",
            "Water reducer",
            MaterialClass.ADMIXTURE,
            admixture_type=AdmixtureType.TYPE_A_WATER_REDUCING,
        )
        assert required_certificates(admix) == (CertificateKind.CONFORMANCE_LETTER,)


class CaseFiling:
    def test_add_and_get(self) -> None:
        catalog = MaterialCatalog()
        catalog.add(cement())
        assert catalog.get("cem i").code == "CEM-I"
        assert len(catalog) == 1

    def test_add_refuses_a_duplicate(self) -> None:
        catalog = stocked()
        with pytest.raises(ConflictError):
            catalog.add(cement())

    def test_get_names_what_is_missing(self) -> None:
        with pytest.raises(NotFoundError, match="CEM-III"):
            MaterialCatalog().get("CEM-III")

    def test_replace_needs_the_code_to_exist(self) -> None:
        with pytest.raises(NotFoundError):
            MaterialCatalog().replace(cement())

    def test_replace_keeps_the_paper(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 6, 1),
                date(2024, 7, 15),
            )
        )
        catalog.replace(
            Material(
                "CEM-I",
                "Ashfield Type I/II relabelled",
                MaterialClass.CEMENT,
                cement_type=CementType.TYPE_II,
                specific_gravity=3.16,
            )
        )
        assert catalog.get("CEM-I").specific_gravity == pytest.approx(3.16)
        assert len(catalog.certificates_for("CEM-I")) == 1

    def test_membership_and_iteration(self) -> None:
        catalog = stocked()
        assert "cem i" in catalog
        assert "CEM-IX" not in catalog
        assert 7 not in catalog
        assert "" not in catalog
        assert [m.code for m in catalog] == ["CA-57", "CEM-I"]

    def test_of_class(self) -> None:
        catalog = stocked()
        assert [m.code for m in catalog.of_class(MaterialClass.CEMENT)] == ["CEM-I"]

    def test_codes(self) -> None:
        assert stocked().codes() == ("CA-57", "CEM-I")


class CaseCertifying:
    def test_certify_needs_the_material_on_file(self) -> None:
        with pytest.raises(NotFoundError):
            MaterialCatalog().certify(
                cert(
                    "CEM-I",
                    CertificateKind.MILL_CERTIFICATE,
                    "MC-1",
                    date(2024, 6, 1),
                    date(2024, 7, 1),
                )
            )

    def test_certify_refuses_a_duplicate_reference(self) -> None:
        catalog = stocked()
        one = cert(
            "CEM-I",
            CertificateKind.MILL_CERTIFICATE,
            "MC-1",
            date(2024, 6, 1),
            date(2024, 7, 1),
        )
        catalog.certify(one)
        with pytest.raises(ConflictError, match="MC-1"):
            catalog.certify(one)

    def test_certificates_come_back_newest_first(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 5, 1),
                date(2024, 6, 15),
            )
        )
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-2",
                date(2024, 6, 1),
                date(2024, 7, 15),
            )
        )
        assert [c.reference for c in catalog.certificates_for("CEM-I")] == ["MC-2", "MC-1"]

    def test_the_latest_issue_covering_the_day_wins(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 5, 1),
                date(2024, 6, 30),
            )
        )
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-2",
                date(2024, 6, 1),
                date(2024, 7, 15),
            )
        )
        found = catalog.current_certificate("CEM-I", CertificateKind.MILL_CERTIFICATE, DAY)
        assert found is not None
        assert found.reference == "MC-2"

    def test_no_certificate_covering_the_day(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 1, 1),
                date(2024, 2, 15),
            )
        )
        assert (
            catalog.current_certificate("CEM-I", CertificateKind.MILL_CERTIFICATE, DAY) is None
        )


class CaseBatchability:
    def test_a_material_with_no_paper_is_not_batchable(self) -> None:
        catalog = stocked()
        assert not catalog.is_batchable("CEM-I", DAY)
        assert catalog.missing_certificates("CEM-I", DAY) == (CertificateKind.MILL_CERTIFICATE,)

    def test_one_of_two_is_still_missing(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CA-57",
                CertificateKind.SOURCE_APPROVAL,
                "SA-1",
                date(2024, 1, 1),
                date(2024, 12, 31),
            )
        )
        assert catalog.missing_certificates("CA-57", DAY) == (CertificateKind.GRADATION,)

    def test_fully_papered_is_batchable(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CA-57",
                CertificateKind.SOURCE_APPROVAL,
                "SA-1",
                date(2024, 1, 1),
                date(2024, 12, 31),
            )
        )
        catalog.certify(
            cert("CA-57", CertificateKind.GRADATION, "G-1", date(2024, 5, 1), date(2024, 8, 1))
        )
        assert catalog.is_batchable("CA-57", DAY)
        assert catalog.require_batchable("CA-57", DAY).code == "CA-57"

    def test_require_batchable_names_the_missing_kind(self) -> None:
        catalog = stocked()
        with pytest.raises(RuleViolationError) as caught:
            catalog.require_batchable("CEM-I", DAY)
        assert caught.value.code == "MATERIAL_NOT_CERTIFIED"
        assert "mill_certificate" in caught.value.detail
        assert "2024-06-12" in caught.value.detail

    def test_potable_water_is_batchable_with_no_paper_at_all(self) -> None:
        catalog = MaterialCatalog()
        catalog.add(water(WaterSource.POTABLE))
        assert catalog.is_batchable("W-1", DAY)

    def test_reclaimed_water_is_not(self) -> None:
        catalog = MaterialCatalog()
        catalog.add(water(WaterSource.RECLAIMED))
        assert not catalog.is_batchable("W-1", DAY)


class CaseExpiry:
    def test_expiring_soon_is_sorted_by_expiry(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 5, 20),
                date(2024, 6, 25),
            )
        )
        catalog.certify(
            cert(
                "CA-57",
                CertificateKind.GRADATION,
                "G-1",
                date(2024, 5, 1),
                date(2024, 6, 20),
            )
        )
        assert [c.reference for c in catalog.expiring_soon(DAY)] == ["G-1", "MC-1"]

    def test_nothing_expiring_inside_a_short_window(self) -> None:
        catalog = stocked()
        catalog.certify(
            cert(
                "CEM-I",
                CertificateKind.MILL_CERTIFICATE,
                "MC-1",
                date(2024, 5, 20),
                date(2024, 8, 25),
            )
        )
        assert catalog.expiring_soon(DAY, within_days=5) == ()
