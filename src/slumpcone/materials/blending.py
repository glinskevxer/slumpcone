"""Combining two or more aggregates into one gradation.

A mixture is never graded by one aggregate. It is graded by the stone and the
sand together, in the proportions the mix design happens to use, and that
combined curve is what governs how the concrete places and finishes. A stone
that conforms and a sand that conforms can still combine into something nobody
can screed.

The blend is by absolute volume, not by weight, when the aggregates differ in
specific gravity. Blending a normal weight stone with a lightweight sand by
weight gives a curve for a mixture that does not exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.materials.gradation import SIEVES, Gradation, Sieve
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class BlendComponent:
    """One aggregate in a blend, with how much of it there is."""

    material_code: str
    gradation: Gradation
    weight: Quantity
    specific_gravity: float | None = None

    def __post_init__(self) -> None:
        if self.weight.dimension.value != "mass":
            raise ValidationError("a blend component is weighed", field="weight")
        if self.weight.value < 0.0:
            raise ValidationError("a blend component cannot be negative", field="weight")
        if self.specific_gravity is not None and self.specific_gravity <= 0.0:
            raise ValidationError(
                "a specific gravity has to be positive", field="specific_gravity"
            )

    @property
    def absolute_volume(self) -> float:
        """Relative volume, for blending when the gravities differ."""
        if self.specific_gravity is None:
            raise ValidationError(
                f"{self.material_code} has no specific gravity, so it cannot be "
                "blended by volume",
                field="specific_gravity",
            )
        return self.weight.base_value / self.specific_gravity


def _share(components: Sequence[BlendComponent], *, by_volume: bool) -> list[float]:
    if not components:
        raise ValidationError("a blend needs at least one component", field="components")
    amounts = [
        component.absolute_volume if by_volume else component.weight.base_value
        for component in components
    ]
    total = sum(amounts)
    if total <= 0.0:
        raise ValidationError("a blend of nothing has no gradation", field="components")
    return [amount / total for amount in amounts]


def combine(components: Sequence[BlendComponent], *, by_volume: bool = False) -> Gradation:
    """The combined gradation of several aggregates.

    Every sieve any component was run on appears in the result. A component
    that was not run on a sieve is taken as passing everything through it,
    which is right when the sieve is coarser than that aggregate and wrong
    when it is finer, so a stack that stops early is refused instead.
    """
    shares = _share(components, by_volume=by_volume)
    labels: list[str] = []
    for component in components:
        for sieve_, _ in component.gradation.passing:
            if sieve_.label not in labels:
                labels.append(sieve_.label)
    ordered = [sieve for sieve in SIEVES if sieve.label in labels]
    finest = min(sieve.opening_mm for sieve in ordered)
    for component in components:
        if component.gradation.finest.opening_mm > finest + 1e-9:
            raise ValidationError(
                f"{component.material_code} was not run down to "
                f"{min(ordered, key=lambda s: s.opening_mm)}, so the blend below that "
                "sieve cannot be computed",
                field="components",
            )
    pairs: list[tuple[Sieve, Percent]] = []
    for sieve_ in ordered:
        total = 0.0
        for component, share in zip(components, shares, strict=True):
            passing = component.gradation.passing_on(sieve_.label)
            total += share * (100.0 if passing is None else passing.value)
        pairs.append((sieve_, Percent(min(total, 100.0))))
    return Gradation(tuple(pairs))


def blend_shares(
    components: Sequence[BlendComponent], *, by_volume: bool = False
) -> tuple[tuple[str, Percent], ...]:
    """What share of the blend each component makes up."""
    shares = _share(components, by_volume=by_volume)
    return tuple(
        (component.material_code, Percent.from_fraction(share))
        for component, share in zip(components, shares, strict=True)
    )


def blend_to_target(
    coarse: BlendComponent,
    fine: BlendComponent,
    target: Gradation,
    sieve_label: str,
) -> Percent:
    """The share of coarse aggregate that hits a target on one sieve.

    Two aggregates and one sieve is the one blending problem with a closed form
    answer. Anything more is a fit, and a fit that nobody can check by hand is
    not what a batch plant needs at eleven at night.
    """
    coarse_passing = coarse.gradation.passing_on(sieve_label)
    fine_passing = fine.gradation.passing_on(sieve_label)
    wanted = target.passing_on(sieve_label)
    if coarse_passing is None or fine_passing is None or wanted is None:
        raise ValidationError(
            f"{sieve_label} was not run on all three gradations", field="sieve_label"
        )
    spread = fine_passing.value - coarse_passing.value
    if abs(spread) < 1e-9:
        raise ValidationError(
            f"both aggregates pass the same amount on {sieve_label}, so no blend of "
            "them changes it",
            field="sieve_label",
        )
    share = (fine_passing.value - wanted.value) / spread
    if not -1e-9 <= share <= 1.0 + 1e-9:
        raise ValidationError(
            f"no blend of these two reaches {wanted.format(1)} passing {sieve_label}",
            field="target",
        )
    return Percent.from_fraction(min(max(share, 0.0), 1.0))
