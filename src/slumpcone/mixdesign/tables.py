"""The proportioning tables, and the interpolation rules that go with them.

These are the tables a mixture is first proportioned from before any trial
batch exists. Three of them and they read differently.

Water demand is a lookup on slump band and aggregate size, and it does *not*
interpolate on slump: the table gives bands, a mixture is in one of them, and
reading between two bands invents a precision the table does not have.

The coarse aggregate factor is a lookup on aggregate size and sand fineness
modulus, and it *does* interpolate, on fineness modulus only, because the sand
actually varies continuously and a tenth of fineness modulus moves the answer.

The ratio table is a lookup on strength and interpolates on strength, but it
runs the other way from everything else: a higher strength means a lower ratio,
so the interpolation has to be written against a decreasing series.
"""

from __future__ import annotations

from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# The aggregate sizes every table is indexed on, in inches.
SIZES: tuple[float, ...] = (0.375, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)

# The fineness moduli the coarse aggregate table is indexed on.
MODULI: tuple[float, ...] = (2.40, 2.60, 2.80, 3.00)


class SlumpBand(Enum):
    """The three slump bands the water demand table is written for."""

    LOW = "1 to 2 in"
    MEDIUM = "3 to 4 in"
    HIGH = "6 to 7 in"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def of(cls, slump: Quantity) -> SlumpBand:
        """Which band a slump target falls in."""
        if slump.dimension.value != "length":
            raise ValidationError("a slump is a length", field="slump")
        inches = slump.to("in").value
        if inches < 1.0:
            raise ValidationError(
                "the water demand table starts at a one inch slump", field="slump"
            )
        if inches <= 2.0 + 1e-9:
            return cls.LOW
        if inches <= 4.0 + 1e-9:
            return cls.MEDIUM
        if inches <= 7.0 + 1e-9:
            return cls.HIGH
        raise ValidationError(
            "the water demand table stops at a seven inch slump; above that a "
            "high range admixture is doing the work and the table does not apply",
            field="slump",
        )


class ExposureSeverity(Enum):
    """How hard a freeze thaw environment the air content is chosen for."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"

    def __str__(self) -> str:
        return self.value


# Mixing water in lb/yd3, by slump band and aggregate size.
_WATER_PLAIN: dict[SlumpBand, tuple[float, ...]] = {
    SlumpBand.LOW: (350.0, 335.0, 315.0, 300.0, 275.0, 260.0, 220.0),
    SlumpBand.MEDIUM: (385.0, 365.0, 340.0, 325.0, 300.0, 285.0, 245.0),
    SlumpBand.HIGH: (410.0, 385.0, 360.0, 340.0, 315.0, 300.0, 270.0),
}

_WATER_ENTRAINED: dict[SlumpBand, tuple[float, ...]] = {
    SlumpBand.LOW: (305.0, 295.0, 280.0, 270.0, 250.0, 240.0, 205.0),
    SlumpBand.MEDIUM: (340.0, 325.0, 305.0, 295.0, 275.0, 265.0, 225.0),
    SlumpBand.HIGH: (365.0, 345.0, 325.0, 310.0, 290.0, 280.0, 260.0),
}

# Air a mixture traps whether or not anybody asked for it.
_ENTRAPPED_AIR: tuple[float, ...] = (3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.3)

# Total air to aim for when the mixture is deliberately entrained.
_ENTRAINED_AIR: dict[ExposureSeverity, tuple[float, ...]] = {
    ExposureSeverity.MILD: (4.5, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5),
    ExposureSeverity.MODERATE: (6.0, 5.5, 5.0, 4.5, 4.5, 4.0, 3.5),
    ExposureSeverity.SEVERE: (7.5, 7.0, 6.0, 6.0, 5.5, 5.0, 4.5),
}

# Dry rodded coarse aggregate volume per unit volume of concrete, by aggregate
# size and sand fineness modulus.
_COARSE_FACTOR: dict[float, tuple[float, ...]] = {
    0.375: (0.50, 0.48, 0.46, 0.44),
    0.5: (0.59, 0.57, 0.55, 0.53),
    0.75: (0.66, 0.64, 0.62, 0.60),
    1.0: (0.71, 0.69, 0.67, 0.65),
    1.5: (0.75, 0.73, 0.71, 0.69),
    2.0: (0.78, 0.76, 0.74, 0.72),
    3.0: (0.82, 0.80, 0.78, 0.76),
}

# Water-cementitious ratio against twenty eight day strength, strongest first.
_RATIO_PLAIN: tuple[tuple[float, float], ...] = (
    (6000.0, 0.41),
    (5000.0, 0.48),
    (4000.0, 0.57),
    (3000.0, 0.68),
    (2000.0, 0.82),
)

_RATIO_ENTRAINED: tuple[tuple[float, float], ...] = (
    (5000.0, 0.40),
    (4000.0, 0.48),
    (3000.0, 0.59),
    (2000.0, 0.74),
)


def _size_index(nominal_max_size: Quantity) -> int:
    if nominal_max_size.dimension.value != "length":
        raise ValidationError("a nominal maximum size is a length", field="nominal_max_size")
    inches = nominal_max_size.to("in").value
    for index, size in enumerate(SIZES):
        if abs(inches - size) < 1e-6:
            return index
    raise ValidationError(
        f"the tables have no row for a {inches:g} inch aggregate", field="nominal_max_size"
    )


def water_demand(
    nominal_max_size: Quantity, slump: Quantity, *, air_entrained: bool
) -> MassPerVolume:
    """Mixing water for a first proportioning, before any admixture credit."""
    index = _size_index(nominal_max_size)
    table = _WATER_ENTRAINED if air_entrained else _WATER_PLAIN
    return MassPerVolume(table[SlumpBand.of(slump)][index], "lb", "yd3")


def entrapped_air(nominal_max_size: Quantity) -> Percent:
    """The air a mixture holds without an entraining admixture."""
    return Percent(_ENTRAPPED_AIR[_size_index(nominal_max_size)])


def target_air(nominal_max_size: Quantity, severity: ExposureSeverity) -> Percent:
    """The total air to aim for in an entrained mixture."""
    return Percent(_ENTRAINED_AIR[severity][_size_index(nominal_max_size)])


def coarse_aggregate_factor(nominal_max_size: Quantity, fineness_modulus: float) -> float:
    """Dry rodded coarse aggregate volume per unit volume of concrete.

    Interpolated on fineness modulus, and refused outside the table rather than
    clamped: a sand at 3.4 is not a sand this table was built from and pinning
    it to the 3.00 column hides that.
    """
    row = _COARSE_FACTOR[SIZES[_size_index(nominal_max_size)]]
    if not MODULI[0] - 1e-9 <= fineness_modulus <= MODULI[-1] + 1e-9:
        raise ValidationError(
            f"fineness modulus {fineness_modulus:.2f} is outside the "
            f"{MODULI[0]:.2f} to {MODULI[-1]:.2f} the table covers",
            field="fineness_modulus",
        )
    for index in range(len(MODULI) - 1):
        low, high = MODULI[index], MODULI[index + 1]
        if low - 1e-9 <= fineness_modulus <= high + 1e-9:
            share = (fineness_modulus - low) / (high - low)
            return row[index] + share * (row[index + 1] - row[index])
    return row[-1]


def ratio_for_strength(strength: Quantity, *, air_entrained: bool) -> float:
    """The water-cementitious ratio the table expects to give ``strength``.

    Interpolated between rows. Refused outside them, because extrapolating this
    table is how a mixture gets proportioned at a ratio nobody has data for.
    """
    if strength.dimension.value != "pressure":
        raise ValidationError("a strength is a pressure", field="strength")
    table = _RATIO_ENTRAINED if air_entrained else _RATIO_PLAIN
    psi = strength.to("psi").value
    highest, lowest = table[0][0], table[-1][0]
    if not lowest - 1e-6 <= psi <= highest + 1e-6:
        raise ValidationError(
            f"{psi:.0f} psi is outside the {lowest:.0f} to {highest:.0f} the table covers",
            field="strength",
        )
    for (upper_psi, upper_ratio), (lower_psi, lower_ratio) in zip(
        table, table[1:], strict=False
    ):
        if lower_psi - 1e-6 <= psi <= upper_psi + 1e-6:
            share = (psi - lower_psi) / (upper_psi - lower_psi)
            return lower_ratio + share * (upper_ratio - lower_ratio)
    return table[-1][1]
