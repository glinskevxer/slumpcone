from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.identity import (
    is_code,
    normalize_code,
    normalize_name,
    normalize_ticket_number,
)


class CaseNormalizeCode:
    @pytest.mark.parametrize(
        ("written", "stored"),
        [
            ("4000P-57", "4000P-57"),
            ("4000p 57", "4000P-57"),
            ("  4000P-57  ", "4000P-57"),
            ("4000p_57", "4000P-57"),
            ("4000P--57", "4000P-57"),
            ("-4000P-57-", "4000P-57"),
            ("mix 1", "MIX-1"),
        ],
    )
    def test_folding(self, written: str, stored: str) -> None:
        assert normalize_code(written) == stored

    def test_blank_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            normalize_code("   ")

    def test_hyphens_only_is_blank(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            normalize_code("---")

    def test_too_long_names_the_limit(self) -> None:
        with pytest.raises(ValidationError, match="limit is 8"):
            normalize_code("ABCDEFGHI", max_length=8)

    @pytest.mark.parametrize("bad", ["4000P/57", "4000P.57", "MIX,1", "MIX#1"])
    def test_punctuation_is_refused(self, bad: str) -> None:
        with pytest.raises(ValidationError, match="not a letter"):
            normalize_code(bad)

    def test_the_field_name_travels_with_the_error(self) -> None:
        with pytest.raises(ValidationError) as caught:
            normalize_code("", field="plant_code")
        assert caught.value.field == "plant_code"

    def test_non_text_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to be text"):
            normalize_code(4000)  # type: ignore[arg-type]


class CaseTicketNumber:
    def test_digits_pass_through(self) -> None:
        assert normalize_ticket_number(" 881204 ") == "881204"

    def test_leading_zeros_are_kept(self) -> None:
        assert normalize_ticket_number("0004312") == "0004312"

    def test_blank_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="required"):
            normalize_ticket_number("  ")

    def test_letters_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="not all digits"):
            normalize_ticket_number("T881204")

    def test_too_long_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="twelve"):
            normalize_ticket_number("1" * 13)


class CaseName:
    def test_whitespace_collapses(self) -> None:
        assert normalize_name("  Northmoor   Ready  Mix ") == "Northmoor Ready Mix"

    def test_blank_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            normalize_name("\t\n")

    def test_too_long_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="limit is 10"):
            normalize_name("a" * 11, max_length=10)

    def test_non_text_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            normalize_name(None)  # type: ignore[arg-type]


class CaseIsCode:
    def test_already_normalised(self) -> None:
        assert is_code("4000P-57")

    def test_not_normalised(self) -> None:
        assert not is_code("4000p 57")

    def test_invalid(self) -> None:
        assert not is_code("")
