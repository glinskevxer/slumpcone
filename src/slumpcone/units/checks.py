"""Guards for quantities, because the same four lines were everywhere.

Nearly every record in this package starts by checking that the quantity it was
handed measures what it should and is not negative. Written out, that is three
or four lines per field and it was written out about eighty times, with the
message spelled slightly differently in a third of them.

The helpers take the noun the message should use, so the wording stays the
plant's rather than becoming a generic "invalid value for field capacity". They
return the quantity, so a constructor can check and assign in one expression.
"""

from __future__ import annotations

from slumpcone.errors import ValidationError
from slumpcone.units.dimension import Dimension
from slumpcone.units.quantity import Quantity


def require_dimension(
    value: Quantity, dimension: Dimension, noun: str, *, field: str
) -> Quantity:
    """Refuse a quantity that measures something else."""
    if value.dimension is not dimension:
        raise ValidationError(f"{noun} is a {dimension}", field=field)
    return value


def require_mass(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse anything that is not a weight."""
    return require_dimension(value, Dimension.MASS, noun, field=field)


def require_volume(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse anything that is not a volume."""
    return require_dimension(value, Dimension.VOLUME, noun, field=field)


def require_length(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse anything that is not a length."""
    return require_dimension(value, Dimension.LENGTH, noun, field=field)


def require_pressure(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse anything that is not a pressure."""
    return require_dimension(value, Dimension.PRESSURE, noun, field=field)


def require_force(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse anything that is not a force."""
    return require_dimension(value, Dimension.FORCE, noun, field=field)


def require_area(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse anything that is not an area."""
    return require_dimension(value, Dimension.AREA, noun, field=field)


def require_positive(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse a quantity that is zero or below."""
    if value.value <= 0.0:
        raise ValidationError(f"{noun} has to be positive", field=field)
    return value


def require_not_negative(value: Quantity, noun: str, *, field: str) -> Quantity:
    """Refuse a quantity below zero, allowing zero itself."""
    if value.value < 0.0:
        raise ValidationError(f"{noun} cannot be negative", field=field)
    return value
