"""Small helpers shared by every repository.

Three things were being written out by hand in each one and two of them had
already gone wrong.

The date window is the important one. Every "between these two days" query was
built as ``>= start AND < end + 'T23:59:59.999999'``, which excludes anything
recorded in the last microsecond of the closing day. Nothing has ever landed in
that microsecond and nothing ever will, but the expression is wrong and it was
copied into six places, so the seventh would have been wrong too. Here it is a
half open interval to the start of the next day, which is what was meant.

The band pack and unpack were duplicated in two repositories with the same
three-column layout and the same ``None`` handling, which is one edit away from
diverging.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from slumpcone.tolerance import Band


def day_range(start: date, end: date) -> tuple[str, str]:
    """A half open window covering both ``start`` and ``end`` in full.

    The pair is meant for ``WHERE column >= ? AND column < ?``, so the second
    value is the start of the day after ``end``.
    """
    return (start.isoformat(), (end + timedelta(days=1)).isoformat())


def band_columns(band: Band | None) -> tuple[float | None, float | None, float | None]:
    """A band as the three nullable columns the schema stores it in."""
    if band is None:
        return (None, None, None)
    return (band.target, band.minus, band.plus)


def band_from(target: float | None, minus: float | None, plus: float | None) -> Band | None:
    """Rebuild a band from its three columns, or ``None`` when it was not set."""
    if target is None or (minus is None and plus is None):
        return None
    return Band(target, minus, plus)


def moment(value: Any) -> datetime | None:
    """A nullable timestamp column as a datetime."""
    return None if value is None else datetime.fromisoformat(str(value))


def day(value: Any) -> date | None:
    """A nullable date column as a date."""
    return None if value is None else date.fromisoformat(str(value))


def text(value: Any) -> str | None:
    """A nullable text column, without turning ``None`` into ``"None"``."""
    return None if value is None else str(value)


def number(value: Any) -> float | None:
    """A nullable numeric column as a float."""
    return None if value is None else float(value)
