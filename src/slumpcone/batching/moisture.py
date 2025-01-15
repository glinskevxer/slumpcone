"""Free moisture on the aggregate, and what it does to the batch.

A mix design is written on saturated surface dry aggregate: stone and sand with
their pores full and nothing on the outside. Nothing in a stockpile is ever in
that condition. It carries free water on the surface after rain, or it is
bone dry off the top of a summer pile and will pull water out of the mixture.

Two corrections come out of one measurement and they go in opposite
directions. The aggregate is weighed heavier so the solid content still comes
out right, and the mix water is cut by the free water that came in with it. Do
one without the other and the ratio moves.

The relation is not the ``1 + free`` shortcut that gets written on whiteboards.
Total moisture and absorption are both quoted against the oven dry weight, so
the batch weight is the SSD weight times ``(1 + total) / (1 + absorption)``. The
shortcut is close at low absorption and wrong by pounds on a lightweight.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.percent import Percent
from slumpcone.units.checks import require_mass, require_positive, require_volume
from slumpcone.units.quantity import Quantity

# Above this, the reading is a probe fault rather than a wet pile. Sand off a
# reclaimer runs six or seven percent and a saturated stockpile bottom might
# touch twelve.
MAX_TOTAL_MOISTURE = Percent(20.0)


@dataclass(frozen=True, slots=True)
class AggregateMoisture:
    """One aggregate's moisture condition at the moment of batching."""

    material_code: str
    total_moisture: Percent
    absorption: Percent

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        if self.total_moisture.value < 0.0:
            raise ValidationError("total moisture cannot be negative", field="total_moisture")
        if self.total_moisture > MAX_TOTAL_MOISTURE:
            raise ValidationError(
                f"total moisture of {self.total_moisture} is a probe fault, not a stockpile",
                field="total_moisture",
            )
        if self.absorption.value < 0.0:
            raise ValidationError("absorption cannot be negative", field="absorption")
        if self.absorption.value > 30.0:
            raise ValidationError(
                "absorption above thirty percent is not an aggregate", field="absorption"
            )

    @property
    def free_moisture(self) -> Percent:
        """Surface water, negative when the aggregate will absorb instead."""
        return self.total_moisture - self.absorption

    @property
    def is_dry(self) -> bool:
        """True when this aggregate will take water out of the mixture."""
        return self.free_moisture.value < 0.0

    @property
    def factor(self) -> float:
        """The multiplier that takes an SSD weight to a batch weight."""
        return (1.0 + self.total_moisture.fraction) / (1.0 + self.absorption.fraction)

    def batch_weight(self, ssd_weight: Quantity) -> Quantity:
        """The weight to put on the scale to get ``ssd_weight`` of solid."""
        require_mass(ssd_weight, "an SSD weight", field="ssd_weight")
        return ssd_weight * self.factor

    def free_water(self, ssd_weight: Quantity) -> Quantity:
        """The water that rides in on the aggregate, negative when it is dry."""
        return self.batch_weight(ssd_weight) - ssd_weight


@dataclass(frozen=True, slots=True)
class MoistureCorrection:
    """A batch after the moisture on the aggregate has been accounted for."""

    design_weights: tuple[tuple[str, Quantity], ...]
    batch_weights: tuple[tuple[str, Quantity], ...]
    design_water: Quantity
    batch_water: Quantity
    free_water: Quantity

    def weight_of(self, material_code: str) -> Quantity:
        """The corrected batch weight for one material."""
        key = normalize_code(material_code, field="material_code")
        for code, weight in self.batch_weights:
            if code == key:
                return weight
        raise ValidationError(f"{key} is not in this batch", field="material_code")

    def design_weight_of(self, material_code: str) -> Quantity:
        """The uncorrected weight the design called for."""
        key = normalize_code(material_code, field="material_code")
        for code, weight in self.design_weights:
            if code == key:
                return weight
        raise ValidationError(f"{key} is not in this batch", field="material_code")

    @property
    def total_batch_weight(self) -> Quantity:
        """Everything on the scales plus the water actually added."""
        total = Quantity.zero(self.batch_water.unit)
        for _, weight in self.batch_weights:
            total = total + weight
        return total

    @property
    def water_was_cut(self) -> bool:
        """True when free moisture reduced the water rather than raising it."""
        return self.free_water.value > 0.0

    def describe(self) -> str:
        """One line summarising the correction."""
        direction = "cut" if self.water_was_cut else "raised"
        return (
            f"water {direction} from {self.design_water.format(0)} to "
            f"{self.batch_water.format(0)} on {abs(self.free_water).format(0)} of free water"
        )


def correct_batch(
    proportions: Proportions,
    volume: Quantity,
    moistures: Mapping[str, AggregateMoisture],
) -> MoistureCorrection:
    """Scale ``proportions`` to ``volume`` and correct for aggregate moisture.

    An aggregate with no moisture reading is batched at its design weight and
    contributes no free water. That is a deliberate choice rather than an error:
    a plant with a broken probe on one bin still has to be able to batch, and
    the missing correction shows up in the water on the ticket.
    """
    require_volume(volume, "a batch size", field="volume")
    require_positive(volume, "a batch size", field="volume")
    design = proportions.batch_weights(volume)
    water_charges = proportions.of_class(MaterialClass.WATER)
    water_code = water_charges[0].material_code
    design_water = design[water_code]
    free_total = Quantity.zero(design_water.unit)
    batch: list[tuple[str, Quantity]] = []
    designed: list[tuple[str, Quantity]] = []
    for charge in proportions.charges:
        weight = design[charge.material_code]
        designed.append((charge.material_code, weight))
        if charge.material_code == water_code:
            continue
        reading = moistures.get(charge.material_code)
        if reading is None or not charge.material_class.is_aggregate:
            batch.append((charge.material_code, weight))
            continue
        batch.append((charge.material_code, reading.batch_weight(weight)))
        free_total = free_total + reading.free_water(weight)
    batch_water = design_water - free_total
    if batch_water.value < 0.0:
        raise ValidationError(
            "the free water on the aggregate is more than the mix water; "
            "the moisture readings or the design water are wrong",
            field="batch_water",
        )
    batch.append((water_code, batch_water))
    return MoistureCorrection(
        tuple(designed), tuple(batch), design_water, batch_water, free_total
    )
