from __future__ import annotations

import pytest

from slumpcone.errors import (
    ConflictError,
    NotFoundError,
    RuleViolationError,
    SlumpconeError,
    UnitError,
    ValidationError,
)


class CaseHierarchy:
    def test_everything_derives_from_the_base(self) -> None:
        subclasses = (
            ValidationError,
            UnitError,
            NotFoundError,
            ConflictError,
            RuleViolationError,
        )
        for cls in subclasses:
            assert issubclass(cls, SlumpconeError)

    def test_unit_error_is_a_validation_error(self) -> None:
        assert issubclass(UnitError, ValidationError)


class CaseValidationError:
    def test_message_alone_prints_bare(self) -> None:
        assert str(ValidationError("slump is negative")) == "slump is negative"

    def test_field_is_prefixed(self) -> None:
        err = ValidationError("slump is negative", field="slump_in")
        assert str(err) == "slump_in: slump is negative"
        assert err.field == "slump_in"

    def test_field_defaults_to_none(self) -> None:
        assert ValidationError("bad").field is None

    def test_raises_and_catches_as_base(self) -> None:
        with pytest.raises(SlumpconeError):
            raise ValidationError("bad")


class CaseNotFoundError:
    def test_carries_kind_and_identity(self) -> None:
        err = NotFoundError("mix design", "4000P-57")
        assert err.kind == "mix design"
        assert err.identity == "4000P-57"
        assert "4000P-57" in str(err)


class CaseConflictError:
    def test_reads_as_already_on_file(self) -> None:
        err = ConflictError("ticket", "881204")
        assert str(err) == "ticket '881204' is already on file"
        assert err.kind == "ticket"
        assert err.identity == "881204"


class CaseRuleViolation:
    def test_code_leads_the_message(self) -> None:
        err = RuleViolationError("DISCHARGE_LATE", "97 minutes from batch to discharge")
        assert err.code == "DISCHARGE_LATE"
        assert err.detail == "97 minutes from batch to discharge"
        assert str(err).startswith("DISCHARGE_LATE: ")
