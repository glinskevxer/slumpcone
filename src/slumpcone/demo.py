"""A worked example, filed into a register.

Every part of this package needs the same handful of records to do anything at
all: a plant with scales, materials with paper on them, a mix design, a job and
a few loads. Building those by hand is twenty commands, which makes trying
anything out a chore and makes the smoke test in CI a wall of arguments.

The example is one plant, one paving mixture and one day's work, with a load
that fails its slump and a set of cylinders that comes out low, because a demo
register where everything passes shows none of the reports doing anything.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.moisture import AggregateMoisture
from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.delivery.truck import Truck
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.materials.certification import Certificate, CertificateKind
from slumpcone.materials.kinds import (
    AdmixtureType,
    CementType,
    MaterialClass,
    ScmKind,
    WaterSource,
)
from slumpcone.materials.spec import Material
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.plant.plant import Plant
from slumpcone.plant.scale import Scale
from slumpcone.plant.silo import Silo
from slumpcone.project.project import Project, SpecifiedClass
from slumpcone.register import Register
from slumpcone.spec.exposure import ExposureSet
from slumpcone.strength.breaks import BreakResult
from slumpcone.strength.specimen import Specimen, SpecimenSize
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

DEMO_DAY = date(2024, 6, 12)
DEMO_PLANT = "PL-1"
DEMO_MIX = "4000P-57"
DEMO_PROJECT = "P-2024-118"
DEMO_PLACEMENT = "Route 9 shoulder"


def _materials() -> tuple[Material, ...]:
    return (
        Material(
            "CEM-I",
            "Ashfield Type I/II",
            MaterialClass.CEMENT,
            supplier="Ashfield Cement",
            cement_type=CementType.TYPE_II,
            specific_gravity=3.15,
        ),
        Material(
            "SCM-F",
            "Class F ash",
            MaterialClass.SCM,
            scm_kind=ScmKind.FLY_ASH_F,
            specific_gravity=2.35,
        ),
        Material(
            "CA-57",
            "Number 57 limestone",
            MaterialClass.COARSE_AGGREGATE,
            specific_gravity=2.68,
            absorption=Percent(0.7),
            nominal_max_size=Quantity(1.0, "in"),
            dry_rodded_unit_weight=MassPerVolume(101.5, "lb", "ft3"),
        ),
        Material(
            "FA-1",
            "Concrete sand",
            MaterialClass.FINE_AGGREGATE,
            specific_gravity=2.63,
            absorption=Percent(1.4),
            fineness_modulus=2.84,
        ),
        Material("W-1", "Plant water", MaterialClass.WATER, water_source=WaterSource.POTABLE),
        Material(
            "AD-AE",
            "Air entrainer",
            MaterialClass.ADMIXTURE,
            admixture_type=AdmixtureType.AIR_ENTRAINING,
            solids_content=Percent(10.0),
            specific_gravity=1.01,
        ),
        Material(
            "AD-WR",
            "Water reducer",
            MaterialClass.ADMIXTURE,
            admixture_type=AdmixtureType.TYPE_A_WATER_REDUCING,
            solids_content=Percent(41.0),
            specific_gravity=1.20,
        ),
    )


def _certificates() -> tuple[Certificate, ...]:
    issued = date(2024, 1, 2)
    expires = date(2024, 12, 31)
    wanted = (
        ("CEM-I", CertificateKind.MILL_CERTIFICATE),
        ("SCM-F", CertificateKind.MILL_CERTIFICATE),
        ("CA-57", CertificateKind.SOURCE_APPROVAL),
        ("CA-57", CertificateKind.GRADATION),
        ("FA-1", CertificateKind.SOURCE_APPROVAL),
        ("FA-1", CertificateKind.GRADATION),
        ("AD-AE", CertificateKind.CONFORMANCE_LETTER),
        ("AD-WR", CertificateKind.CONFORMANCE_LETTER),
    )
    return tuple(
        Certificate(code, kind, f"{code}-{kind.value[:4].upper()}", issued, expires)
        for code, kind in wanted
    )


def _plant() -> Plant:
    return Plant(
        DEMO_PLANT,
        "Northmoor batch plant",
        scales=(
            Scale(
                "SC-CEM",
                "Cement hopper scale",
                Quantity(6000, "lb"),
                Quantity(1, "lb"),
                (MaterialClass.CEMENT, MaterialClass.SCM),
                date(2024, 3, 1),
            ),
            Scale(
                "SC-AGG",
                "Aggregate hopper scale",
                Quantity(12000, "lb"),
                Quantity(2, "lb"),
                (MaterialClass.COARSE_AGGREGATE, MaterialClass.FINE_AGGREGATE),
                date(2024, 3, 1),
            ),
        ),
        max_load=Quantity(11, "yd3"),
        certification_expires=date(2025, 1, 31),
        location="Ashfield",
    )


def _silos() -> tuple[Silo, ...]:
    return (
        Silo(
            "SI-1",
            "Cement silo one",
            "CEM-I",
            Quantity(200000, "lb"),
            Quantity(120000, "lb"),
            Quantity(30000, "lb"),
        ),
        Silo(
            "SI-2",
            "Ash silo",
            "SCM-F",
            Quantity(120000, "lb"),
            Quantity(40000, "lb"),
            Quantity(20000, "lb"),
        ),
    )


def _design() -> MixDesign:
    proportions = Proportions(
        (
            Charge("CEM-I", MaterialClass.CEMENT, MassPerVolume(470, "lb", "yd3")),
            Charge("SCM-F", MaterialClass.SCM, MassPerVolume(94, "lb", "yd3")),
            Charge("CA-57", MaterialClass.COARSE_AGGREGATE, MassPerVolume(1780, "lb", "yd3")),
            Charge("FA-1", MaterialClass.FINE_AGGREGATE, MassPerVolume(1255, "lb", "yd3")),
            Charge("W-1", MaterialClass.WATER, MassPerVolume(250, "lb", "yd3")),
        ),
        (
            AdmixtureCharge("AD-AE", Quantity(1.2, "floz")),
            AdmixtureCharge("AD-WR", Quantity(4.0, "floz")),
        ),
        Percent(6.0),
    )
    return MixDesign(
        code=DEMO_MIX,
        name="4000 psi paving mix",
        proportions=proportions,
        specified_strength=Quantity(4500, "psi"),
        nominal_max_size=Quantity(1.0, "in"),
        slump_target=Quantity(4.0, "in"),
        exposure=ExposureSet.parse("F2 S1"),
        plant_code=DEMO_PLANT,
    )


def _project() -> Project:
    return Project(
        DEMO_PROJECT,
        "Route 9 shoulder widening",
        classes=(
            SpecifiedClass(
                "SLAB",
                Quantity(4000, "psi"),
                exposure=ExposureSet.parse("F2 S1"),
                nominal_max_size=Quantity(1.0, "in"),
                description="paving slab",
            ),
        ),
        owner="County highways",
        specifier="Harlow Engineering",
        started_on=date(2024, 5, 1),
        finished_on=date(2024, 11, 30),
    )


def seed(register: Register) -> dict[str, int]:
    """File the worked example, returning how much of each kind was written."""
    materials = _materials()
    register.materials.save_all(list(materials))
    for certificate in _certificates():
        register.materials.save_certificate(certificate)
    plant = _plant()
    register.plants.save(plant, _silos())
    design = _design()
    register.mixes.save(design)
    register.projects.save(_project())
    register.deliveries.save_truck(
        Truck(
            "TR-114",
            Quantity(11, "yd3"),
            fleet="Northmoor",
            last_uniformity_test=date(2024, 2, 1),
        )
    )
    catalog = register.materials.load_catalog()
    moistures = {
        "CA-57": AggregateMoisture("CA-57", Percent(1.5), Percent(0.7)),
        "FA-1": AggregateMoisture("FA-1", Percent(5.0), Percent(1.4)),
    }
    tickets = 0
    for index in range(4):
        batched_at = datetime(2024, 6, 12, 7, 42) + timedelta(minutes=35 * index)
        planned = plan_batch(plant, design, catalog, Quantity(9, "yd3"), DEMO_DAY, moistures)
        ticket = BatchTicket.from_plan(
            planned,
            f"88120{index + 4}",
            batched_at,
            {"CEM-I": Quantity(4230 + index * 40, "lb")},
            None,
            truck_code="TR-114",
            purchaser="Ashfield Paving",
            project=DEMO_PLACEMENT,
        )
        register.batches.save(ticket)
        register.deliveries.save(
            Delivery(
                ticket.number,
                "TR-114",
                batched_at,
                left_plant_at=batched_at + timedelta(minutes=6),
                arrived_at=batched_at + timedelta(minutes=28),
                discharge_started_at=batched_at + timedelta(minutes=35),
                discharge_finished_at=batched_at + timedelta(minutes=52 + index * 12),
                revolutions_on_arrival=140,
                revolutions_at_discharge=210 + index * 20,
            )
        )
        tickets += 1
        taken_at = batched_at + timedelta(minutes=38)
        slump = 4.0 if index != 2 else 7.5
        register.fresh.save_all(
            [
                FreshTest(
                    ticket.number,
                    FreshTestKind.SLUMP,
                    taken_at,
                    slump=Quantity(slump, "in"),
                    technician="TECH-7",
                ),
                FreshTest(
                    ticket.number,
                    FreshTestKind.AIR_PRESSURE,
                    taken_at,
                    air=Percent(6.2),
                    technician="TECH-7",
                ),
                FreshTest(
                    ticket.number,
                    FreshTestKind.UNIT_WEIGHT,
                    taken_at,
                    unit_weight=MassPerVolume(142.6, "lb", "ft3"),
                    technician="TECH-7",
                ),
            ]
        )
    sets = 0
    for index, strength in enumerate((4900.0, 4700.0, 3300.0)):
        set_code = f"S-447{index + 1}"
        sampled = datetime(2024, 6, 12 + index, 9, 20)
        register.strength.open_set(
            set_code,
            DEMO_MIX,
            1,
            sampled,
            size=SpecimenSize.CYL_6X12,
            ticket_number="881204",
            project=DEMO_PLACEMENT,
        )
        for letter in ("A", "B"):
            code = f"C-{set_code}-{letter}"
            register.strength.save_specimen(
                Specimen(code, set_code, "881204", sampled, SpecimenSize.CYL_6X12)
            )
            register.strength.save_break(
                BreakResult(
                    code,
                    sampled + timedelta(days=28),
                    28.0,
                    Quantity(6.0, "in"),
                    Quantity(6.0, "in"),
                    Quantity(12.0, "in"),
                    Quantity(strength * 28.274333882308138, "lbf"),
                    tested_by="TECH-7",
                )
            )
        sets += 1
    return {
        "materials": len(materials),
        "tickets": tickets,
        "specimen sets": sets,
    }
