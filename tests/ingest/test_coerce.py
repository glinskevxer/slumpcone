from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.errors import ValidationError
from slumpcone.ingest.coerce import (
    coerce,
    is_blank,
    to_boolean,
    to_date,
    to_datetime,
    to_number,
)
from slumpcone.ingest.mapping import FieldKind, FieldSpec
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


def spec(kind: FieldKind = FieldKind.TEXT, unit: str | None = None) -> FieldSpec:
    return FieldSpec("value", ("value",), kind=kind, unit=unit)


class CaseBlank:
    @pytest.mark.parametrize("raw", ["", "  ", "-", "--", "N/A", "null", "NONE", "#N/A"])
    def test_the_words_that_mean_nothing(self, raw: str) -> None:
        assert is_blank(raw)

    def test_a_real_value_is_not_blank(self) -> None:
        assert not is_blank("0")
        assert not is_blank("881204")


class CaseNumber:
    @pytest.mark.parametrize(
        ("raw", "value"),
        [
            ("4230", 4230.0),
            (" 4,230 ", 4230.0),
            ("4_230", 4230.0),
            ("4 230", 4230.0),
            ("4230.5", 4230.5),
            ("-12.5", -12.5),
            ("(120)", -120.0),
            ("4230 lb", 4230.0),
            ("4230lb", 4230.0),
            ("6.0%", 6.0),
            ("1.2e3", 1200.0),
            ("142.6 lb/ft3", 142.6),
        ],
    )
    def test_reading(self, raw: str, value: float) -> None:
        assert to_number(raw) == pytest.approx(value)

    @pytest.mark.parametrize("raw", ["", "abc", "1.2.3", "lb 4230"])
    def test_unreadable(self, raw: str) -> None:
        with pytest.raises(ValidationError, match="as a number"):
            to_number(raw)

    def test_the_field_name_travels(self) -> None:
        with pytest.raises(ValidationError) as caught:
            to_number("abc", field="batch_weight")
        assert caught.value.field == "batch_weight"


class CaseDate:
    @pytest.mark.parametrize(
        ("raw", "value"),
        [
            ("2024-06-12", date(2024, 6, 12)),
            ("2024/06/12", date(2024, 6, 12)),
            ("20240612", date(2024, 6, 12)),
            ("12-Jun-2024", date(2024, 6, 12)),
            ("12 Jun 2024", date(2024, 6, 12)),
        ],
    )
    def test_unambiguous_layouts(self, raw: str, value: date) -> None:
        assert to_date(raw) == value

    def test_an_ambiguous_layout_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="day first or month first"):
            to_date("03/04/2024")

    def test_an_explicit_layout_reads_it(self) -> None:
        assert to_date("03/04/2024", layout="%m/%d/%Y") == date(2024, 3, 4)
        assert to_date("03/04/2024", layout="%d/%m/%Y") == date(2024, 4, 3)

    def test_a_wrong_explicit_layout_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="in %Y-%m-%d"):
            to_date("03/04/2024", layout="%Y-%m-%d")

    def test_nonsense_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="as a date"):
            to_date("yesterday")


class CaseDatetime:
    @pytest.mark.parametrize(
        "raw",
        [
            "2024-06-12 07:42:00",
            "2024-06-12 07:42",
            "2024-06-12T07:42:00",
            "2024/06/12 07:42",
        ],
    )
    def test_layouts(self, raw: str) -> None:
        assert to_datetime(raw) == datetime(2024, 6, 12, 7, 42)

    def test_a_bare_date_becomes_midnight(self) -> None:
        assert to_datetime("2024-06-12") == datetime(2024, 6, 12, 0, 0)

    def test_an_explicit_layout(self) -> None:
        assert to_datetime("06/12/2024 07:42", layout="%m/%d/%Y %H:%M") == datetime(
            2024, 6, 12, 7, 42
        )

    def test_a_wrong_explicit_layout_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="as a timestamp"):
            to_datetime("nonsense", layout="%m/%d/%Y %H:%M")

    def test_nonsense_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="as a date"):
            to_datetime("nonsense")


class CaseBoolean:
    @pytest.mark.parametrize("raw", ["1", "Y", "yes", "TRUE", "on", " t "])
    def test_true_words(self, raw: str) -> None:
        assert to_boolean(raw)

    @pytest.mark.parametrize("raw", ["0", "N", "no", "FALSE", "off", " f "])
    def test_false_words(self, raw: str) -> None:
        assert not to_boolean(raw)

    def test_anything_else_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="as a yes or no"):
            to_boolean("maybe")


class CaseCoerce:
    def test_a_blank_is_none_whatever_the_kind(self) -> None:
        for kind in FieldKind:
            unit = "lb" if kind is FieldKind.QUANTITY else None
            assert coerce(spec(kind, unit), "  ") is None

    def test_text_is_stripped(self) -> None:
        assert coerce(spec(), "  881204 ") == "881204"

    def test_a_number(self) -> None:
        assert coerce(spec(FieldKind.NUMBER), "4,230") == pytest.approx(4230.0)

    def test_a_percent(self) -> None:
        assert coerce(spec(FieldKind.PERCENT), "6.0%") == Percent(6.0)

    def test_a_quantity_takes_its_unit_from_the_spec(self) -> None:
        assert coerce(spec(FieldKind.QUANTITY, "lb"), "4230") == Quantity(4230, "lb")

    def test_a_quantity_with_the_unit_written_in_the_cell(self) -> None:
        assert coerce(spec(FieldKind.QUANTITY, "lb"), "4230 lb") == Quantity(4230, "lb")

    def test_a_date(self) -> None:
        assert coerce(spec(FieldKind.DATE), "2024-06-12") == date(2024, 6, 12)

    def test_a_date_with_a_profile_layout(self) -> None:
        assert coerce(spec(FieldKind.DATE), "06/12/2024", date_format="%m/%d/%Y") == date(
            2024, 6, 12
        )

    def test_a_datetime(self) -> None:
        assert coerce(spec(FieldKind.DATETIME), "2024-06-12 07:42") == datetime(
            2024, 6, 12, 7, 42
        )

    def test_a_boolean(self) -> None:
        assert coerce(spec(FieldKind.BOOLEAN), "yes") is True

    def test_the_field_name_is_on_the_error(self) -> None:
        with pytest.raises(ValidationError) as caught:
            coerce(FieldSpec("batch_weight", ("w",), kind=FieldKind.NUMBER), "abc")
        assert caught.value.field == "batch_weight"
