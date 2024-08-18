"""The run: read, map, coerce, check, dedupe.

Every row is taken as far as it can go and every complaint about it is
collected, rather than stopping at the first. An operator fixing an export
wants the whole list, not one problem per attempt, and a file with four bad
columns takes four passes to fix if the reader stops at the first one.

Duplicate detection runs against two sets at once: what the register already
holds, and what has already been accepted in this same file. Recorder exports
repeat rows within a file more often than they repeat them between files,
because the operator re-printed a range and the range overlapped.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from slumpcone.errors import ValidationError
from slumpcone.ingest.coerce import coerce
from slumpcone.ingest.mapping import MappingProfile
from slumpcone.ingest.result import AcceptedRow, IngestResult, Quarantined, content_hash
from slumpcone.ingest.source import SourceRow, read_delimited

Validator = Callable[[Mapping[str, Any]], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class RowReview:
    """One row after coercion, before the duplicate check."""

    line_number: int
    values: dict[str, Any]
    reasons: tuple[str, ...]
    raw: dict[str, str]

    @property
    def is_usable(self) -> bool:
        """True when nothing about the row stops it being accepted."""
        return not self.reasons


def review_row(
    profile: MappingProfile,
    row: SourceRow,
    header: tuple[str, ...],
    validators: tuple[Validator, ...] = (),
) -> RowReview:
    """Map and coerce one row, collecting every complaint about it."""
    raw = profile.raw_values(row, header)
    values: dict[str, Any] = {}
    reasons: list[str] = []
    if row.extra:
        reasons.append(f"{len(row.extra)} field(s) past the end of the header")
    for spec in profile.fields:
        if spec.name not in raw:
            if spec.required:
                reasons.append(f"{spec.name} has no column in this file")
            continue
        try:
            value = coerce(spec, raw[spec.name], date_format=profile.date_format)
        except ValidationError as exc:
            reasons.append(str(exc))
            continue
        if value is None:
            if spec.required:
                reasons.append(f"{spec.name} is blank")
            continue
        values[spec.name] = value
    if not reasons:
        for validator in validators:
            reasons.extend(validator(values))
    return RowReview(row.line_number, values, tuple(reasons), raw)


def run_ingest(
    profile: MappingProfile,
    text: str,
    source_name: str,
    *,
    known_digests: Collection[str] = (),
    validators: tuple[Validator, ...] = (),
    run_at: datetime | None = None,
) -> IngestResult:
    """Read one file through one profile."""
    header, rows = read_delimited(
        text, delimiter=profile.delimiter, skip_lines=profile.skip_lines
    )
    profile.check_header(header)
    seen: set[str] = set(known_digests)
    accepted: list[AcceptedRow] = []
    quarantined: list[Quarantined] = []
    duplicates: list[int] = []
    for row in rows:
        if row.is_blank:
            continue
        review = review_row(profile, row, header, validators)
        if not review.is_usable:
            quarantined.append(Quarantined(review.line_number, review.reasons, review.raw))
            continue
        digest = content_hash(review.values)
        if digest in seen:
            duplicates.append(review.line_number)
            continue
        seen.add(digest)
        accepted.append(AcceptedRow(review.line_number, review.values, digest))
    return IngestResult(
        profile.code,
        source_name,
        tuple(accepted),
        tuple(quarantined),
        tuple(duplicates),
        profile.unmapped_columns(header),
        run_at,
    )


def required_together(*names: str) -> Validator:
    """A validator demanding that a set of fields is all present or all absent.

    Half a set is the shape a bad export takes: a slump column with no slump
    time beside it, or an air content with no method. Either the technician ran
    the test or they did not.
    """

    def check(values: Mapping[str, Any]) -> tuple[str, ...]:
        present = [name for name in names if values.get(name) is not None]
        if present and len(present) != len(names):
            missing = [name for name in names if name not in present]
            return (f"{', '.join(present)} present without {', '.join(missing)}",)
        return ()

    return check


def one_of(*names: str) -> Validator:
    """A validator demanding at least one of a set of fields."""

    def check(values: Mapping[str, Any]) -> tuple[str, ...]:
        if any(values.get(name) is not None for name in names):
            return ()
        return (f"none of {', '.join(names)} is filled in",)

    return check
