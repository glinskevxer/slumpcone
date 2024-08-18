"""What comes out of a run: the rows that landed, and the ones that did not.

Three outcomes, not two. A row is accepted, quarantined because something about
it is wrong, or skipped because the register already holds it. Collapsing the
last two loses the distinction that matters most on a re-run: a file loaded
twice should be all duplicates and no quarantine, and a file that is all
quarantine is a mapping problem rather than a data problem.

The content hash is over the mapped values, not the raw line. Two exports of
the same batch from the same recorder differ in whitespace, column order and
sometimes in a trailing column the vendor added last week, and none of that
makes it a different batch.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


class RowOutcome(Enum):
    """What happened to one row."""

    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    DUPLICATE = "duplicate"

    def __str__(self) -> str:
        return self.value


def _canonical(value: Any) -> Any:
    if isinstance(value, Quantity):
        return ["quantity", round(value.base_value, 9)]
    if isinstance(value, Percent):
        return ["percent", round(value.value, 9)]
    if isinstance(value, datetime):
        return ["datetime", value.isoformat()]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, float):
        return round(value, 9)
    return value


def content_hash(values: Mapping[str, Any]) -> str:
    """A stable hash over the mapped values of one row.

    Keys are sorted and every value is reduced to a form that does not depend
    on the units it happened to arrive in, so the same batch exported in pounds
    and in kilograms hashes the same.
    """
    payload = {key: _canonical(value) for key, value in sorted(values.items())}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Quarantined:
    """One row that could not be accepted, and why."""

    line_number: int
    reasons: tuple[str, ...]
    values: dict[str, str] = field(default_factory=dict)

    def describe(self) -> str:
        """One line for a quarantine listing."""
        return f"line {self.line_number}: {'; '.join(self.reasons)}"


@dataclass(frozen=True, slots=True)
class AcceptedRow:
    """One row that made it through, with where it came from."""

    line_number: int
    values: dict[str, Any]
    digest: str

    def get(self, name: str, default: Any = None) -> Any:
        """One mapped value."""
        return self.values.get(name, default)


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Everything one run of one file produced."""

    profile_code: str
    source_name: str
    accepted: tuple[AcceptedRow, ...] = ()
    quarantined: tuple[Quarantined, ...] = ()
    duplicates: tuple[int, ...] = ()
    unmapped_columns: tuple[str, ...] = ()
    run_at: datetime | None = None

    @property
    def row_count(self) -> int:
        """How many rows the file held, not counting the header."""
        return len(self.accepted) + len(self.quarantined) + len(self.duplicates)

    @property
    def accepted_count(self) -> int:
        """How many rows landed."""
        return len(self.accepted)

    @property
    def is_clean(self) -> bool:
        """True when nothing was quarantined."""
        return not self.quarantined

    @property
    def is_all_duplicate(self) -> bool:
        """True when the whole file was already on file, which a re-run is."""
        return bool(self.duplicates) and not self.accepted and not self.quarantined

    def outcome_of(self, line_number: int) -> RowOutcome | None:
        """What happened to one line of the source file."""
        if any(row.line_number == line_number for row in self.accepted):
            return RowOutcome.ACCEPTED
        if any(row.line_number == line_number for row in self.quarantined):
            return RowOutcome.QUARANTINED
        if line_number in self.duplicates:
            return RowOutcome.DUPLICATE
        return None

    def reasons(self) -> tuple[str, ...]:
        """Every quarantine reason across the run, in line order."""
        collected: list[str] = []
        for row in self.quarantined:
            collected.extend(row.reasons)
        return tuple(collected)

    def describe(self) -> str:
        """A short run summary."""
        lines = [
            f"{self.source_name} through {self.profile_code}: "
            f"{self.accepted_count} accepted, {len(self.quarantined)} quarantined, "
            f"{len(self.duplicates)} already on file"
        ]
        if self.unmapped_columns:
            lines.append(f"  columns not mapped: {', '.join(self.unmapped_columns)}")
        lines.extend(f"  {row.describe()}" for row in self.quarantined)
        return "\n".join(lines)


def digests(rows: Iterable[AcceptedRow]) -> set[str]:
    """The content hashes of a set of accepted rows."""
    return {row.digest for row in rows}
