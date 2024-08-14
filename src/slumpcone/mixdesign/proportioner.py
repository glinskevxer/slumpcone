"""Proportioning a mixture from the tables, in the order the method runs.

Eight steps and the order matters, because each one narrows what the next can
choose. Water demand comes from the slump and the aggregate. The ratio comes
from the strength, and then whichever of the table ratio and the specified
limit is tighter wins. Cementitious content falls out of those two and then has
to clear whatever floor the specification puts under it, which can push the
ratio back down again below what the strength alone asked for.

Coarse aggregate is chosen by bulk volume from a table and converted to a
weight through its dry rodded unit weight. Sand is whatever absolute volume is
left, which is why every earlier step has to be right: the sand absorbs every
error made above it, and a mixture with the wrong sand weight still closes on
twenty seven cubic feet.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.materials.spec import Material
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.mixdesign.tables import (
    ExposureSeverity,
    coarse_aggregate_factor,
    entrapped_air,
    ratio_for_strength,
    target_air,
    water_demand,
)
from slumpcone.mixdesign.volumes import WATER_DENSITY, absolute_volume
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

CUBIC_FEET_PER_YARD = 27.0


@dataclass(frozen=True, slots=True)
class ProportioningRequest:
    """Everything the method needs to propose a mixture."""

    required_average_strength: Quantity
    slump_target: Quantity
    cement: Material
    coarse: Material
    fine: Material
    water: Material
    scm: Material | None = None
    scm_replacement: Percent = Percent(0.0)
    air_entrained: bool = True
    severity: ExposureSeverity = ExposureSeverity.MODERATE
    max_water_cementitious: float | None = None
    min_cementitious: Quantity | None = None
    admixtures: tuple[AdmixtureCharge, ...] = ()

    def __post_init__(self) -> None:
        if self.coarse.material_class is not MaterialClass.COARSE_AGGREGATE:
            raise ValidationError(
                "the coarse material is not a coarse aggregate", field="coarse"
            )
        if self.fine.material_class is not MaterialClass.FINE_AGGREGATE:
            raise ValidationError("the fine material is not a fine aggregate", field="fine")
        if self.cement.material_class is not MaterialClass.CEMENT:
            raise ValidationError("the cement material is not a cement", field="cement")
        if self.scm is not None and self.scm.material_class is not MaterialClass.SCM:
            raise ValidationError("the scm material is not an scm", field="scm")
        if self.coarse.dry_rodded_unit_weight is None:
            raise ValidationError(
                "a coarse aggregate needs a dry rodded unit weight to be proportioned",
                field="coarse",
            )
        if self.coarse.nominal_max_size is None:
            raise ValidationError(
                "a coarse aggregate needs a nominal maximum size", field="coarse"
            )
        if self.fine.fineness_modulus is None:
            raise ValidationError("a fine aggregate needs a fineness modulus", field="fine")
        if not 0.0 <= self.scm_replacement.value < 100.0:
            raise ValidationError(
                "an scm replacement is a share of the binder", field="scm_replacement"
            )
        if self.scm is None and self.scm_replacement:
            raise ValidationError("there is a replacement percentage but no scm", field="scm")


@dataclass(frozen=True, slots=True)
class ProportioningResult:
    """The mixture the method produced, and how it got there."""

    proportions: Proportions
    water_cementitious: float
    air: Percent
    steps: tuple[str, ...]

    def describe(self) -> str:
        """The working, as a plain text list."""
        return "\n".join(self.steps)


def proportion(request: ProportioningRequest) -> ProportioningResult:
    """Run the method and return the mixture it produces."""
    size = request.coarse.nominal_max_size
    assert size is not None
    steps: list[str] = []

    water = water_demand(size, request.slump_target, air_entrained=request.air_entrained)
    steps.append(
        f"water demand for a {request.slump_target.format(1)} slump on a "
        f"{size.format(2)} aggregate is {water.format(0)}"
    )

    air = target_air(size, request.severity) if request.air_entrained else entrapped_air(size)
    steps.append(
        f"air is {air.format(1)} "
        f"({'entrained, ' + str(request.severity) if request.air_entrained else 'entrapped'})"
    )

    from_table = ratio_for_strength(
        request.required_average_strength, air_entrained=request.air_entrained
    )
    ratio = from_table
    if request.max_water_cementitious is not None:
        ratio = min(ratio, request.max_water_cementitious)
        steps.append(
            f"ratio from strength is {from_table:.3f}, the specification allows "
            f"{request.max_water_cementitious:.2f}, so {ratio:.3f} governs"
        )
    else:
        steps.append(f"ratio from strength is {ratio:.3f}")

    cementitious = water * (1.0 / ratio)
    floor = request.min_cementitious
    if floor is not None:
        as_rate = MassPerVolume(floor.to("lb").value, "lb", "yd3")
        if as_rate > cementitious:
            cementitious = as_rate
            ratio = water.ratio_to(cementitious)
            steps.append(
                f"the {floor.format(0)} cementitious floor raises the content and "
                f"drops the ratio to {ratio:.3f}"
            )
    steps.append(f"cementitious content is {cementitious.format(0)}")

    scm_content = cementitious * request.scm_replacement.fraction
    cement_content = cementitious - scm_content
    if request.scm is not None:
        steps.append(
            f"{request.scm_replacement.format(0)} of the binder is "
            f"{request.scm.code}, so {cement_content.format(0)} cement and "
            f"{scm_content.format(0)} scm"
        )

    factor = coarse_aggregate_factor(size, request.fine.fineness_modulus or 0.0)
    dry_rodded = request.coarse.dry_rodded_unit_weight
    assert dry_rodded is not None
    coarse_weight = MassPerVolume(
        factor * CUBIC_FEET_PER_YARD * dry_rodded.to("lb", "ft3").value, "lb", "yd3"
    )
    steps.append(
        f"coarse aggregate factor is {factor:.3f} bulk volume, which is "
        f"{coarse_weight.format(0)}"
    )

    one_yard = Quantity(1.0, "yd3")
    used = Quantity.zero("ft3")
    for material, content in (
        (request.cement, cement_content),
        (request.scm, scm_content),
        (request.coarse, coarse_weight),
    ):
        if material is None or content.is_zero():
            continue
        gravity = material.specific_gravity
        if gravity is None:
            raise ValidationError(
                f"{material.code} has no specific gravity", field="specific_gravity"
            )
        used = used + absolute_volume(content.times(one_yard), gravity)
    used = used + absolute_volume(water.times(one_yard), 1.0)
    used = used + Quantity(air.of(CUBIC_FEET_PER_YARD), "ft3")

    fine_volume = Quantity(CUBIC_FEET_PER_YARD, "ft3") - used
    if fine_volume.value <= 0.0:
        raise ValidationError(
            "the mixture is over full before any sand goes in; check the coarse "
            "aggregate factor and the water demand",
            field="fine",
        )
    fine_gravity = request.fine.specific_gravity
    if fine_gravity is None:
        raise ValidationError("the sand has no specific gravity", field="fine")
    fine_weight = MassPerVolume(
        fine_volume.value * fine_gravity * WATER_DENSITY.to("lb", "ft3").value,
        "lb",
        "yd3",
    )
    steps.append(
        f"sand fills the remaining {fine_volume.format(2)}, which is {fine_weight.format(0)}"
    )

    charges = [
        Charge(request.cement.code, MaterialClass.CEMENT, cement_content),
        Charge(request.coarse.code, MaterialClass.COARSE_AGGREGATE, coarse_weight),
        Charge(request.fine.code, MaterialClass.FINE_AGGREGATE, fine_weight),
        Charge(request.water.code, MaterialClass.WATER, water),
    ]
    if request.scm is not None and not scm_content.is_zero():
        charges.insert(1, Charge(request.scm.code, MaterialClass.SCM, scm_content))
    proportions = Proportions(tuple(charges), request.admixtures, air)
    return ProportioningResult(proportions, ratio, air, tuple(steps))
