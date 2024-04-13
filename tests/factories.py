"""Builders the test suite shares.

Every module that needs a mix design was building the same five charges and the
same seven materials, and they had already drifted: one had the sand at 1155
and another at 1255, so the same design closed on volume in one file and did
not in another. One set of builders, one set of numbers.

Every builder takes overrides, so a test that cares about one field says only
that field and nothing else.
"""

from __future__ import annotations

from slumpcone.materials.catalog import MaterialCatalog
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
from slumpcone.spec.exposure import ExposureSet
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


def rate(value: float, mass: str = "lb", volume: str = "yd3") -> MassPerVolume:
    """A mass per unit volume, in the customary pair unless told otherwise."""
    return MassPerVolume(value, mass, volume)


def cement(cement_type: CementType = CementType.TYPE_II) -> Material:
    """The plant's portland cement."""
    return Material(
        "CEM-I",
        "Ashfield Type I/II",
        MaterialClass.CEMENT,
        supplier="Ashfield Cement",
        cement_type=cement_type,
        specific_gravity=3.15,
    )


def fly_ash() -> Material:
    """Class F ash, the usual replacement."""
    return Material(
        "SCM-F",
        "Class F ash",
        MaterialClass.SCM,
        scm_kind=ScmKind.FLY_ASH_F,
        specific_gravity=2.35,
    )


def class_c_ash() -> Material:
    """Class C ash, which a sulfate exposure will not accept."""
    return Material(
        "SCM-C",
        "Class C ash",
        MaterialClass.SCM,
        scm_kind=ScmKind.FLY_ASH_C,
        specific_gravity=2.60,
    )


def slag() -> Material:
    """Grade 120 slag cement."""
    return Material(
        "SCM-SL",
        "Grade 120 slag",
        MaterialClass.SCM,
        scm_kind=ScmKind.SLAG_120,
        specific_gravity=2.90,
    )


def coarse() -> Material:
    """A number 57 limestone."""
    return Material(
        "CA-57",
        "Number 57 limestone",
        MaterialClass.COARSE_AGGREGATE,
        specific_gravity=2.68,
        absorption=Percent(0.7),
        nominal_max_size=Quantity(1.0, "in"),
        dry_rodded_unit_weight=rate(101.5, "lb", "ft3"),
    )


def fine() -> Material:
    """A natural concrete sand."""
    return Material(
        "FA-1",
        "Concrete sand",
        MaterialClass.FINE_AGGREGATE,
        specific_gravity=2.63,
        absorption=Percent(1.4),
        fineness_modulus=2.84,
    )


def water(source: WaterSource = WaterSource.POTABLE) -> Material:
    """City water unless the caller wants a reclaimer."""
    return Material("W-1", "Plant water", MaterialClass.WATER, water_source=source)


def air_entrainer() -> Material:
    """A C260 air entraining admixture."""
    return Material(
        "AD-AE",
        "Air entrainer",
        MaterialClass.ADMIXTURE,
        admixture_type=AdmixtureType.AIR_ENTRAINING,
        solids_content=Percent(10.0),
        specific_gravity=1.01,
    )


def water_reducer(
    admixture_type: AdmixtureType = AdmixtureType.TYPE_A_WATER_REDUCING,
) -> Material:
    """A water reducing admixture, type A unless the caller wants a retarder."""
    return Material(
        "AD-WR",
        "Water reducer",
        MaterialClass.ADMIXTURE,
        admixture_type=admixture_type,
        solids_content=Percent(41.0),
        specific_gravity=1.20,
    )


def catalog(cement_type: CementType = CementType.TYPE_II) -> MaterialCatalog:
    """Everything the plant stocks, with no certificates filed."""
    stock = MaterialCatalog()
    stock.add_all(
        [
            cement(cement_type),
            fly_ash(),
            class_c_ash(),
            slag(),
            coarse(),
            fine(),
            water(),
            air_entrainer(),
            water_reducer(),
        ]
    )
    return stock


def gravities() -> dict[str, float]:
    """Specific gravities for every material in :func:`catalog`."""
    return {
        material.code: material.specific_gravity
        for material in catalog()
        if material.specific_gravity is not None
    }


def proportions(
    *,
    water_content: float = 250.0,
    scm: float = 94.0,
    scm_code: str = "SCM-F",
    cementitious: float = 564.0,
    stone: float = 1780.0,
    sand: float = 1255.0,
    air: float = 6.0,
    admixtures: tuple[AdmixtureCharge, ...] | None = None,
) -> Proportions:
    """A four thousand pound paving mix that closes on twenty seven cubic feet."""
    doses = (
        (
            AdmixtureCharge("AD-AE", Quantity(1.2, "floz")),
            AdmixtureCharge("AD-WR", Quantity(4.0, "floz")),
        )
        if admixtures is None
        else admixtures
    )
    return Proportions(
        (
            Charge("CEM-I", MaterialClass.CEMENT, rate(cementitious - scm)),
            Charge(scm_code, MaterialClass.SCM, rate(scm)),
            Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(stone)),
            Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(sand)),
            Charge("W-1", MaterialClass.WATER, rate(water_content)),
        ),
        doses,
        Percent(air),
    )


def design(**overrides: object) -> MixDesign:
    """The paving mix as a filed design."""
    fields: dict[str, object] = {
        "code": "4000P-57",
        "name": "4000 psi paving mix",
        "proportions": proportions(),
        "specified_strength": Quantity(4500, "psi"),
        "nominal_max_size": Quantity(1.0, "in"),
        "slump_target": Quantity(4.0, "in"),
        "exposure": ExposureSet.parse("F2 S1"),
        "plant_code": "PL-1",
    }
    fields.update(overrides)
    return MixDesign(**fields)  # type: ignore[arg-type]
