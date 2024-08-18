"""The profiles that ship with the package.

Four, covering the files a plant actually receives: the batch recorder's own
export, the lab's break results, the field technician's test sheet and the
supplier's delivery list.

They are written against the column names those systems use rather than against
tidy ones, which is why several fields carry three or four candidate columns.
A new plant is usually a new set of candidates on an existing profile rather
than a new profile, and adding one is a one line change here.
"""

from __future__ import annotations

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.ingest.mapping import FieldKind, FieldSpec, MappingProfile
from slumpcone.ingest.pipeline import Validator, one_of, required_together

BATCH_RECORDER = MappingProfile(
    "BATCH-RECORDER",
    "Plant batch recorder export",
    (
        FieldSpec(
            "ticket_number", ("ticket", "ticket_no", "ticket_number", "doc_no"), required=True
        ),
        FieldSpec("plant_code", ("plant", "plant_code", "plant_id"), required=True),
        FieldSpec("mix_code", ("mix", "mix_code", "mix_id", "product"), required=True),
        FieldSpec("mix_revision", ("rev", "revision", "mix_rev"), kind=FieldKind.NUMBER),
        FieldSpec(
            "batched_at",
            ("batched", "batch_time", "load_time", "batched_at"),
            kind=FieldKind.DATETIME,
            required=True,
        ),
        FieldSpec(
            "volume",
            ("volume", "volume_yd3", "qty", "quantity", "cy"),
            kind=FieldKind.QUANTITY,
            unit="yd3",
            required=True,
        ),
        FieldSpec("truck_code", ("truck", "truck_no", "unit")),
        FieldSpec("purchaser", ("customer", "purchaser", "account")),
        FieldSpec("project", ("job", "project", "job_name")),
        FieldSpec(
            "cumulative_volume",
            ("cum_qty", "cumulative", "load_to_date"),
            kind=FieldKind.QUANTITY,
            unit="yd3",
        ),
        FieldSpec(
            "water_held_back",
            ("water_held", "held_water_lb", "water_withheld"),
            kind=FieldKind.QUANTITY,
            unit="lb",
        ),
    ),
)

LAB_BREAKS = MappingProfile(
    "LAB-BREAKS",
    "Laboratory compressive strength results",
    (
        FieldSpec(
            "specimen_code", ("specimen", "cylinder", "specimen_id", "sample_id"), required=True
        ),
        FieldSpec("set_code", ("set", "set_no", "sample_no"), required=True),
        FieldSpec(
            "tested_at",
            ("tested", "test_date", "break_date"),
            kind=FieldKind.DATETIME,
            required=True,
        ),
        FieldSpec("age_days", ("age", "age_days"), kind=FieldKind.NUMBER, required=True),
        FieldSpec(
            "diameter_one",
            ("dia_1", "diameter_1", "d1"),
            kind=FieldKind.QUANTITY,
            unit="in",
        ),
        FieldSpec(
            "diameter_two",
            ("dia_2", "diameter_2", "d2"),
            kind=FieldKind.QUANTITY,
            unit="in",
        ),
        FieldSpec("length", ("length", "len_in", "height"), kind=FieldKind.QUANTITY, unit="in"),
        FieldSpec(
            "max_load",
            ("load", "max_load", "load_lbf", "peak_load"),
            kind=FieldKind.QUANTITY,
            unit="lbf",
            required=True,
        ),
        FieldSpec("fracture", ("fracture", "break_type", "fracture_type")),
        FieldSpec("tested_by", ("tech", "technician", "tested_by")),
    ),
)

FIELD_TESTS = MappingProfile(
    "FIELD-TESTS",
    "Field technician test sheet",
    (
        FieldSpec("ticket_number", ("ticket", "ticket_no"), required=True),
        FieldSpec(
            "taken_at",
            ("time", "sampled", "taken", "sample_time"),
            kind=FieldKind.DATETIME,
            required=True,
        ),
        FieldSpec("slump", ("slump", "slump_in"), kind=FieldKind.QUANTITY, unit="in"),
        FieldSpec("air", ("air", "air_pct", "air_content"), kind=FieldKind.PERCENT),
        FieldSpec(
            "temperature",
            ("temp", "temp_f", "concrete_temp"),
            kind=FieldKind.NUMBER,
        ),
        FieldSpec(
            "unit_weight",
            ("unit_wt", "density", "unit_weight"),
            kind=FieldKind.NUMBER,
        ),
        FieldSpec("technician", ("tech", "technician")),
        FieldSpec("is_retest", ("retest", "is_retest"), kind=FieldKind.BOOLEAN, default="no"),
    ),
)

MATERIAL_RECEIPTS = MappingProfile(
    "MATERIAL-RECEIPTS",
    "Supplier delivery list",
    (
        FieldSpec("reference", ("ref", "reference", "receipt_no"), required=True),
        FieldSpec("plant_code", ("plant", "plant_code"), required=True),
        FieldSpec("silo_code", ("silo", "bin", "vessel"), required=True),
        FieldSpec("material_code", ("material", "product", "material_code"), required=True),
        FieldSpec(
            "received_at",
            ("received", "delivery_time", "date"),
            kind=FieldKind.DATETIME,
            required=True,
        ),
        FieldSpec(
            "quantity",
            ("weight", "net_weight", "quantity_lb", "net_lb"),
            kind=FieldKind.QUANTITY,
            unit="lb",
            required=True,
        ),
        FieldSpec("supplier", ("supplier", "vendor")),
        FieldSpec("supplier_ticket", ("supplier_ticket", "bol", "bol_no")),
        FieldSpec("certificate_reference", ("cert", "certificate", "mill_cert")),
    ),
)

PROFILES: tuple[MappingProfile, ...] = (
    BATCH_RECORDER,
    LAB_BREAKS,
    FIELD_TESTS,
    MATERIAL_RECEIPTS,
)


def profile(code: str) -> MappingProfile:
    """One shipped profile by code."""
    key = normalize_code(code, field="profile_code")
    for candidate in PROFILES:
        if candidate.code == key:
            return candidate
    raise NotFoundError("mapping profile", key)


def codes() -> tuple[str, ...]:
    """Every shipped profile code, sorted."""
    return tuple(sorted(candidate.code for candidate in PROFILES))


def validators_for(code: str) -> tuple[Validator, ...]:
    """The extra checks a profile's rows have to pass.

    The lab profile is the one that needs them. A break with one diameter and
    not the other cannot be turned into a strength, and a cylinder with no
    dimensions at all is a load reading rather than a break.
    """
    chosen = profile(code)
    if chosen.code == LAB_BREAKS.code:
        return (
            required_together("diameter_one", "diameter_two"),
            one_of("diameter_one", "length"),
        )
    if chosen.code == FIELD_TESTS.code:
        return (one_of("slump", "air", "temperature", "unit_weight"),)
    return ()
