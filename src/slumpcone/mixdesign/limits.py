"""Checking a mix design against everything that constrains it.

Four sources of constraint and they do not agree with each other. The exposure
classes cap the water-cementitious ratio and floor the strength. The freeze
thaw class floors the air. F3 caps how much of the binder may be replaced, by
material and in total. And the proportions themselves have to close on the unit
volume they claim.

Every finding names the rule that produced it. A plant told its ratio is too
high and not told which class said so cannot do anything with that.
"""

from __future__ import annotations

from dataclasses import dataclass

from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import MaterialClass, ScmKind
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.volumes import check_yield
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureClass

# ACI's caps on replacement for concrete exposed to deicing chemicals. The
# individual caps and the total are separate rules and a mixture can pass every
# individual one and still fail the total.
F3_REPLACEMENT_CAPS: dict[str, Percent] = {
    "fly_ash": Percent(25.0),
    "slag": Percent(50.0),
    "silica_fume": Percent(10.0),
    "total": Percent(50.0),
}


@dataclass(frozen=True, slots=True)
class LimitFinding:
    """One rule a mix design does not satisfy."""

    code: str
    detail: str
    governing: str | None = None

    def describe(self) -> str:
        """One line naming the rule and, where there is one, its source."""
        if self.governing is None:
            return f"{self.code}: {self.detail}"
        return f"{self.code}: {self.detail} [{self.governing}]"

    def __str__(self) -> str:
        return self.describe()


def _replacement_family(kind: ScmKind) -> str:
    if kind.is_fly_ash or kind in {ScmKind.NATURAL_POZZOLAN, ScmKind.METAKAOLIN}:
        return "fly_ash"
    if kind.is_slag:
        return "slag"
    return "silica_fume"


def check_ratio(design: MixDesign) -> tuple[LimitFinding, ...]:
    """The water-cementitious ratio against the tightest exposure limit."""
    limit = design.exposure.max_water_cementitious
    if limit is None:
        return ()
    actual = design.water_cementitious_ratio
    if actual <= limit + 1e-9:
        return ()
    governing = design.exposure.governing_class("max_water_cementitious")
    return (
        LimitFinding(
            "WCM_ABOVE_LIMIT",
            f"water-cementitious ratio is {actual:.3f} and the limit is {limit:.2f}",
            None if governing is None else str(governing),
        ),
    )


def check_strength(design: MixDesign) -> tuple[LimitFinding, ...]:
    """The specified strength against the exposure floor."""
    floor = design.exposure.min_strength
    if design.specified_strength >= floor:
        return ()
    governing = design.exposure.governing_class("min_strength")
    return (
        LimitFinding(
            "STRENGTH_BELOW_FLOOR",
            f"specified strength is {design.specified_strength.format(0)} and the "
            f"floor is {floor.format(0)}",
            None if governing is None else str(governing),
        ),
    )


def check_air(design: MixDesign) -> tuple[LimitFinding, ...]:
    """The design air against the freeze thaw requirement."""
    required = design.exposure.air_target(_size_label(design), design.specified_strength)
    if required is None:
        return ()
    if not design.is_air_entrained:
        return (
            LimitFinding(
                "AIR_MISSING",
                f"{design.exposure.freeze_thaw} needs {required.format(1)} air and the "
                "design carries none",
                str(design.exposure.freeze_thaw),
            ),
        )
    if design.design_air.value + 1e-9 < required.value:
        return (
            LimitFinding(
                "AIR_BELOW_REQUIREMENT",
                f"design air is {design.design_air.format(1)} and the requirement is "
                f"{required.format(1)}",
                str(design.exposure.freeze_thaw),
            ),
        )
    return ()


def check_replacement(design: MixDesign, catalog: MaterialCatalog) -> tuple[LimitFinding, ...]:
    """Supplementary replacement against the F3 caps.

    Only F3 imposes them. Every other class allows whatever the strength data
    supports, which is the point of qualifying a mixture by test rather than by
    prescription.
    """
    if design.exposure.freeze_thaw is not ExposureClass.F3:
        return ()
    cementitious = design.proportions.cementitious
    if cementitious.is_zero():
        return ()
    by_family: dict[str, Percent] = {}
    for charge in design.proportions.of_class(MaterialClass.SCM):
        material = catalog.get(charge.material_code)
        if material.scm_kind is None:
            continue
        family = _replacement_family(material.scm_kind)
        share = Percent.from_fraction(charge.content.ratio_to(cementitious))
        by_family[family] = by_family.get(family, Percent(0.0)) + share
    findings: list[LimitFinding] = []
    for family, share in sorted(by_family.items()):
        cap = F3_REPLACEMENT_CAPS[family]
        if share.value > cap.value + 1e-9:
            findings.append(
                LimitFinding(
                    "REPLACEMENT_ABOVE_CAP",
                    f"{family} is {share.format(1)} of the binder and the cap is "
                    f"{cap.format(0)}",
                    "F3",
                )
            )
    total = Percent(sum(share.value for share in by_family.values()))
    if total.value > F3_REPLACEMENT_CAPS["total"].value + 1e-9:
        findings.append(
            LimitFinding(
                "REPLACEMENT_ABOVE_CAP",
                f"total replacement is {total.format(1)} of the binder and the cap is "
                f"{F3_REPLACEMENT_CAPS['total'].format(0)}",
                "F3",
            )
        )
    return tuple(findings)


def check_sulfate_cement(
    design: MixDesign, catalog: MaterialCatalog
) -> tuple[LimitFinding, ...]:
    """Cement type and SCM choice against a sulfate class.

    Class C fly ash is the trap. It is a perfectly good pozzolan, it is cheaper
    than the alternatives, and in a sulfate exposure it is not allowed to be
    part of the answer.
    """
    sulfate = design.exposure.sulfate
    if sulfate.severity == 0:
        return ()
    findings: list[LimitFinding] = []
    for charge in design.proportions.of_class(MaterialClass.CEMENT):
        cement_type = catalog.get(charge.material_code).cement_type
        if cement_type is not None and not cement_type.is_sulfate_resisting:
            findings.append(
                LimitFinding(
                    "CEMENT_NOT_SULFATE_RESISTING",
                    f"{charge.material_code} is type {cement_type} and {sulfate} needs a "
                    "sulfate resisting cement",
                    str(sulfate),
                )
            )
    for charge in design.proportions.of_class(MaterialClass.SCM):
        kind = catalog.get(charge.material_code).scm_kind
        if kind is not None and not kind.helps_sulfate_resistance:
            findings.append(
                LimitFinding(
                    "SCM_NOT_SULFATE_RESISTING",
                    f"{charge.material_code} is {kind} and does not count toward sulfate "
                    "resistance",
                    str(sulfate),
                )
            )
    return tuple(findings)


def check_closure(design: MixDesign, catalog: MaterialCatalog) -> tuple[LimitFinding, ...]:
    """Whether the absolute volumes come to the unit volume they claim."""
    gravities: dict[str, float] = {}
    for charge in design.proportions.charges:
        material = catalog.get(charge.material_code)
        if material.specific_gravity is not None:
            gravities[charge.material_code] = material.specific_gravity
    check = check_yield(design.proportions, gravities)
    if check.conforms:
        return ()
    return (LimitFinding("YIELD_DOES_NOT_CLOSE", check.describe(), "ASTM C138"),)


def check_design(design: MixDesign, catalog: MaterialCatalog) -> tuple[LimitFinding, ...]:
    """Every rule this design breaks, in a stable order."""
    return (
        *check_ratio(design),
        *check_strength(design),
        *check_air(design),
        *check_replacement(design, catalog),
        *check_sulfate_cement(design, catalog),
        *check_closure(design, catalog),
    )


def is_conforming(design: MixDesign, catalog: MaterialCatalog) -> bool:
    """True when a design breaks no rule at all."""
    return not check_design(design, catalog)


def _size_label(design: MixDesign) -> str:
    """The air table row a design's aggregate falls in."""
    inches = design.nominal_max_size.to("in").value
    rows = (
        (0.375, "3/8 in"),
        (0.5, "1/2 in"),
        (0.75, "3/4 in"),
        (1.0, "1 in"),
        (1.5, "1-1/2 in"),
        (2.0, "2 in"),
        (3.0, "3 in"),
    )
    for size, label in rows:
        if inches <= size + 1e-6:
            return label
    return "3 in"
