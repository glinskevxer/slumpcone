"""Certificates, and the fact that they run out.

Every material in a batch has to be covered by a current certificate on the day
it was batched. Cement carries a mill certificate, aggregate carries a source
approval and a gradation, an admixture carries a conformance letter, and
non-potable water carries a qualification. They expire on different clocks and
nobody notices until an inspector asks for the file.

The date a certificate is judged against is the date of the batch, never today.
A ticket written in March is judged against the certificate that was current in
March, whatever has expired since.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name


class CertificateKind(Enum):
    """What kind of paper this is."""

    MILL_CERTIFICATE = "mill_certificate"
    SOURCE_APPROVAL = "source_approval"
    GRADATION = "gradation"
    CONFORMANCE_LETTER = "conformance_letter"
    WATER_QUALIFICATION = "water_qualification"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> CertificateKind:
        """Read a certificate kind out of a filing."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown certificate kind {text!r}", field="certificate_kind")

    @property
    def default_term_days(self) -> int:
        """How long this kind is normally good for.

        A mill certificate covers a shipment and is renewed monthly. A source
        approval runs a year. A gradation is a rolling test and the interval is
        set by the specifying agency, so a year is only the fallback.
        """
        table = {
            CertificateKind.MILL_CERTIFICATE: 45,
            CertificateKind.SOURCE_APPROVAL: 365,
            CertificateKind.GRADATION: 90,
            CertificateKind.CONFORMANCE_LETTER: 365,
            CertificateKind.WATER_QUALIFICATION: 365,
        }
        return table[self]


class CertificateState(Enum):
    """Where a certificate sits relative to a date."""

    NOT_YET_ISSUED = "not_yet_issued"
    CURRENT = "current"
    EXPIRING = "expiring"
    EXPIRED = "expired"

    def __str__(self) -> str:
        return self.value

    @property
    def blocks_batching(self) -> bool:
        """True when a material in this state cannot go into a batch."""
        return self in {CertificateState.NOT_YET_ISSUED, CertificateState.EXPIRED}


# A certificate inside this many days of its expiry is reported as expiring so
# the plant can chase the paper before it stops a truck.
WARNING_DAYS = 21


@dataclass(frozen=True, slots=True)
class Certificate:
    """One piece of paper covering one material for a stretch of time."""

    material_code: str
    kind: CertificateKind
    reference: str
    issued: date
    expires: date
    issuer: str | None = None
    lot: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        object.__setattr__(
            self, "reference", normalize_code(self.reference, field="certificate_reference")
        )
        if self.issuer is not None:
            object.__setattr__(self, "issuer", normalize_name(self.issuer, field="issuer"))
        if self.lot is not None:
            object.__setattr__(self, "lot", normalize_code(self.lot, field="lot"))
        if self.expires < self.issued:
            raise ValidationError(
                f"certificate {self.reference} expires before it was issued", field="expires"
            )

    @classmethod
    def for_term(
        cls,
        material_code: str,
        kind: CertificateKind,
        reference: str,
        issued: date,
        *,
        days: int | None = None,
        issuer: str | None = None,
        lot: str | None = None,
    ) -> Certificate:
        """Build a certificate running the kind's normal term from ``issued``."""
        from datetime import timedelta

        term = kind.default_term_days if days is None else days
        if term <= 0:
            raise ValidationError("a certificate term has to be positive", field="days")
        return cls(
            material_code,
            kind,
            reference,
            issued,
            issued + timedelta(days=term),
            issuer=issuer,
            lot=lot,
        )

    def state(self, on: date, *, warning_days: int = WARNING_DAYS) -> CertificateState:
        """Where this certificate sits on ``on``.

        The expiry date is the last day the certificate covers, not the first
        day it does not. A certificate expiring on the 30th covers a batch made
        on the 30th.
        """
        if on < self.issued:
            return CertificateState.NOT_YET_ISSUED
        if on > self.expires:
            return CertificateState.EXPIRED
        if (self.expires - on).days <= warning_days:
            return CertificateState.EXPIRING
        return CertificateState.CURRENT

    def covers(self, on: date) -> bool:
        """True when this certificate is in force on ``on``."""
        return self.issued <= on <= self.expires

    def days_remaining(self, on: date) -> int:
        """Days left, negative once it has expired."""
        return (self.expires - on).days

    def describe(self, on: date) -> str:
        """One line for a listing, with the state on ``on``."""
        state = self.state(on)
        return (
            f"{self.material_code}  {self.kind}  {self.reference}  "
            f"{self.issued.isoformat()} to {self.expires.isoformat()}  {state}"
        )
