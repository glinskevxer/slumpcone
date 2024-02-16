"""The plant's material catalogue and the paper that has to go with it.

Which certificates a material needs is a property of what the material is, not
of what somebody remembered to file. Aggregate needs a source approval and a
current gradation. Cement needs a mill certificate. Water needs a qualification
only when it is not potable, which is the one rule that reads off another
field, and it is exactly the one that gets missed when a plant switches to a
reclaimer.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import date

from slumpcone.errors import ConflictError, NotFoundError, RuleViolationError
from slumpcone.identity import normalize_code
from slumpcone.materials.certification import Certificate, CertificateKind, CertificateState
from slumpcone.materials.kinds import MaterialClass
from slumpcone.materials.spec import Material

_REQUIRED_BY_CLASS: dict[MaterialClass, tuple[CertificateKind, ...]] = {
    MaterialClass.CEMENT: (CertificateKind.MILL_CERTIFICATE,),
    MaterialClass.SCM: (CertificateKind.MILL_CERTIFICATE,),
    MaterialClass.COARSE_AGGREGATE: (
        CertificateKind.SOURCE_APPROVAL,
        CertificateKind.GRADATION,
    ),
    MaterialClass.FINE_AGGREGATE: (
        CertificateKind.SOURCE_APPROVAL,
        CertificateKind.GRADATION,
    ),
    MaterialClass.ADMIXTURE: (CertificateKind.CONFORMANCE_LETTER,),
    MaterialClass.FIBER: (CertificateKind.CONFORMANCE_LETTER,),
    MaterialClass.PIGMENT: (CertificateKind.CONFORMANCE_LETTER,),
    MaterialClass.WATER: (),
}


def required_certificates(material: Material) -> tuple[CertificateKind, ...]:
    """Which certificate kinds ``material`` has to have on file to be batched."""
    required = _REQUIRED_BY_CLASS[material.material_class]
    if material.material_class is MaterialClass.WATER:
        source = material.water_source
        if source is not None and source.needs_qualification:
            return (CertificateKind.WATER_QUALIFICATION,)
    return required


class MaterialCatalog:
    """Every material the plant can batch, and its certificates."""

    def __init__(self) -> None:
        self._materials: dict[str, Material] = {}
        self._certificates: dict[str, list[Certificate]] = {}

    def __len__(self) -> int:
        return len(self._materials)

    def __contains__(self, code: object) -> bool:
        if not isinstance(code, str):
            return False
        try:
            return normalize_code(code) in self._materials
        except Exception:
            return False

    def __iter__(self) -> Iterator[Material]:
        return iter(sorted(self._materials.values(), key=lambda m: m.code))

    def add(self, material: Material) -> Material:
        """File a material. Refuses a code that is already on file."""
        if material.code in self._materials:
            raise ConflictError("material", material.code)
        self._materials[material.code] = material
        self._certificates.setdefault(material.code, [])
        return material

    def add_all(self, materials: Iterable[Material]) -> None:
        """File several materials, stopping at the first collision."""
        for material in materials:
            self.add(material)

    def replace(self, material: Material) -> Material:
        """Overwrite a material that is already on file, keeping its paper."""
        if material.code not in self._materials:
            raise NotFoundError("material", material.code)
        self._materials[material.code] = material
        return material

    def get(self, code: str) -> Material:
        """The material filed under ``code``."""
        key = normalize_code(code, field="material_code")
        material = self._materials.get(key)
        if material is None:
            raise NotFoundError("material", key)
        return material

    def of_class(self, material_class: MaterialClass) -> tuple[Material, ...]:
        """Every material of one class, in code order."""
        return tuple(m for m in self if m.material_class is material_class)

    def codes(self) -> tuple[str, ...]:
        """Every material code on file, sorted."""
        return tuple(sorted(self._materials))

    def certify(self, certificate: Certificate) -> Certificate:
        """File a certificate against a material that is already on file."""
        self.get(certificate.material_code)
        filed = self._certificates.setdefault(certificate.material_code, [])
        for existing in filed:
            if existing.reference == certificate.reference:
                raise ConflictError("certificate", certificate.reference)
        filed.append(certificate)
        return certificate

    def certificates_for(self, code: str) -> tuple[Certificate, ...]:
        """Every certificate on file for a material, newest issue first."""
        material = self.get(code)
        filed = self._certificates.get(material.code, [])
        return tuple(sorted(filed, key=lambda c: (c.issued, c.reference), reverse=True))

    def current_certificate(
        self, code: str, kind: CertificateKind, on: date
    ) -> Certificate | None:
        """The certificate of ``kind`` covering ``code`` on ``on``, if any.

        When more than one covers the date the latest issue wins, because that
        is the one a plant would hand over.
        """
        covering = [
            cert
            for cert in self.certificates_for(code)
            if cert.kind is kind and cert.covers(on)
        ]
        if not covering:
            return None
        return max(covering, key=lambda c: (c.issued, c.reference))

    def missing_certificates(self, code: str, on: date) -> tuple[CertificateKind, ...]:
        """Which required certificate kinds are not covered on ``on``."""
        material = self.get(code)
        return tuple(
            kind
            for kind in required_certificates(material)
            if self.current_certificate(material.code, kind, on) is None
        )

    def expiring_soon(self, on: date, *, within_days: int = 21) -> tuple[Certificate, ...]:
        """Certificates that are current but will lapse inside ``within_days``."""
        soon: list[Certificate] = []
        for code in self.codes():
            for cert in self.certificates_for(code):
                if cert.state(on, warning_days=within_days) is CertificateState.EXPIRING:
                    soon.append(cert)
        return tuple(sorted(soon, key=lambda c: (c.expires, c.material_code)))

    def is_batchable(self, code: str, on: date) -> bool:
        """True when ``code`` has every certificate it needs on ``on``."""
        return not self.missing_certificates(code, on)

    def require_batchable(self, code: str, on: date) -> Material:
        """Return the material, or refuse the batch and say what is missing."""
        material = self.get(code)
        missing = self.missing_certificates(material.code, on)
        if missing:
            names = ", ".join(str(kind) for kind in missing)
            raise RuleViolationError(
                "MATERIAL_NOT_CERTIFIED",
                f"{material.code} has no current {names} on {on.isoformat()}",
            )
        return material
