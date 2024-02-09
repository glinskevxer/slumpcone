"""Identifier normalisation.

Every record in the register is found by a short human-written code: a plant
code, a mix design code, a ticket number, a truck number. They arrive from
dispatch screens, from lab spreadsheets and from vendor exports, and the same
mix is written ``4000P-57``, ``4000p 57`` and `` 4000P-57 `` depending on who
typed it. One normaliser, applied at the boundary, means the store never holds
two rows for the same thing.
"""

from __future__ import annotations

import re

from slumpcone.errors import ValidationError

_ALLOWED = re.compile(r"^[A-Z0-9][A-Z0-9\-]*$")
_SEPARATORS = re.compile(r"[\s_]+")
_RUNS = re.compile(r"-{2,}")

MAX_CODE_LENGTH = 32


def normalize_code(raw: str, *, field: str = "code", max_length: int = MAX_CODE_LENGTH) -> str:
    """Fold ``raw`` to the one spelling the register stores.

    Upper case, spaces and underscores become single hyphens, runs of hyphens
    collapse, and leading or trailing hyphens come off. What is left has to be
    letters, digits and interior hyphens, because a code that carries a slash
    or a comma breaks every export this thing writes.
    """
    if not isinstance(raw, str):
        raise ValidationError(f"{field} has to be text", field=field)
    folded = _SEPARATORS.sub("-", raw.strip().upper())
    folded = _RUNS.sub("-", folded).strip("-")
    if not folded:
        raise ValidationError(f"{field} cannot be blank", field=field)
    if len(folded) > max_length:
        raise ValidationError(
            f"{field} is {len(folded)} characters, the limit is {max_length}",
            field=field,
        )
    if not _ALLOWED.match(folded):
        raise ValidationError(
            f"{field} {raw!r} has a character that is not a letter, digit or hyphen",
            field=field,
        )
    return folded


def normalize_ticket_number(raw: str) -> str:
    """A delivery ticket number, which is digits and nothing else.

    Leading zeros are kept. Plants print them and the customer's copy has them,
    so dropping them makes two documents that do not match.
    """
    text = str(raw).strip()
    if not text:
        raise ValidationError("a ticket number is required", field="ticket_number")
    if not text.isdigit():
        raise ValidationError(f"ticket number {raw!r} is not all digits", field="ticket_number")
    if len(text) > 12:
        raise ValidationError("a ticket number is at most twelve digits", field="ticket_number")
    return text


def normalize_name(raw: str, *, field: str = "name", max_length: int = 120) -> str:
    """Collapse the whitespace in a free-text name and check it is not empty."""
    if not isinstance(raw, str):
        raise ValidationError(f"{field} has to be text", field=field)
    folded = " ".join(raw.split())
    if not folded:
        raise ValidationError(f"{field} cannot be blank", field=field)
    if len(folded) > max_length:
        raise ValidationError(
            f"{field} is {len(folded)} characters, the limit is {max_length}",
            field=field,
        )
    return folded


def is_code(raw: str) -> bool:
    """True when ``raw`` is already in normalised form."""
    try:
        return normalize_code(raw) == raw
    except ValidationError:
        return False
