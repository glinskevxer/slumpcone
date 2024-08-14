"""Reading a vendor's export, which is never quite a CSV.

Batch recorders and lab systems export text files and every one of them is
wrong in its own way. Byte order marks on the first header. Semicolons because
the machine was configured for a European locale. Blank lines between the
header and the data. Trailing commas that give every row one more field than
the header. Titles above the header that are not data at all.

None of that is worth failing over, and none of it should be silently
tolerated either, so the reader normalises what it safely can, records what it
could not, and carries the source line number on every row so a complaint can
point at a line in the file the operator is looking at.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from slumpcone.errors import ValidationError

# Delimiters worth trying, most likely first.
CANDIDATE_DELIMITERS = (",", ";", "\t", "|")


def normalize_header(name: str) -> str:
    """Fold a column heading to the form a mapping profile is written in.

    Lower case, spaces and punctuation to single underscores, no leading or
    trailing underscore. ``"Batch Wt. (lb)"`` and ``"batch_wt_lb"`` are the same
    column and a profile should only have to name it once.
    """
    folded = name.strip().lstrip("﻿").lower()
    kept = [character if character.isalnum() else "_" for character in folded]
    squashed = "".join(kept)
    while "__" in squashed:
        squashed = squashed.replace("__", "_")
    return squashed.strip("_")


@dataclass(frozen=True, slots=True)
class SourceRow:
    """One row of a source file, with where it came from."""

    line_number: int
    values: dict[str, str]
    extra: tuple[str, ...] = field(default=())
    missing: tuple[str, ...] = field(default=())

    def get(self, column: str, default: str = "") -> str:
        """One column's value, or ``default`` when the column is not there."""
        return self.values.get(normalize_header(column), default)

    def has(self, column: str) -> bool:
        """True when the row carries a non-empty value for a column."""
        return bool(self.get(column).strip())

    @property
    def is_ragged(self) -> bool:
        """True when the row did not have the same fields as the header."""
        return bool(self.extra or self.missing)

    @property
    def is_blank(self) -> bool:
        """True when every field is empty."""
        return all(not value.strip() for value in self.values.values())

    def describe(self) -> str:
        """One line naming the row for a quarantine note."""
        return f"line {self.line_number}"


def sniff_delimiter(sample: str) -> str:
    """Guess the delimiter from the first line that has any of the candidates.

    A count on the header line beats a heuristic on the whole file. A file with
    commas inside quoted addresses and semicolons between the fields fools
    anything that counts characters over the body.
    """
    for line in sample.splitlines():
        if not line.strip():
            continue
        counts = {
            delimiter: len(next(csv.reader([line], delimiter=delimiter))) - 1
            for delimiter in CANDIDATE_DELIMITERS
        }
        best = max(counts, key=lambda key: counts[key])
        if counts[best] > 0:
            return best
    raise ValidationError("no delimiter found in the file", field="delimiter")


def read_delimited(
    text: str,
    *,
    delimiter: str | None = None,
    skip_lines: int = 0,
) -> tuple[tuple[str, ...], list[SourceRow]]:
    """Read a delimited file into a header and a list of rows.

    ``skip_lines`` drops leading junk: recorder exports often carry a plant name
    and a date above the real header. Blank rows are read and kept rather than
    dropped, because a blank row in the middle of a file is usually the sign of
    something worse further down.
    """
    if skip_lines < 0:
        raise ValidationError("skip_lines cannot be negative", field="skip_lines")
    body = text.lstrip("﻿")
    lines = body.splitlines()
    if skip_lines:
        lines = lines[skip_lines:]
    if not lines:
        raise ValidationError("the file has no rows", field="text")
    while lines and not lines[0].strip():
        lines.pop(0)
        skip_lines += 1
    if not lines:
        raise ValidationError("the file has no rows", field="text")
    chosen = delimiter or sniff_delimiter("\n".join(lines[:5]))
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=chosen)
    raw_header = next(reader, None)
    if raw_header is None:
        raise ValidationError("the file has no header", field="text")
    header = tuple(normalize_header(name) for name in raw_header)
    if not any(header):
        raise ValidationError("the header row is empty", field="text")
    rows: list[SourceRow] = []
    for offset, record in enumerate(reader, start=skip_lines + 2):
        rows.append(_row_from(header, record, offset))
    return header, rows


def _row_from(header: Sequence[str], record: Sequence[str], line_number: int) -> SourceRow:
    values: dict[str, str] = {}
    for index, name in enumerate(header):
        if not name:
            continue
        values[name] = record[index].strip() if index < len(record) else ""
    missing = tuple(name for index, name in enumerate(header) if name and index >= len(record))
    extra = tuple(record[len(header) :]) if len(record) > len(header) else ()
    return SourceRow(line_number, values, extra, missing)


def rows_with_values(rows: Iterator[SourceRow] | list[SourceRow]) -> list[SourceRow]:
    """Drop the blank rows, keeping everything else."""
    return [row for row in rows if not row.is_blank]
