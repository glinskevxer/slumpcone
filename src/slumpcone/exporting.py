"""Getting things back out: delimited text, and a mix design as JSON.

Two different jobs. The delimited export is for somebody who wants the numbers
in a spreadsheet, so it is flat, quoted properly and carries units in the
column headings rather than in the cells.

The JSON is for a mixture moving between plants, and it round trips: what comes
out of a register goes back into another one as the same design. That means
every field the design carries has to be in it, including the ones a report
would leave out, and it means the reader has to refuse a document it does not
fully understand rather than filling the gaps in with defaults.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from typing import Any

from slumpcone.batching.ticket import BatchTicket
from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.materials.spec import Material
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.strength.tests import StrengthTest
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# The version of the exchange document. A reader refuses anything it does not
# recognise rather than guessing at a newer shape.
DOCUMENT_VERSION = 1


def to_delimited(
    headings: Sequence[str], rows: Iterable[Sequence[object]], *, delimiter: str = ","
) -> str:
    """Write rows out as delimited text, quoting whatever needs it."""
    if not headings:
        raise ValidationError("an export needs at least one column", field="headings")
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerow(list(headings))
    for row in rows:
        if len(row) != len(headings):
            raise ValidationError(
                f"a row has {len(row)} cells and the export has {len(headings)} columns",
                field="rows",
            )
        writer.writerow(["" if cell is None else cell for cell in row])
    return buffer.getvalue()


def tickets_to_delimited(tickets: Sequence[BatchTicket], **options: Any) -> str:
    """Delivery tickets as a flat table."""
    headings = (
        "ticket",
        "plant",
        "mix",
        "revision",
        "batched_at",
        "volume_yd3",
        "truck",
        "purchaser",
        "project",
        "findings",
    )
    rows = [
        [
            ticket.number,
            ticket.plant_code,
            ticket.mix_code,
            ticket.mix_revision,
            ticket.batched_at.isoformat(),
            f"{ticket.volume.to('yd3').value:.2f}",
            ticket.truck_code,
            ticket.purchaser,
            ticket.project,
            len(ticket.out_of_tolerance),
        ]
        for ticket in tickets
    ]
    return to_delimited(headings, rows, **options)


def strength_to_delimited(tests: Sequence[StrengthTest], **options: Any) -> str:
    """Strength tests as a flat table."""
    headings = (
        "set",
        "mix",
        "tested_on",
        "age_days",
        "result_psi",
        "lowest_psi",
        "highest_psi",
        "spread_pct",
        "cylinders",
        "counts_for_acceptance",
    )
    rows = [
        [
            test.set_code,
            test.mix_code,
            test.tested_on.isoformat(),
            f"{test.age_days:g}",
            f"{test.average.to('psi').value:.0f}",
            f"{test.lowest.to('psi').value:.0f}",
            f"{test.highest.to('psi').value:.0f}",
            f"{test.within_test_range_percent.value:.1f}",
            len(test.breaks),
            "yes" if test.counts_for_acceptance else "no",
        ]
        for test in tests
    ]
    return to_delimited(headings, rows, **options)


def materials_to_delimited(materials: Sequence[Material], **options: Any) -> str:
    """The catalogue as a flat table."""
    headings = (
        "code",
        "name",
        "class",
        "supplier",
        "specific_gravity",
        "absorption_pct",
        "fineness_modulus",
        "chloride_pct",
        "alkali_pct",
    )
    rows = [
        [
            material.code,
            material.name,
            str(material.material_class),
            material.supplier,
            material.specific_gravity,
            None if material.absorption is None else material.absorption.value,
            material.fineness_modulus,
            None if material.chloride_content is None else material.chloride_content.value,
            None if material.alkali_content is None else material.alkali_content.value,
        ]
        for material in materials
    ]
    return to_delimited(headings, rows, **options)


def _band_json(band: Band | None) -> dict[str, float | None] | None:
    if band is None:
        return None
    return {"target": band.target, "minus": band.minus, "plus": band.plus}


def _band_from_json(raw: dict[str, Any] | None) -> Band | None:
    if raw is None:
        return None
    return Band(float(raw["target"]), raw["minus"], raw["plus"])


def mix_to_json(design: MixDesign) -> str:
    """A mix design as an exchange document."""
    document = {
        "document": "slumpcone.mixdesign",
        "version": DOCUMENT_VERSION,
        "code": design.code,
        "name": design.name,
        "revision": design.revision,
        "plant_code": design.plant_code,
        "specified_strength_psi": design.specified_strength.to("psi").value,
        "test_age_days": design.test_age_days,
        "nominal_max_size_mm": design.nominal_max_size.to("mm").value,
        "slump_target_in": design.slump_target.to("in").value,
        "slump_band": _band_json(design.slump_band),
        "air_band": _band_json(design.air_band),
        "exposure": str(design.exposure),
        "design_air_pct": design.design_air.value,
        "mass_unit": design.proportions.mass_unit,
        "volume_unit": design.proportions.volume_unit,
        "charges": [
            {
                "material_code": charge.material_code,
                "material_class": charge.material_class.value,
                "content": charge.content.value,
            }
            for charge in design.proportions.charges
        ],
        "admixtures": [
            {
                "material_code": dose.material_code,
                "dose_floz_per_cwt": dose.dose_per_cwt.to("floz").value,
            }
            for dose in design.proportions.admixtures
        ],
        "notes": design.notes,
    }
    return json.dumps(document, indent=2, sort_keys=True)


def mix_from_json(text: str) -> MixDesign:
    """Read an exchange document back into a mix design."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"the document is not JSON: {exc}", field="document") from exc
    if not isinstance(document, dict):
        raise ValidationError("the document is not an object", field="document")
    if document.get("document") != "slumpcone.mixdesign":
        raise ValidationError("this is not a mix design document", field="document")
    version = document.get("version")
    if version != DOCUMENT_VERSION:
        raise ValidationError(
            f"this build reads version {DOCUMENT_VERSION} documents and that one is "
            f"version {version}",
            field="version",
        )
    mass_unit = str(document["mass_unit"])
    volume_unit = str(document["volume_unit"])
    charges = tuple(
        Charge(
            str(entry["material_code"]),
            MaterialClass(str(entry["material_class"])),
            MassPerVolume(float(entry["content"]), mass_unit, volume_unit),
        )
        for entry in document["charges"]
    )
    admixtures = tuple(
        AdmixtureCharge(
            str(entry["material_code"]),
            Quantity(float(entry["dose_floz_per_cwt"]), "floz"),
        )
        for entry in document.get("admixtures", [])
    )
    proportions = Proportions(charges, admixtures, Percent(float(document["design_air_pct"])))
    return MixDesign(
        code=str(document["code"]),
        name=str(document["name"]),
        proportions=proportions,
        specified_strength=Quantity(float(document["specified_strength_psi"]), "psi"),
        nominal_max_size=Quantity(float(document["nominal_max_size_mm"]), "mm"),
        slump_target=Quantity(float(document["slump_target_in"]), "in"),
        test_age_days=int(document["test_age_days"]),
        slump_band=_band_from_json(document.get("slump_band")),
        air_band=_band_from_json(document.get("air_band")),
        exposure=ExposureSet.parse(str(document["exposure"])),
        revision=int(document["revision"]),
        plant_code=(
            None if document.get("plant_code") is None else str(document["plant_code"])
        ),
        notes=str(document.get("notes", "")),
    )
