"""Turning a vendor's text into the types the register holds.

Numbers arrive with thousands separators, with the unit stuck on the end, and
occasionally in parentheses because the export was written by an accounting
package and a negative is ``(120)``. Dates arrive in at least four layouts and
two of them are ambiguous with each other. Blanks arrive as ``""``, ``-``,
``N/A`` and ``NULL``, all meaning the same thing.

Ambiguous dates are the one place this refuses to guess. ``03/04/2024`` is the
third of April or the fourth of March depending on who wrote the file, and
picking one silently produces a register that is wrong for four fifths of the
year. A profile that reads such a file has to say which layout it is.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from slumpcone.errors import ValidationError
from slumpcone.ingest.mapping import FieldKind, FieldSpec
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity

BLANKS = {"", "-", "--", "n/a", "na", "null", "none", "#n/a"}

TRUE_WORDS = {"1", "y", "yes", "t", "true", "on"}
FALSE_WORDS = {"0", "n", "no", "f", "false", "off"}

# Layouts tried in order for a date with no explicit format. The unambiguous
# ones come first and the ambiguous one is not in the list at all.
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d-%b-%Y", "%d %b %Y", "%b %d %Y")

_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)

_AMBIGUOUS = re.compile(r"^\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")

_NUMBER = re.compile(r"^[-+]?[0-9][0-9,_ ]*(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?$")

_TRAILING_UNIT = re.compile(r"(?<=[0-9\s])[A-Za-z][A-Za-z0-9/³^]*\.?$")


def is_blank(raw: str) -> bool:
    """True when a value means "nothing was recorded here"."""
    return raw.strip().lower() in BLANKS


def to_number(raw: str, *, field: str = "value") -> float:
    """Read a number written the way an export writes one."""
    text = raw.strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.rstrip("%").strip()
    # Drop a trailing unit, but only when the text is not already a number.
    # "4230 lb" and "4230lb" both need the unit taking off; "1.2e3" does not,
    # and stripping its exponent would silently divide it by a thousand.
    if not _NUMBER.match(text):
        without_unit = _TRAILING_UNIT.sub("", text).strip()
        if _NUMBER.match(without_unit):
            text = without_unit
    if not _NUMBER.match(text):
        raise ValidationError(f"cannot read {raw!r} as a number", field=field)
    value = float(text.replace(",", "").replace("_", "").replace(" ", ""))
    return -value if negative else value


def to_date(raw: str, *, field: str = "value", layout: str | None = None) -> date:
    """Read a date, refusing the layouts that could be two different days."""
    text = raw.strip()
    if layout is not None:
        try:
            return datetime.strptime(text, layout).date()
        except ValueError as exc:
            raise ValidationError(
                f"cannot read {raw!r} as a date in {layout}", field=field
            ) from exc
    for candidate in _DATE_FORMATS:
        try:
            return datetime.strptime(text, candidate).date()
        except ValueError:
            continue
    if _AMBIGUOUS.match(text):
        raise ValidationError(
            f"{raw!r} could be day first or month first; the profile has to say which",
            field=field,
        )
    raise ValidationError(f"cannot read {raw!r} as a date", field=field)


def to_datetime(raw: str, *, field: str = "value", layout: str | None = None) -> datetime:
    """Read a timestamp, falling back to a date at midnight."""
    text = raw.strip()
    if layout is not None:
        try:
            return datetime.strptime(text, layout)
        except ValueError as exc:
            raise ValidationError(
                f"cannot read {raw!r} as a timestamp in {layout}", field=field
            ) from exc
    for candidate in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, candidate)
        except ValueError:
            continue
    return datetime.combine(to_date(text, field=field), datetime.min.time())


def to_boolean(raw: str, *, field: str = "value") -> bool:
    """Read a flag written as a word, a letter or a digit."""
    text = raw.strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    raise ValidationError(f"cannot read {raw!r} as a yes or no", field=field)


def coerce(spec: FieldSpec, raw: str, *, date_format: str | None = None) -> Any:
    """Turn one raw value into the type its field spec says it is.

    A blank comes back as ``None`` whatever the field is, and it is the
    caller's job to decide whether that matters. Deciding here would mean the
    coercer needed to know which fields are required, which the profile already
    knows.
    """
    if is_blank(raw):
        return None
    if spec.kind is FieldKind.TEXT:
        return raw.strip()
    if spec.kind is FieldKind.NUMBER:
        return to_number(raw, field=spec.name)
    if spec.kind is FieldKind.PERCENT:
        return Percent(to_number(raw, field=spec.name))
    if spec.kind is FieldKind.QUANTITY:
        unit = spec.unit
        assert unit is not None
        return Quantity(to_number(raw, field=spec.name), unit)
    if spec.kind is FieldKind.DATE:
        return to_date(raw, field=spec.name, layout=date_format)
    if spec.kind is FieldKind.DATETIME:
        return to_datetime(raw, field=spec.name, layout=date_format)
    return to_boolean(raw, field=spec.name)
