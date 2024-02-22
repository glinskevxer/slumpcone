"""Fixed width text tables.

Every report this thing writes ends up pasted into an email or printed on the
plant's dot matrix, so the output is plain text with no colour and no escape
codes. Columns size themselves to their contents and numbers line up on the
right, because a column of batch weights that does not line up is unreadable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError


class Align(Enum):
    """Which way a column's cells are padded."""

    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"

    def pad(self, text: str, width: int) -> str:
        """Pad ``text`` out to ``width``."""
        if self is Align.RIGHT:
            return text.rjust(width)
        if self is Align.CENTER:
            return text.center(width)
        return text.ljust(width)


@dataclass(frozen=True, slots=True)
class Column:
    """One column: its heading, how its cells are aligned, and a minimum width."""

    heading: str
    align: Align = Align.LEFT
    min_width: int = 0

    def __post_init__(self) -> None:
        if self.min_width < 0:
            raise ValidationError("a column width cannot be negative", field="min_width")


GAP = "  "


def render_table(
    columns: Sequence[Column],
    rows: Iterable[Sequence[object]],
    *,
    rule: bool = True,
) -> str:
    """Lay out ``rows`` under ``columns``.

    Every row has to have as many cells as there are columns. A short row is a
    bug in the caller and printing it ragged hides that, so it raises instead.
    """
    if not columns:
        raise ValidationError("a table needs at least one column", field="columns")
    body = [[_cell(value) for value in row] for row in rows]
    for index, row in enumerate(body):
        if len(row) != len(columns):
            raise ValidationError(
                f"row {index} has {len(row)} cells and the table has {len(columns)}",
                field="rows",
            )
    widths = []
    for position, column in enumerate(columns):
        widest = max(
            [len(column.heading), column.min_width, *[len(row[position]) for row in body]]
        )
        widths.append(widest)
    lines = [
        GAP.join(
            column.align.pad(column.heading, width)
            for column, width in zip(columns, widths, strict=True)
        ).rstrip()
    ]
    if rule:
        lines.append(GAP.join("-" * width for width in widths))
    for row in body:
        lines.append(
            GAP.join(
                column.align.pad(cell, width)
                for column, cell, width in zip(columns, row, widths, strict=True)
            ).rstrip()
        )
    return "\n".join(lines)


def _cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def render_pairs(pairs: Iterable[tuple[str, object]], *, separator: str = ": ") -> str:
    """Lay out label and value pairs with the labels padded to a common width."""
    items = [(label, _cell(value)) for label, value in pairs]
    if not items:
        return ""
    width = max(len(label) for label, _ in items)
    return "\n".join(f"{label.ljust(width)}{separator}{value}" for label, value in items)


def heading(text: str, *, underline: str = "=") -> str:
    """A title with a rule under it."""
    if len(underline) != 1:
        raise ValidationError("an underline is a single character", field="underline")
    return f"{text}\n{underline * len(text)}"


def indent(text: str, *, spaces: int = 2) -> str:
    """Indent every non-empty line of ``text``."""
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())


def bullet_list(items: Iterable[str], *, marker: str = "-") -> str:
    """A list with each item on its own line, wrapped lines hanging."""
    lines: list[str] = []
    for item in items:
        parts = item.splitlines() or [""]
        lines.append(f"{marker} {parts[0]}")
        lines.extend(f"{' ' * (len(marker) + 1)}{part}" for part in parts[1:])
    return "\n".join(lines)
