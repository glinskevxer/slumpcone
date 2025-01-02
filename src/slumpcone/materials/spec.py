"""A material as the plant has it on file.

One record type covers every class, because a batch has to iterate over its
ingredients without asking what each one is. What differs is which fields are
required, and that is checked here rather than left to whoever reads the record
later. A coarse aggregate with no specific gravity cannot be proportioned by
absolute volume, and finding that out at the batch computer is too late.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.materials.kinds import (
    AdmixtureType,
    CementType,
    MaterialClass,
    ScmKind,
    WaterSource,
)
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# Specific gravity outside this range is a data entry error, not a material.
# Portland cement is 3.15, normal weight aggregate is 2.4 to 2.9, lightweight
# aggregate goes down to 1.2, and admixture solutions sit just above water.
_SG_LOW = 0.8
_SG_HIGH = 5.0


def _check_specific_gravity(value: float | None, field_name: str) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not _SG_LOW <= number <= _SG_HIGH:
        raise ValidationError(
            f"specific gravity {number} is outside {_SG_LOW} to {_SG_HIGH}",
            field=field_name,
        )
    return number


@dataclass(frozen=True, slots=True)
class Material:
    """One material the plant can batch, with the properties its class needs."""

    code: str
    name: str
    material_class: MaterialClass
    supplier: str | None = None
    source: str | None = None
    specific_gravity: float | None = None
    absorption: Percent | None = None
    fineness_modulus: float | None = None
    nominal_max_size: Quantity | None = None
    dry_rodded_unit_weight: MassPerVolume | None = None
    cement_type: CementType | None = None
    scm_kind: ScmKind | None = None
    admixture_type: AdmixtureType | None = None
    solids_content: Percent | None = None
    water_source: WaterSource | None = None
    chloride_content: Percent | None = None
    alkali_content: Percent | None = None
    notes: str = field(default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="material_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="material_name"))
        object.__setattr__(
            self,
            "specific_gravity",
            _check_specific_gravity(self.specific_gravity, "specific_gravity"),
        )
        self._check_required()
        self._check_forbidden()
        self._check_ranges()

    def _check_required(self) -> None:
        klass = self.material_class
        if klass is MaterialClass.CEMENT and self.cement_type is None:
            raise ValidationError("a cement needs a type", field="cement_type")
        if klass is MaterialClass.SCM and self.scm_kind is None:
            raise ValidationError("an scm needs a kind", field="scm_kind")
        if klass is MaterialClass.ADMIXTURE and self.admixture_type is None:
            raise ValidationError("an admixture needs a type", field="admixture_type")
        if klass is MaterialClass.WATER and self.water_source is None:
            raise ValidationError("water needs a source", field="water_source")
        if klass.is_aggregate:
            if self.specific_gravity is None:
                raise ValidationError(
                    "an aggregate needs a bulk specific gravity", field="specific_gravity"
                )
            if self.absorption is None:
                raise ValidationError("an aggregate needs an absorption", field="absorption")
        if klass is MaterialClass.FINE_AGGREGATE and self.fineness_modulus is None:
            raise ValidationError(
                "a fine aggregate needs a fineness modulus", field="fineness_modulus"
            )
        if klass is MaterialClass.COARSE_AGGREGATE and self.nominal_max_size is None:
            raise ValidationError(
                "a coarse aggregate needs a nominal maximum size", field="nominal_max_size"
            )

    def _check_forbidden(self) -> None:
        klass = self.material_class
        if self.cement_type is not None and klass is not MaterialClass.CEMENT:
            raise ValidationError("only a cement carries a cement type", field="cement_type")
        if self.scm_kind is not None and klass is not MaterialClass.SCM:
            raise ValidationError("only an scm carries an scm kind", field="scm_kind")
        if self.admixture_type is not None and klass is not MaterialClass.ADMIXTURE:
            raise ValidationError(
                "only an admixture carries an admixture type", field="admixture_type"
            )
        if self.water_source is not None and klass is not MaterialClass.WATER:
            raise ValidationError("only water carries a water source", field="water_source")
        if self.fineness_modulus is not None and klass is not MaterialClass.FINE_AGGREGATE:
            raise ValidationError(
                "a fineness modulus belongs to a fine aggregate", field="fineness_modulus"
            )

    def _check_ranges(self) -> None:
        if self.fineness_modulus is not None and not 1.5 <= self.fineness_modulus <= 4.5:
            raise ValidationError(
                f"fineness modulus {self.fineness_modulus} is outside 1.5 to 4.5",
                field="fineness_modulus",
            )
        if self.absorption is not None and not 0.0 <= self.absorption.value <= 30.0:
            raise ValidationError(
                f"absorption {self.absorption} is outside 0 to 30 percent", field="absorption"
            )
        if self.solids_content is not None and not 0.0 < self.solids_content.value <= 100.0:
            raise ValidationError(
                f"solids content {self.solids_content} is outside 0 to 100 percent",
                field="solids_content",
            )
        if self.chloride_content is not None and not 0.0 <= self.chloride_content.value <= 5.0:
            raise ValidationError(
                f"a chloride content of {self.chloride_content} is not a material assay",
                field="chloride_content",
            )
        if self.alkali_content is not None and not 0.0 <= self.alkali_content.value <= 5.0:
            raise ValidationError(
                f"an alkali content of {self.alkali_content} is not a mill certificate",
                field="alkali_content",
            )
        if self.nominal_max_size is not None and self.nominal_max_size.value <= 0.0:
            raise ValidationError(
                "a nominal maximum size has to be positive", field="nominal_max_size"
            )

    @property
    def has_chloride_assay(self) -> bool:
        """True when somebody has actually measured this material's chloride.

        A missing figure is not zero. Aggregate dredged from a tidal estuary
        carries chloride and looks exactly like aggregate that does not, so a
        calculation that treats an absent assay as nothing is quietly wrong in
        the one case that matters.
        """
        return self.chloride_content is not None

    @property
    def is_cementitious(self) -> bool:
        """True when this material counts toward the cementitious total."""
        return self.material_class.is_cementitious

    @property
    def is_aggregate(self) -> bool:
        """True when this material is weighed wet and corrected for moisture."""
        return self.material_class.is_aggregate

    @property
    def absolute_density(self) -> MassPerVolume:
        """Mass per unit of absolute volume, from the specific gravity.

        Absolute volume proportioning needs this for every solid in the mix, so
        a material without a specific gravity cannot appear in a mix design.
        """
        if self.specific_gravity is None:
            raise ValidationError(
                f"{self.code} has no specific gravity, so it has no absolute volume",
                field="specific_gravity",
            )
        return MassPerVolume(self.specific_gravity * 62.42796, "lb", "ft3")

    def describe(self) -> str:
        """One line for a listing."""
        detail = str(self.material_class)
        if self.cement_type is not None:
            detail = f"cement {self.cement_type}"
        elif self.scm_kind is not None:
            detail = str(self.scm_kind)
        elif self.admixture_type is not None:
            detail = str(self.admixture_type)
        return f"{self.code}  {self.name}  ({detail})"
