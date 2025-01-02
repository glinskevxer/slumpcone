"""Alkali loading, and what it takes to stop an aggregate reacting.

Some aggregates react with the alkalis in the paste and the product swells. It
takes years, it cracks the structure from the inside, and nothing done
afterwards fixes it. So the whole of alkali silica prevention is done before
the first load: limit the alkali the mixture carries, or replace enough of the
cement with a supplementary material that the reaction cannot get going, or
both.

The alkali figure on a mill certificate is already an equivalent: sodium oxide
plus a fraction of the potassium oxide, because potassium contributes to the
reaction but weighs less per mole. Multiplying it by the cement content gives
the loading in pounds per cubic yard, and that loading is what the limits are
written against, not the percentage.

Which limit applies is a two way lookup: how reactive the aggregate is, and how
much the structure matters. A pavement made with a mildly reactive aggregate
and a nuclear containment made with the same aggregate get different answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import MaterialClass, ScmKind
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

# The factor that turns potassium oxide into its sodium oxide equivalent.
POTASSIUM_FACTOR = 0.658


class ReactivityClass(Enum):
    """How reactive an aggregate has tested."""

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> ReactivityClass:
        """Read a reactivity class off an aggregate test report."""
        key = text.strip().upper()
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown reactivity class {text!r}", field="reactivity")

    @property
    def is_reactive(self) -> bool:
        """True when the aggregate needs anything done about it at all."""
        return self is not ReactivityClass.R0


class StructureClass(Enum):
    """How much the structure matters, in the terms the standard uses."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> StructureClass:
        """Read a structure class off a specification."""
        key = text.strip().upper()
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown structure class {text!r}", field="structure")


class PreventionLevel(Enum):
    """How hard the mixture has to work to stop the reaction."""

    NONE = "none"
    V = "V"
    W = "W"
    X = "X"
    Y = "Y"
    Z = "Z"

    def __str__(self) -> str:
        return self.value

    @property
    def alkali_limit(self) -> Quantity | None:
        """The alkali loading this level allows, when it caps one at all."""
        table = {
            PreventionLevel.V: 3.0,
            PreventionLevel.W: 3.0,
            PreventionLevel.X: 2.4,
            PreventionLevel.Y: 1.8,
        }
        value = table.get(self)
        return None if value is None else Quantity(value, "lb")

    @property
    def minimum_replacement(self) -> Percent:
        """How much of the binder has to be a supplementary material."""
        table = {
            PreventionLevel.NONE: 0.0,
            PreventionLevel.V: 0.0,
            PreventionLevel.W: 20.0,
            PreventionLevel.X: 25.0,
            PreventionLevel.Y: 35.0,
            PreventionLevel.Z: 50.0,
        }
        return Percent(table[self])


# The lookup: reactivity down, structure class across.
_LEVELS: dict[ReactivityClass, dict[StructureClass, PreventionLevel]] = {
    ReactivityClass.R0: dict.fromkeys(StructureClass, PreventionLevel.NONE),
    ReactivityClass.R1: {
        StructureClass.S1: PreventionLevel.NONE,
        StructureClass.S2: PreventionLevel.V,
        StructureClass.S3: PreventionLevel.W,
        StructureClass.S4: PreventionLevel.X,
    },
    ReactivityClass.R2: {
        StructureClass.S1: PreventionLevel.V,
        StructureClass.S2: PreventionLevel.W,
        StructureClass.S3: PreventionLevel.X,
        StructureClass.S4: PreventionLevel.Y,
    },
    ReactivityClass.R3: {
        StructureClass.S1: PreventionLevel.W,
        StructureClass.S2: PreventionLevel.X,
        StructureClass.S3: PreventionLevel.Y,
        StructureClass.S4: PreventionLevel.Z,
    },
}


def prevention_level(reactivity: ReactivityClass, structure: StructureClass) -> PreventionLevel:
    """Which prevention level applies to an aggregate in a structure."""
    return _LEVELS[reactivity][structure]


def sodium_equivalent(sodium: Percent, potassium: Percent) -> Percent:
    """The alkali equivalent from the two oxides on a mill certificate."""
    return Percent(sodium.value + POTASSIUM_FACTOR * potassium.value)


@dataclass(frozen=True, slots=True)
class AlkaliLoading:
    """How much alkali one unit volume of a mixture carries."""

    per_material: tuple[tuple[str, Quantity], ...]
    unassayed: tuple[str, ...]

    @property
    def total(self) -> Quantity:
        """Alkali in one unit volume, from everything that was assayed."""
        running = Quantity.zero("lb")
        for _, amount in self.per_material:
            running = running + amount.to("lb")
        return running

    @property
    def is_complete(self) -> bool:
        """True when every cementitious material has an alkali figure."""
        return not self.unassayed

    def describe(self) -> str:
        """One line for a submittal."""
        tail = (
            "" if self.is_complete else f", incomplete: {', '.join(self.unassayed)} not assayed"
        )
        return f"alkali loading is {self.total.format(2)} per unit volume{tail}"


def alkali_loading(proportions: Proportions, catalog: MaterialCatalog) -> AlkaliLoading:
    """Add up the alkali the cementitious materials bring."""
    one_unit = Quantity(1.0, proportions.volume_unit)
    weights = proportions.batch_weights(one_unit)
    per_material: list[tuple[str, Quantity]] = []
    unassayed: list[str] = []
    for charge in proportions.charges:
        if not charge.material_class.is_cementitious:
            continue
        material = catalog.get(charge.material_code)
        if material.alkali_content is None:
            unassayed.append(charge.material_code)
            continue
        weight = weights[charge.material_code]
        per_material.append((charge.material_code, weight * material.alkali_content.fraction))
    return AlkaliLoading(tuple(per_material), tuple(unassayed))


def scm_counts_toward_prevention(kind: ScmKind) -> bool:
    """True when a supplementary material actually suppresses the reaction.

    Class C fly ash is the exception again. Its own alkali and calcium content
    mean high replacement levels of it can make the reaction worse rather than
    better, so it does not count toward a prevention level on its own.
    """
    return kind is not ScmKind.FLY_ASH_C


def check_alkali(
    proportions: Proportions,
    catalog: MaterialCatalog,
    reactivity: ReactivityClass,
    structure: StructureClass,
) -> tuple[str, ...]:
    """Everything about a mixture that leaves the reaction unaddressed."""
    level = prevention_level(reactivity, structure)
    if level is PreventionLevel.NONE:
        return ()
    findings: list[str] = []
    loading = alkali_loading(proportions, catalog)
    limit = level.alkali_limit
    if not loading.is_complete:
        findings.append(
            f"{', '.join(loading.unassayed)} has no alkali assay, so the loading "
            "cannot be shown to meet the limit"
        )
    elif limit is not None and loading.total > limit:
        findings.append(
            f"alkali loading is {loading.total.format(2)} and level {level} allows "
            f"{limit.format(2)}"
        )
    wanted = level.minimum_replacement
    if wanted:
        counted = Percent(0.0)
        for charge in proportions.of_class(MaterialClass.SCM):
            kind = catalog.get(charge.material_code).scm_kind
            if kind is None or not scm_counts_toward_prevention(kind):
                continue
            counted = counted + Percent.from_fraction(
                charge.content.ratio_to(proportions.cementitious)
            )
        if counted.value + 1e-9 < wanted.value:
            findings.append(
                f"level {level} needs {wanted.format(0)} replacement and the mixture "
                f"has {counted.format(1)} that counts"
            )
    return tuple(findings)
