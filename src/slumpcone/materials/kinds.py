"""What a material is, and what that implies about how it is treated.

The distinctions here are not filing categories. Whether something counts as
cementitious decides the water-cementitious ratio, which decides whether the
mix meets an exposure requirement. Whether an admixture retards set decides
whether the ninety minute discharge limit applies. Getting the class wrong
changes the arithmetic, not just the label.
"""

from __future__ import annotations

from enum import Enum

from slumpcone.errors import ValidationError


def _parse(cls: type[Enum], text: str, field: str) -> Enum:
    key = text.strip().upper().replace(" ", "_").replace("-", "_")
    for member in cls:
        if member.name == key or str(member.value).upper() == key:
            return member
    raise ValidationError(f"unknown {field} {text!r}", field=field)


class MaterialClass(Enum):
    """The broad class a material belongs to."""

    CEMENT = "cement"
    SCM = "scm"
    COARSE_AGGREGATE = "coarse_aggregate"
    FINE_AGGREGATE = "fine_aggregate"
    ADMIXTURE = "admixture"
    WATER = "water"
    FIBER = "fiber"
    PIGMENT = "pigment"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> MaterialClass:
        """Read a material class out of a mapping profile or a CSV column."""
        member = _parse(cls, text, "material class")
        assert isinstance(member, MaterialClass)
        return member

    @property
    def is_cementitious(self) -> bool:
        """True when this class counts toward the cementitious total."""
        return self in {MaterialClass.CEMENT, MaterialClass.SCM}

    @property
    def is_aggregate(self) -> bool:
        """True when this class is batched by weight and carries moisture."""
        return self in {MaterialClass.COARSE_AGGREGATE, MaterialClass.FINE_AGGREGATE}

    @property
    def is_batched_by_weight(self) -> bool:
        """True when the plant weighs it rather than metering it by volume."""
        return self not in {MaterialClass.ADMIXTURE, MaterialClass.WATER}


class CementType(Enum):
    """Portland and blended hydraulic cements, ASTM C150 and C595."""

    TYPE_I = "I"
    TYPE_IA = "IA"
    TYPE_II = "II"
    TYPE_IIA = "IIA"
    TYPE_II_V = "II/V"
    TYPE_III = "III"
    TYPE_IIIA = "IIIA"
    TYPE_IV = "IV"
    TYPE_V = "V"
    TYPE_IL = "IL"
    TYPE_IS = "IS"
    TYPE_IP = "IP"
    TYPE_IT = "IT"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> CementType:
        """Read a cement type off a mill certificate."""
        key = text.strip().upper().replace(" ", "").replace("TYPE", "")
        for member in cls:
            if member.value == key or member.name == text.strip().upper():
                return member
        raise ValidationError(f"unknown cement type {text!r}", field="cement_type")

    @property
    def standard(self) -> str:
        """The ASTM specification this type is bought against."""
        blended = {
            CementType.TYPE_IL,
            CementType.TYPE_IS,
            CementType.TYPE_IP,
            CementType.TYPE_IT,
        }
        if self in blended:
            return "ASTM C595"
        return "ASTM C150"

    @property
    def is_blended(self) -> bool:
        """True for the C595 blended cements, which already contain an SCM."""
        return self.standard == "ASTM C595"

    @property
    def is_air_entraining(self) -> bool:
        """True for the A suffix types, which carry their own air entrainer."""
        return self.value.endswith("A")

    @property
    def is_sulfate_resisting(self) -> bool:
        """True for the types a sulfate exposure class will accept on its own."""
        return self in {
            CementType.TYPE_II,
            CementType.TYPE_IIA,
            CementType.TYPE_II_V,
            CementType.TYPE_V,
        }

    @property
    def is_high_early(self) -> bool:
        """True for the types used to pull a seven day strength forward."""
        return self in {CementType.TYPE_III, CementType.TYPE_IIIA}


class ScmKind(Enum):
    """Supplementary cementitious materials and what they are graded on."""

    FLY_ASH_F = "fly_ash_f"
    FLY_ASH_C = "fly_ash_c"
    SLAG_100 = "slag_100"
    SLAG_120 = "slag_120"
    SILICA_FUME = "silica_fume"
    METAKAOLIN = "metakaolin"
    NATURAL_POZZOLAN = "natural_pozzolan"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> ScmKind:
        """Read an SCM kind out of a mix design or a silo assignment."""
        member = _parse(cls, text, "scm kind")
        assert isinstance(member, ScmKind)
        return member

    @property
    def standard(self) -> str:
        """The ASTM specification this material is bought against."""
        table = {
            ScmKind.FLY_ASH_F: "ASTM C618",
            ScmKind.FLY_ASH_C: "ASTM C618",
            ScmKind.NATURAL_POZZOLAN: "ASTM C618",
            ScmKind.SLAG_100: "ASTM C989",
            ScmKind.SLAG_120: "ASTM C989",
            ScmKind.SILICA_FUME: "ASTM C1240",
            ScmKind.METAKAOLIN: "ASTM C618",
        }
        return table[self]

    @property
    def is_fly_ash(self) -> bool:
        """True for the two fly ash classes."""
        return self in {ScmKind.FLY_ASH_F, ScmKind.FLY_ASH_C}

    @property
    def is_slag(self) -> bool:
        """True for the two slag cement grades."""
        return self in {ScmKind.SLAG_100, ScmKind.SLAG_120}

    @property
    def helps_sulfate_resistance(self) -> bool:
        """True when this SCM is accepted as part of a sulfate resisting system.

        Class C fly ash is the exception that catches people out. Its high
        calcium content does not help sulfate resistance and the specifications
        that allow substitution do not allow it.
        """
        return self is not ScmKind.FLY_ASH_C


class AdmixtureType(Enum):
    """Chemical admixtures, by the type letter their standard gives them."""

    AIR_ENTRAINING = "air_entraining"
    TYPE_A_WATER_REDUCING = "type_a"
    TYPE_B_RETARDING = "type_b"
    TYPE_C_ACCELERATING = "type_c"
    TYPE_D_WATER_REDUCING_RETARDING = "type_d"
    TYPE_E_WATER_REDUCING_ACCELERATING = "type_e"
    TYPE_F_HIGH_RANGE = "type_f"
    TYPE_G_HIGH_RANGE_RETARDING = "type_g"
    TYPE_S_SPECIFIC_PERFORMANCE = "type_s"
    VISCOSITY_MODIFYING = "vma"
    SHRINKAGE_REDUCING = "shrinkage_reducing"
    CORROSION_INHIBITING = "corrosion_inhibiting"
    HYDRATION_STABILIZING = "hydration_stabilizing"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> AdmixtureType:
        """Read an admixture type out of a mix design line."""
        member = _parse(cls, text, "admixture type")
        assert isinstance(member, AdmixtureType)
        return member

    @property
    def standard(self) -> str:
        """The ASTM specification this admixture is bought against."""
        if self is AdmixtureType.AIR_ENTRAINING:
            return "ASTM C260"
        if self in {AdmixtureType.TYPE_F_HIGH_RANGE, AdmixtureType.TYPE_G_HIGH_RANGE_RETARDING}:
            return "ASTM C494"
        if self is AdmixtureType.HYDRATION_STABILIZING:
            return "ASTM C1798"
        return "ASTM C494"

    @property
    def retards_set(self) -> bool:
        """True when this admixture extends the time the load stays workable.

        The discharge time limit is written against a load with no retarder in
        it, so this flag is what lets a stabilised load run past ninety minutes
        without a non-conformance.
        """
        return self in {
            AdmixtureType.TYPE_B_RETARDING,
            AdmixtureType.TYPE_D_WATER_REDUCING_RETARDING,
            AdmixtureType.TYPE_G_HIGH_RANGE_RETARDING,
            AdmixtureType.HYDRATION_STABILIZING,
        }

    @property
    def accelerates_set(self) -> bool:
        """True when this admixture pulls set and early strength forward."""
        return self in {
            AdmixtureType.TYPE_C_ACCELERATING,
            AdmixtureType.TYPE_E_WATER_REDUCING_ACCELERATING,
        }

    @property
    def reduces_water(self) -> bool:
        """True when the mix design may take credit for water reduction."""
        return self in {
            AdmixtureType.TYPE_A_WATER_REDUCING,
            AdmixtureType.TYPE_D_WATER_REDUCING_RETARDING,
            AdmixtureType.TYPE_E_WATER_REDUCING_ACCELERATING,
            AdmixtureType.TYPE_F_HIGH_RANGE,
            AdmixtureType.TYPE_G_HIGH_RANGE_RETARDING,
        }

    @property
    def is_high_range(self) -> bool:
        """True for the superplasticisers, which change how slump is judged."""
        return self in {
            AdmixtureType.TYPE_F_HIGH_RANGE,
            AdmixtureType.TYPE_G_HIGH_RANGE_RETARDING,
        }


class WaterSource(Enum):
    """Where the mixing water came from, ASTM C1602."""

    POTABLE = "potable"
    NON_POTABLE = "non_potable"
    RECLAIMED = "reclaimed"
    WASH_WATER = "wash_water"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> WaterSource:
        """Read a water source off a plant configuration."""
        member = _parse(cls, text, "water source")
        assert isinstance(member, WaterSource)
        return member

    @property
    def needs_qualification(self) -> bool:
        """True when C1602 wants strength and set time testing before use.

        Potable water is accepted with no testing at all. Everything else has
        to be qualified, and the qualification has to be kept current.
        """
        return self is not WaterSource.POTABLE

    @property
    def carries_solids(self) -> bool:
        """True when the source contributes solids that count as cementitious."""
        return self in {WaterSource.RECLAIMED, WaterSource.WASH_WATER}
