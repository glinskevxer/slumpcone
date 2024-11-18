"""Physical dimensions and the unit table.

A unit is a symbol, the dimension it measures, and the factor that takes it to
that dimension's base unit. Base units are SI: kilogram, cubic metre, metre,
pascal, second. Every conversion goes through the base, so adding a unit means
adding one row and nothing else.

Ready-mix runs on US customary units in most of the country and on SI in the
rest, and a plant does not get to pick per field. Both live in the same table so
a mix design filed in one can be read in the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import UnitError


class Dimension(Enum):
    """What a unit measures."""

    MASS = "mass"
    VOLUME = "volume"
    AREA = "area"
    LENGTH = "length"
    PRESSURE = "pressure"
    FORCE = "force"
    TIME = "time"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class UnitDef:
    """One row of the unit table."""

    symbol: str
    dimension: Dimension
    to_base: float
    plural: str | None = None


_TABLE: tuple[UnitDef, ...] = (
    UnitDef("kg", Dimension.MASS, 1.0),
    UnitDef("g", Dimension.MASS, 1e-3),
    UnitDef("t", Dimension.MASS, 1000.0),
    UnitDef("lb", Dimension.MASS, 0.45359237),
    UnitDef("oz", Dimension.MASS, 0.028349523125),
    UnitDef("ton", Dimension.MASS, 907.18474),
    UnitDef("m3", Dimension.VOLUME, 1.0),
    UnitDef("L", Dimension.VOLUME, 1e-3),
    UnitDef("mL", Dimension.VOLUME, 1e-6),
    UnitDef("yd3", Dimension.VOLUME, 0.764554857984),
    UnitDef("ft3", Dimension.VOLUME, 0.028316846592),
    UnitDef("gal", Dimension.VOLUME, 0.003785411784),
    UnitDef("floz", Dimension.VOLUME, 2.95735295625e-5),
    UnitDef("m2", Dimension.AREA, 1.0),
    UnitDef("cm2", Dimension.AREA, 1e-4),
    UnitDef("mm2", Dimension.AREA, 1e-6),
    UnitDef("in2", Dimension.AREA, 0.00064516),
    UnitDef("ft2", Dimension.AREA, 0.09290304),
    UnitDef("yd2", Dimension.AREA, 0.83612736),
    UnitDef("m", Dimension.LENGTH, 1.0),
    UnitDef("cm", Dimension.LENGTH, 1e-2),
    UnitDef("mm", Dimension.LENGTH, 1e-3),
    UnitDef("in", Dimension.LENGTH, 0.0254),
    UnitDef("ft", Dimension.LENGTH, 0.3048),
    UnitDef("Pa", Dimension.PRESSURE, 1.0),
    UnitDef("kPa", Dimension.PRESSURE, 1e3),
    UnitDef("MPa", Dimension.PRESSURE, 1e6),
    UnitDef("psi", Dimension.PRESSURE, 6894.757293168361),
    UnitDef("N", Dimension.FORCE, 1.0),
    UnitDef("kN", Dimension.FORCE, 1e3),
    UnitDef("lbf", Dimension.FORCE, 4.4482216152605),
    UnitDef("kip", Dimension.FORCE, 4448.2216152605),
    UnitDef("s", Dimension.TIME, 1.0),
    UnitDef("min", Dimension.TIME, 60.0),
    UnitDef("h", Dimension.TIME, 3600.0),
)

_BY_SYMBOL: dict[str, UnitDef] = {u.symbol: u for u in _TABLE}

_ALIASES: dict[str, str] = {
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "kilogram": "kg",
    "kilograms": "kg",
    "tonne": "t",
    "tonnes": "t",
    "tons": "ton",
    "cy": "yd3",
    "yd^3": "yd3",
    "yd³": "yd3",
    "cuyd": "yd3",
    "cf": "ft3",
    "ft^3": "ft3",
    "ft³": "ft3",
    "cuft": "ft3",
    "m^3": "m3",
    "sf": "ft2",
    "sqft": "ft2",
    "ft^2": "ft2",
    "ft²": "ft2",
    "sy": "yd2",
    "sqyd": "yd2",
    "m^2": "m2",
    "m²": "m2",
    "sqm": "m2",
    "m³": "m3",
    "l": "L",
    "litre": "L",
    "liter": "L",
    "gallon": "gal",
    "gallons": "gal",
    "fl_oz": "floz",
    "fluid_ounce": "floz",
    "inch": "in",
    "inches": "in",
    '"': "in",
    "feet": "ft",
    "foot": "ft",
    "'": "ft",
    "metre": "m",
    "meter": "m",
    "sec": "s",
    "second": "s",
    "seconds": "s",
    "minute": "min",
    "minutes": "min",
    "hour": "h",
    "hours": "h",
    "hr": "h",
    "lbsf": "lbf",
    "poundforce": "lbf",
    "kips": "kip",
    "newton": "N",
    "newtons": "N",
}


def resolve(symbol: str) -> UnitDef:
    """Return the unit table row for ``symbol``, following aliases.

    Raises :class:`UnitError` when the symbol is not one this package knows.
    Matching is exact after alias lookup, because ``in`` and ``IN`` are both
    written on real tickets but ``Mpa`` never means anything but a typo.
    """
    key = symbol.strip()
    if not key:
        raise UnitError("a unit symbol is required", field="unit")
    key = _ALIASES.get(key, _ALIASES.get(key.lower(), key))
    unit = _BY_SYMBOL.get(key)
    if unit is None:
        raise UnitError(f"unknown unit {symbol!r}", field="unit")
    return unit


def symbols_for(dimension: Dimension) -> tuple[str, ...]:
    """Every symbol this package knows for ``dimension``, in table order."""
    return tuple(u.symbol for u in _TABLE if u.dimension is dimension)


def dimension_of(symbol: str) -> Dimension:
    """The dimension ``symbol`` measures."""
    return resolve(symbol).dimension
