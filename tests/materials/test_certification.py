from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import ValidationError
from slumpcone.materials.certification import (
    Certificate,
    CertificateKind,
    CertificateState,
)


def mill(**overrides: object) -> Certificate:
    fields: dict[str, object] = {
        "material_code": "CEM-I",
        "kind": CertificateKind.MILL_CERTIFICATE,
        "reference": "MC-2024-0412",
        "issued": date(2024, 4, 1),
        "expires": date(2024, 5, 16),
    }
    fields.update(overrides)
    return Certificate(**fields)  # type: ignore[arg-type]


class CaseKind:
    def test_parse(self) -> None:
        assert CertificateKind.parse("mill certificate") is CertificateKind.MILL_CERTIFICATE
        assert CertificateKind.parse("SOURCE-APPROVAL") is CertificateKind.SOURCE_APPROVAL

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="certificate kind"):
            CertificateKind.parse("handshake")

    def test_default_terms_differ_by_kind(self) -> None:
        assert CertificateKind.MILL_CERTIFICATE.default_term_days == 45
        assert CertificateKind.SOURCE_APPROVAL.default_term_days == 365
        assert CertificateKind.GRADATION.default_term_days == 90

    def test_prints_its_own_value(self) -> None:
        assert str(CertificateKind.GRADATION) == "gradation"


class CaseConstruction:
    def test_codes_are_normalised(self) -> None:
        cert = mill(material_code=" cem i ", reference="mc 2024 0412", lot="lot 7")
        assert cert.material_code == "CEM-I"
        assert cert.reference == "MC-2024-0412"
        assert cert.lot == "LOT-7"

    def test_issuer_whitespace_collapses(self) -> None:
        assert mill(issuer="  Ashfield   Cement ").issuer == "Ashfield Cement"

    def test_expiry_before_issue_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="expires before"):
            mill(expires=date(2024, 3, 1))

    def test_same_day_expiry_is_allowed(self) -> None:
        cert = mill(expires=date(2024, 4, 1))
        assert cert.covers(date(2024, 4, 1))

    def test_for_term_uses_the_kind_default(self) -> None:
        cert = Certificate.for_term(
            "CEM-I", CertificateKind.MILL_CERTIFICATE, "MC-1", date(2024, 4, 1)
        )
        assert cert.expires == date(2024, 5, 16)

    def test_for_term_takes_an_explicit_term(self) -> None:
        cert = Certificate.for_term(
            "CA-57", CertificateKind.GRADATION, "G-1", date(2024, 4, 1), days=30
        )
        assert cert.expires == date(2024, 5, 1)

    def test_for_term_refuses_a_non_positive_term(self) -> None:
        with pytest.raises(ValidationError, match="positive"):
            Certificate.for_term(
                "CA-57", CertificateKind.GRADATION, "G-1", date(2024, 4, 1), days=0
            )


class CaseState:
    cert = mill()

    def test_before_issue(self) -> None:
        assert self.cert.state(date(2024, 3, 31)) is CertificateState.NOT_YET_ISSUED

    def test_on_the_day_of_issue(self) -> None:
        assert self.cert.state(date(2024, 4, 1)) is CertificateState.CURRENT

    def test_well_inside(self) -> None:
        assert self.cert.state(date(2024, 4, 10)) is CertificateState.CURRENT

    def test_inside_the_warning_window(self) -> None:
        assert self.cert.state(date(2024, 4, 30)) is CertificateState.EXPIRING

    def test_on_the_expiry_date_it_still_covers(self) -> None:
        assert self.cert.state(date(2024, 5, 16)) is CertificateState.EXPIRING
        assert self.cert.covers(date(2024, 5, 16))

    def test_the_day_after_expiry(self) -> None:
        assert self.cert.state(date(2024, 5, 17)) is CertificateState.EXPIRED
        assert not self.cert.covers(date(2024, 5, 17))

    def test_the_warning_window_is_adjustable(self) -> None:
        assert self.cert.state(date(2024, 4, 30), warning_days=0) is CertificateState.CURRENT

    def test_which_states_block_a_batch(self) -> None:
        assert CertificateState.EXPIRED.blocks_batching
        assert CertificateState.NOT_YET_ISSUED.blocks_batching
        assert not CertificateState.CURRENT.blocks_batching
        assert not CertificateState.EXPIRING.blocks_batching

    def test_state_prints_its_own_value(self) -> None:
        assert str(CertificateState.EXPIRING) == "expiring"


class CaseReporting:
    def test_days_remaining(self) -> None:
        assert mill().days_remaining(date(2024, 5, 1)) == 15

    def test_days_remaining_goes_negative(self) -> None:
        assert mill().days_remaining(date(2024, 5, 26)) == -10

    def test_describe(self) -> None:
        line = mill().describe(date(2024, 4, 10))
        assert "CEM-I" in line
        assert "mill_certificate" in line
        assert "2024-04-01 to 2024-05-16" in line
        assert "current" in line
