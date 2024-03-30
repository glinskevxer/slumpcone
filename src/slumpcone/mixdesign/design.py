"""The mix design record.

A mix design is a proportion sheet plus everything the proportions have to be
judged against: the strength it is sold as, the age that strength is measured
at, the slump and air the field is allowed to hold it to, and the exposure the
structure puts it in.

Revisions matter and are part of the identity. A plant that adjusts a sand
proportion has produced a new revision of the same design, and a cylinder broken
next month has to be attributable to the revision that was actually batched.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity

# The ages a strength is ever specified at. A design quoting anything else is
# almost always a typo for one of these.
COMMON_TEST_AGES = (3, 7, 14, 28, 56, 90)


# ASTM C94's slump tolerance when the specification names a target rather than
# a maximum: plus or minus one inch when the target is three inches or less,
# and plus or minus one and a half above that.
def default_slump_band(target: Quantity) -> Band:
    """The tolerance C94 allows around a nominal slump target."""
    inches = target.to("in").value
    allowance = 1.0 if inches <= 3.0 else 1.5
    return Band.symmetric(inches, allowance)


@dataclass(frozen=True, slots=True)
class MixDesign:
    """One proportioned mixture, at one revision."""

    code: str
    name: str
    proportions: Proportions
    specified_strength: Quantity
    nominal_max_size: Quantity
    slump_target: Quantity
    test_age_days: int = 28
    slump_band: Band | None = None
    air_band: Band | None = None
    exposure: ExposureSet = field(default_factory=ExposureSet)
    revision: int = 1
    plant_code: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="mix_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="mix_name"))
        if self.plant_code is not None:
            object.__setattr__(
                self, "plant_code", normalize_code(self.plant_code, field="plant_code")
            )
        if self.specified_strength.dimension.value != "pressure":
            raise ValidationError(
                "a specified strength is a pressure", field="specified_strength"
            )
        if self.specified_strength.value <= 0.0:
            raise ValidationError(
                "a specified strength has to be positive", field="specified_strength"
            )
        if self.nominal_max_size.dimension.value != "length":
            raise ValidationError(
                "a nominal maximum size is a length", field="nominal_max_size"
            )
        if self.nominal_max_size.value <= 0.0:
            raise ValidationError(
                "a nominal maximum size has to be positive", field="nominal_max_size"
            )
        if self.slump_target.dimension.value != "length":
            raise ValidationError("a slump is a length", field="slump_target")
        if self.slump_target.value < 0.0:
            raise ValidationError("a slump target cannot be negative", field="slump_target")
        if self.test_age_days <= 0:
            raise ValidationError("a test age has to be positive", field="test_age_days")
        if self.revision <= 0:
            raise ValidationError("a revision number starts at one", field="revision")
        if self.slump_band is None:
            object.__setattr__(self, "slump_band", default_slump_band(self.slump_target))
        if self.air_band is None and self.proportions.design_air:
            object.__setattr__(
                self, "air_band", Band.symmetric(self.proportions.design_air.value, 1.5)
            )

    @property
    def identity(self) -> str:
        """Code and revision together, which is what a ticket prints."""
        return f"{self.code} r{self.revision}"

    @property
    def water_cementitious_ratio(self) -> float:
        """The design ratio."""
        return self.proportions.water_cementitious_ratio

    @property
    def cementitious(self) -> Quantity:
        """Cementitious content in one unit volume."""
        return self.proportions.cementitious.times(Quantity(1.0, self.proportions.volume_unit))

    @property
    def design_air(self) -> Percent:
        """The air content the proportions were computed on."""
        return self.proportions.design_air

    @property
    def is_air_entrained(self) -> bool:
        """True when the design carries a deliberate air content."""
        return bool(self.proportions.design_air)

    def slump_tolerance(self) -> Band:
        """The band the field holds the load to."""
        assert self.slump_band is not None
        return self.slump_band

    def air_tolerance(self) -> Band | None:
        """The air band, or ``None`` for a design with no air requirement."""
        return self.air_band

    def revise(self, proportions: Proportions, *, notes: str = "") -> MixDesign:
        """The next revision of this design, carrying everything else forward."""
        return replace(
            self,
            proportions=proportions,
            revision=self.revision + 1,
            notes=notes or self.notes,
        )

    def describe(self) -> str:
        """One line for a listing."""
        return (
            f"{self.identity}  {self.name}  "
            f"{self.specified_strength.format(0)} at {self.test_age_days} d  "
            f"w/cm {self.water_cementitious_ratio:.3f}  "
            f"slump {self.slump_target.format(1)}  {self.exposure}"
        )
