"""Planning a batch: from a mix design to the weights the plant will call for.

Everything that can stop a batch is checked before any arithmetic happens, and
each refusal names itself. A plant whose scale calibration lapsed and whose
cement certificate expired should hear both, not whichever one the code
happened to reach first.

The order the checks run in is the order they are cheapest to fix in: the
plant, then the load size, then the paperwork on each material. That is also
the order a dispatcher would work through them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from slumpcone.batching.moisture import AggregateMoisture, MoistureCorrection, correct_batch
from slumpcone.batching.weighing import weighing_allowance
from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import MixDesign
from slumpcone.plant.plant import Plant
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class BatchLine:
    """One material the plant has to put in, and how close it has to get."""

    material_code: str
    material_class: MaterialClass
    design_weight: Quantity
    required: Quantity
    allowance: Quantity
    scale_code: str | None

    @property
    def moisture_adjustment(self) -> Quantity:
        """How far the moisture correction moved this line."""
        return self.required - self.design_weight.to(self.required.unit)

    def describe(self) -> str:
        """One line for a batch sheet."""
        where = self.scale_code or "metered"
        return (
            f"{self.material_code}  {self.required.format(0)}  "
            f"+/- {self.allowance.format(1)}  {where}"
        )


@dataclass(frozen=True, slots=True)
class AdmixtureLine:
    """One admixture dose, already scaled to the binder in this load."""

    material_code: str
    charge: Quantity

    def describe(self) -> str:
        """One line for a batch sheet."""
        return f"{self.material_code}  {self.charge.format(1)}"


@dataclass(frozen=True, slots=True)
class PlannedBatch:
    """Everything the plant needs to weigh out one load."""

    plant_code: str
    mix_code: str
    mix_revision: int
    volume: Quantity
    batched_on: date
    lines: tuple[BatchLine, ...]
    admixture_lines: tuple[AdmixtureLine, ...]
    correction: MoistureCorrection

    def line(self, material_code: str) -> BatchLine:
        """One line by material code."""
        for candidate in self.lines:
            if candidate.material_code == material_code:
                return candidate
        raise ValidationError(f"{material_code} is not in this batch", field="material_code")

    @property
    def total_weight(self) -> Quantity:
        """Everything the scales will see."""
        total = Quantity.zero(self.lines[0].required.unit)
        for entry in self.lines:
            total = total + entry.required
        return total

    @property
    def water_line(self) -> BatchLine:
        """The water line, which is the one a dispatcher looks at first."""
        for entry in self.lines:
            if entry.material_class is MaterialClass.WATER:
                return entry
        raise ValidationError("this batch has no water line", field="lines")

    def describe(self) -> str:
        """A batch sheet as plain text."""
        head = (
            f"{self.mix_code} r{self.mix_revision} at {self.plant_code}, "
            f"{self.volume.format(2)} on {self.batched_on.isoformat()}"
        )
        body = [entry.describe() for entry in self.lines]
        body.extend(entry.describe() for entry in self.admixture_lines)
        return "\n".join([head, *body])


def blocking_reasons(
    plant: Plant,
    design: MixDesign,
    catalog: MaterialCatalog,
    volume: Quantity,
    on: date,
) -> tuple[str, ...]:
    """Everything stopping this batch, in the order a dispatcher would fix it."""
    reasons = list(plant.blocking_reasons(on))
    if plant.max_load is not None and volume > plant.max_load:
        reasons.append(
            f"load of {volume.format(2)} is over the {plant.max_load.format(2)} "
            "the plant carries"
        )
    for charge in design.proportions.charges:
        missing = catalog.missing_certificates(charge.material_code, on)
        if missing:
            names = ", ".join(str(kind) for kind in missing)
            reasons.append(f"{charge.material_code} has no current {names}")
    for admixture in design.proportions.admixtures:
        missing = catalog.missing_certificates(admixture.material_code, on)
        if missing:
            names = ", ".join(str(kind) for kind in missing)
            reasons.append(f"{admixture.material_code} has no current {names}")
    return tuple(reasons)


def plan_batch(
    plant: Plant,
    design: MixDesign,
    catalog: MaterialCatalog,
    volume: Quantity,
    on: date,
    moistures: Mapping[str, AggregateMoisture] | None = None,
) -> PlannedBatch:
    """Work out the weights for one load, or refuse and say why."""
    reasons = blocking_reasons(plant, design, catalog, volume, on)
    if reasons:
        raise RuleViolationError("BATCH_REFUSED", "; ".join(reasons))
    correction = correct_batch(design.proportions, volume, moistures or {})
    lines: list[BatchLine] = []
    for charge in design.proportions.charges:
        required = correction.weight_of(charge.material_code)
        scale = None
        capacity = None
        if plant.has_scale_for(charge.material_class):
            found = plant.scale_for(charge.material_class)
            scale = found.code
            capacity = found.capacity
        allowance = weighing_allowance(charge.material_class, required, capacity)
        lines.append(
            BatchLine(
                charge.material_code,
                charge.material_class,
                correction.design_weight_of(charge.material_code),
                required,
                allowance,
                scale,
            )
        )
    doses = design.proportions.admixture_charges(volume)
    admixtures = tuple(AdmixtureLine(code, charge) for code, charge in sorted(doses.items()))
    return PlannedBatch(
        plant.code,
        design.code,
        design.revision,
        volume,
        on,
        tuple(lines),
        admixtures,
        correction,
    )
