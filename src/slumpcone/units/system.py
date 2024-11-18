"""The two unit systems a plant can be filed under.

A plant is customary or metric and it does not mix. Every report, ticket and
mix design printed for that plant comes out in its system, whatever units the
record happened to be entered in. Keeping the preference in one place stops the
"``350`` of what?" argument that a mixed-unit ticket always starts.
"""

from __future__ import annotations

from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.units.dimension import Dimension
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature


class UnitSystem(Enum):
    """Which set of units a plant files and prints in."""

    CUSTOMARY = "customary"
    METRIC = "metric"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> UnitSystem:
        """Read a system from a configuration field."""
        key = text.strip().lower()
        aliases = {
            "customary": cls.CUSTOMARY,
            "us": cls.CUSTOMARY,
            "imperial": cls.CUSTOMARY,
            "english": cls.CUSTOMARY,
            "metric": cls.METRIC,
            "si": cls.METRIC,
        }
        if key not in aliases:
            raise ValidationError(f"unknown unit system {text!r}", field="unit_system")
        return aliases[key]

    @property
    def mass(self) -> str:
        """The unit batch weights print in."""
        return "lb" if self is UnitSystem.CUSTOMARY else "kg"

    @property
    def small_mass(self) -> str:
        """The unit an admixture charge prints in."""
        return "oz" if self is UnitSystem.CUSTOMARY else "g"

    @property
    def volume(self) -> str:
        """The unit a load size prints in."""
        return "yd3" if self is UnitSystem.CUSTOMARY else "m3"

    @property
    def small_volume(self) -> str:
        """The unit an admixture dose and a water draw print in."""
        return "floz" if self is UnitSystem.CUSTOMARY else "mL"

    @property
    def water_volume(self) -> str:
        """The unit added water prints in."""
        return "gal" if self is UnitSystem.CUSTOMARY else "L"

    @property
    def area(self) -> str:
        """The unit a placement's surface area prints in."""
        return "ft2" if self is UnitSystem.CUSTOMARY else "m2"

    @property
    def length(self) -> str:
        """The unit a slump and an aggregate size print in."""
        return "in" if self is UnitSystem.CUSTOMARY else "mm"

    @property
    def pressure(self) -> str:
        """The unit a strength prints in."""
        return "psi" if self is UnitSystem.CUSTOMARY else "MPa"

    @property
    def force(self) -> str:
        """The unit a testing machine reports its load in."""
        return "lbf" if self is UnitSystem.CUSTOMARY else "kN"

    @property
    def temperature(self) -> str:
        """The scale a concrete temperature prints on."""
        return "F" if self is UnitSystem.CUSTOMARY else "C"

    def preferred(self, dimension: Dimension) -> str:
        """The default print unit for ``dimension`` in this system."""
        table = {
            Dimension.MASS: self.mass,
            Dimension.VOLUME: self.volume,
            Dimension.AREA: self.area,
            Dimension.LENGTH: self.length,
            Dimension.PRESSURE: self.pressure,
            Dimension.FORCE: self.force,
            Dimension.TIME: "min",
        }
        return table[dimension]

    def convert(self, quantity: Quantity) -> Quantity:
        """Restate ``quantity`` in this system's default unit for its dimension."""
        return quantity.to(self.preferred(quantity.dimension))

    def convert_temperature(self, reading: Temperature) -> Temperature:
        """Restate ``reading`` on this system's scale."""
        return reading.to(self.temperature)
