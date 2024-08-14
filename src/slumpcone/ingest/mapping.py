"""Column mapping profiles: which of a vendor's columns is which of ours.

Every plant runs a different batch recorder and every recorder writes its own
column names. A profile is the translation, written once per system, and it is
data rather than code so a new plant does not need a release.

Two things a profile has to carry beyond the names. The unit, because a column
called ``water`` is gallons on one system and pounds on another and neither
says so. And whether the field is required, because a missing optional column
is a fact about that vendor's export and a missing required one is a file that
cannot be read at all.

A profile deliberately does not fail on columns it does not know about. Vendor
exports carry twenty columns nobody needs, they add more with every release,
and a profile that breaks when a new one appears is a profile that breaks every
year.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.ingest.source import SourceRow, normalize_header


class FieldKind(Enum):
    """What sort of value a mapped column holds."""

    TEXT = "text"
    NUMBER = "number"
    QUANTITY = "quantity"
    PERCENT = "percent"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"

    def __str__(self) -> str:
        return self.value

    @property
    def needs_a_unit(self) -> bool:
        """True when a field of this kind is meaningless without a unit."""
        return self is FieldKind.QUANTITY


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One canonical field and the column names it might arrive under."""

    name: str
    columns: tuple[str, ...]
    kind: FieldKind = FieldKind.TEXT
    unit: str | None = None
    required: bool = False
    default: str | None = None

    def __post_init__(self) -> None:
        folded = normalize_header(self.name)
        if not folded:
            raise ValidationError("a field needs a name", field="name")
        object.__setattr__(self, "name", folded)
        if not self.columns:
            raise ValidationError(
                f"{folded} has no source columns to look for", field="columns"
            )
        object.__setattr__(
            self, "columns", tuple(normalize_header(column) for column in self.columns)
        )
        if self.kind.needs_a_unit and self.unit is None:
            raise ValidationError(f"{folded} is a quantity and needs a unit", field="unit")
        if self.required and self.default is not None:
            raise ValidationError(
                f"{folded} is required, so a default makes no sense", field="default"
            )

    def column_in(self, header: Sequence[str]) -> str | None:
        """Which of this field's candidate columns is in ``header``, if any."""
        available = {normalize_header(name) for name in header}
        for candidate in self.columns:
            if candidate in available:
                return candidate
        return None


@dataclass(frozen=True, slots=True)
class MappingProfile:
    """One vendor export format, as a set of field specs."""

    code: str
    name: str
    fields: tuple[FieldSpec, ...]
    delimiter: str | None = None
    skip_lines: int = 0
    date_format: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_code(self.code, field="profile_code"))
        object.__setattr__(self, "name", normalize_name(self.name, field="profile_name"))
        if not self.fields:
            raise ValidationError("a profile needs at least one field", field="fields")
        seen: set[str] = set()
        for spec in self.fields:
            if spec.name in seen:
                raise ValidationError(f"{spec.name} is mapped twice", field="fields")
            seen.add(spec.name)
        if self.skip_lines < 0:
            raise ValidationError("skip_lines cannot be negative", field="skip_lines")

    @property
    def field_names(self) -> tuple[str, ...]:
        """Every canonical field this profile produces, in order."""
        return tuple(spec.name for spec in self.fields)

    @property
    def required_names(self) -> tuple[str, ...]:
        """The fields a file has to carry to be readable at all."""
        return tuple(spec.name for spec in self.fields if spec.required)

    def field(self, name: str) -> FieldSpec:
        """One field spec by canonical name."""
        wanted = normalize_header(name)
        for spec in self.fields:
            if spec.name == wanted:
                return spec
        raise ValidationError(f"{wanted} is not in this profile", field="name")

    def resolve(self, header: Sequence[str]) -> dict[str, str]:
        """Canonical name to source column, for the fields this file has."""
        found: dict[str, str] = {}
        for spec in self.fields:
            column = spec.column_in(header)
            if column is not None:
                found[spec.name] = column
        return found

    def missing_required(self, header: Sequence[str]) -> tuple[str, ...]:
        """Required fields this file does not carry a column for."""
        resolved = self.resolve(header)
        return tuple(name for name in self.required_names if name not in resolved)

    def unmapped_columns(self, header: Sequence[str]) -> tuple[str, ...]:
        """Columns in the file that this profile has no field for."""
        claimed = set(self.resolve(header).values())
        return tuple(
            name
            for name in (normalize_header(entry) for entry in header)
            if name and name not in claimed
        )

    def check_header(self, header: Sequence[str]) -> None:
        """Refuse a file that cannot be read with this profile."""
        missing = self.missing_required(header)
        if missing:
            raise ValidationError(
                f"{self.code} needs {', '.join(missing)} and the file has none of them",
                field="header",
            )

    def raw_values(self, row: SourceRow, header: Sequence[str]) -> dict[str, str]:
        """The row's values keyed by canonical field name, before coercion."""
        resolved = self.resolve(header)
        values: dict[str, str] = {}
        for spec in self.fields:
            column = resolved.get(spec.name)
            if column is None:
                if spec.default is not None:
                    values[spec.name] = spec.default
                continue
            text = row.values.get(column, "")
            if not text.strip() and spec.default is not None:
                text = spec.default
            values[spec.name] = text
        return values

    def describe(self) -> str:
        """One line for a profile listing."""
        return (
            f"{self.code}  {self.name}  {len(self.fields)} fields, "
            f"{len(self.required_names)} required"
        )
