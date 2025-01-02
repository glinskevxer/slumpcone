"""Reading and writing materials and their certificates.

Every quantity is stored in one unit and one unit only, whatever the plant
prints in. Specific gravity is dimensionless, absorption is a percentage,
nominal maximum size is millimetres and dry rodded weight is pounds per cubic
foot. A column that can hold either unit system is a column nobody can query.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.materials.catalog import MaterialCatalog
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
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

_COLUMNS = (
    "code",
    "name",
    "material_class",
    "supplier",
    "source",
    "specific_gravity",
    "absorption_percent",
    "fineness_modulus",
    "nominal_max_size_mm",
    "dry_rodded_lb_per_ft3",
    "cement_type",
    "scm_kind",
    "admixture_type",
    "solids_percent",
    "water_source",
    "chloride_percent",
    "alkali_percent",
    "notes",
)


def _to_row(material: Material) -> dict[str, object]:
    return {
        "code": material.code,
        "name": material.name,
        "material_class": material.material_class.value,
        "supplier": material.supplier,
        "source": material.source,
        "specific_gravity": material.specific_gravity,
        "absorption_percent": None
        if material.absorption is None
        else material.absorption.value,
        "fineness_modulus": material.fineness_modulus,
        "nominal_max_size_mm": (
            None
            if material.nominal_max_size is None
            else material.nominal_max_size.to("mm").value
        ),
        "dry_rodded_lb_per_ft3": (
            None
            if material.dry_rodded_unit_weight is None
            else material.dry_rodded_unit_weight.to("lb", "ft3").value
        ),
        "cement_type": None if material.cement_type is None else material.cement_type.value,
        "scm_kind": None if material.scm_kind is None else material.scm_kind.value,
        "admixture_type": (
            None if material.admixture_type is None else material.admixture_type.value
        ),
        "solids_percent": (
            None if material.solids_content is None else material.solids_content.value
        ),
        "water_source": None if material.water_source is None else material.water_source.value,
        "chloride_percent": (
            None if material.chloride_content is None else material.chloride_content.value
        ),
        "alkali_percent": (
            None if material.alkali_content is None else material.alkali_content.value
        ),
        "notes": material.notes,
    }


def _from_row(row: sqlite3.Row) -> Material:
    return Material(
        code=str(row["code"]),
        name=str(row["name"]),
        material_class=MaterialClass(str(row["material_class"])),
        supplier=None if row["supplier"] is None else str(row["supplier"]),
        source=None if row["source"] is None else str(row["source"]),
        specific_gravity=(
            None if row["specific_gravity"] is None else float(row["specific_gravity"])
        ),
        absorption=(
            None
            if row["absorption_percent"] is None
            else Percent(float(row["absorption_percent"]))
        ),
        fineness_modulus=(
            None if row["fineness_modulus"] is None else float(row["fineness_modulus"])
        ),
        nominal_max_size=(
            None
            if row["nominal_max_size_mm"] is None
            else Quantity(float(row["nominal_max_size_mm"]), "mm")
        ),
        dry_rodded_unit_weight=(
            None
            if row["dry_rodded_lb_per_ft3"] is None
            else MassPerVolume(float(row["dry_rodded_lb_per_ft3"]), "lb", "ft3")
        ),
        cement_type=None if row["cement_type"] is None else CementType(str(row["cement_type"])),
        scm_kind=None if row["scm_kind"] is None else ScmKind(str(row["scm_kind"])),
        admixture_type=(
            None if row["admixture_type"] is None else AdmixtureType(str(row["admixture_type"]))
        ),
        solids_content=(
            None if row["solids_percent"] is None else Percent(float(row["solids_percent"]))
        ),
        water_source=(
            None if row["water_source"] is None else WaterSource(str(row["water_source"]))
        ),
        chloride_content=(
            None if row["chloride_percent"] is None else Percent(float(row["chloride_percent"]))
        ),
        alkali_content=(
            None if row["alkali_percent"] is None else Percent(float(row["alkali_percent"]))
        ),
        notes=str(row["notes"]),
    )


def _certificate_from_row(row: sqlite3.Row) -> Certificate:
    return Certificate(
        material_code=str(row["material_code"]),
        kind=CertificateKind(str(row["kind"])),
        reference=str(row["reference"]),
        issued=date.fromisoformat(str(row["issued"])),
        expires=date.fromisoformat(str(row["expires"])),
        issuer=None if row["issuer"] is None else str(row["issuer"]),
        lot=None if row["lot"] is None else str(row["lot"]),
    )


class MaterialRepository:
    """Materials and certificates, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, material: Material) -> Material:
        """Insert or update a material by code."""
        row = _to_row(material)
        placeholders = ", ".join(f":{name}" for name in _COLUMNS)
        assignments = ", ".join(f"{name} = :{name}" for name in _COLUMNS if name != "code")
        self._db.execute(
            f"INSERT INTO material ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(code) DO UPDATE SET {assignments}",
            row,
        )
        return material

    def save_all(self, materials: list[Material]) -> None:
        """Save several materials in one transaction."""
        with self._db.transaction():
            for material in materials:
                self.save(material)

    def get(self, code: str) -> Material:
        """The material filed under ``code``."""
        key = normalize_code(code, field="material_code")
        row = self._db.query_one("SELECT * FROM material WHERE code = ?", (key,))
        if row is None:
            raise NotFoundError("material", key)
        return _from_row(row)

    def find(self, code: str) -> Material | None:
        """The material, or ``None`` when it is not on file."""
        key = normalize_code(code, field="material_code")
        row = self._db.query_one("SELECT * FROM material WHERE code = ?", (key,))
        return None if row is None else _from_row(row)

    def all(self) -> tuple[Material, ...]:
        """Every material, in code order."""
        rows = self._db.query("SELECT * FROM material ORDER BY code")
        return tuple(_from_row(row) for row in rows)

    def of_class(self, material_class: MaterialClass) -> tuple[Material, ...]:
        """Every material of one class, in code order."""
        rows = self._db.query(
            "SELECT * FROM material WHERE material_class = ? ORDER BY code",
            (material_class.value,),
        )
        return tuple(_from_row(row) for row in rows)

    def delete(self, code: str) -> None:
        """Remove a material and everything filed against it."""
        key = normalize_code(code, field="material_code")
        cursor = self._db.execute("DELETE FROM material WHERE code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("material", key)

    def save_certificate(self, certificate: Certificate) -> Certificate:
        """File a certificate, replacing one with the same reference."""
        self.get(certificate.material_code)
        self._db.execute(
            "INSERT INTO material_certificate "
            "(material_code, kind, reference, issued, expires, issuer, lot) "
            "VALUES (:material_code, :kind, :reference, :issued, :expires, :issuer, :lot) "
            "ON CONFLICT(material_code, reference) DO UPDATE SET "
            "kind = :kind, issued = :issued, expires = :expires, issuer = :issuer, lot = :lot",
            {
                "material_code": certificate.material_code,
                "kind": certificate.kind.value,
                "reference": certificate.reference,
                "issued": certificate.issued.isoformat(),
                "expires": certificate.expires.isoformat(),
                "issuer": certificate.issuer,
                "lot": certificate.lot,
            },
        )
        return certificate

    def certificates_for(self, code: str) -> tuple[Certificate, ...]:
        """Every certificate on file for a material, newest issue first."""
        key = normalize_code(code, field="material_code")
        rows = self._db.query(
            "SELECT * FROM material_certificate WHERE material_code = ? "
            "ORDER BY issued DESC, reference DESC",
            (key,),
        )
        return tuple(_certificate_from_row(row) for row in rows)

    def load_catalog(self) -> MaterialCatalog:
        """Everything on file, as an in-memory catalogue."""
        catalog = MaterialCatalog()
        for material in self.all():
            catalog.add(material)
            for certificate in self.certificates_for(material.code):
                catalog.certify(certificate)
        return catalog
