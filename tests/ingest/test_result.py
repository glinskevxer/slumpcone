from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.ingest.result import (
    AcceptedRow,
    IngestResult,
    Quarantined,
    RowOutcome,
    content_hash,
    digests,
)
from slumpcone.percent import Percent
from slumpcone.units.quantity import Quantity


def accepted(line: int = 2, ticket: str = "881204") -> AcceptedRow:
    values = {"ticket_number": ticket, "volume": Quantity(9, "yd3")}
    return AcceptedRow(line, values, content_hash(values))


class CaseContentHash:
    def test_the_same_values_hash_the_same(self) -> None:
        assert content_hash({"a": "1"}) == content_hash({"a": "1"})

    def test_key_order_does_not_matter(self) -> None:
        assert content_hash({"a": "1", "b": "2"}) == content_hash({"b": "2", "a": "1"})

    def test_a_different_value_hashes_differently(self) -> None:
        assert content_hash({"a": "1"}) != content_hash({"a": "2"})

    def test_a_quantity_hashes_on_its_base_value(self) -> None:
        assert content_hash({"w": Quantity(1, "yd3")}) == content_hash(
            {"w": Quantity(27, "ft3")}
        )

    def test_a_different_quantity_still_differs(self) -> None:
        assert content_hash({"w": Quantity(1, "yd3")}) != content_hash(
            {"w": Quantity(2, "yd3")}
        )

    def test_a_percent(self) -> None:
        assert content_hash({"air": Percent(6.0)}) == content_hash({"air": Percent(6.0)})
        assert content_hash({"air": Percent(6.0)}) != content_hash({"air": Percent(6.5)})

    def test_dates_and_timestamps(self) -> None:
        assert content_hash({"d": date(2024, 6, 12)}) != content_hash(
            {"d": datetime(2024, 6, 12)}
        )

    def test_float_noise_does_not_change_it(self) -> None:
        assert content_hash({"v": 1.0}) == content_hash({"v": 1.0000000000001})

    def test_none_is_carried(self) -> None:
        assert content_hash({"v": None}) != content_hash({"v": ""})


class CaseQuarantined:
    def test_describe(self) -> None:
        row = Quarantined(7, ("no ticket number", "unreadable volume"))
        assert row.describe() == "line 7: no ticket number; unreadable volume"


class CaseAcceptedRow:
    def test_get(self) -> None:
        row = accepted()
        assert row.get("ticket_number") == "881204"
        assert row.get("nothing", "-") == "-"

    def test_digests(self) -> None:
        assert len(digests([accepted(2, "881204"), accepted(3, "881205")])) == 2
        assert len(digests([accepted(2), accepted(3)])) == 1


class CaseResult:
    def result(self, **overrides: object) -> IngestResult:
        fields: dict[str, object] = {
            "profile_code": "MARCOTTE-V4",
            "source_name": "batches-2024-06-12.csv",
            "accepted": (accepted(2), accepted(3, "881205")),
            "quarantined": (Quarantined(4, ("no ticket number",)),),
            "duplicates": (5,),
            "unmapped_columns": ("operator",),
            "run_at": datetime(2024, 6, 13, 8, 0),
        }
        fields.update(overrides)
        return IngestResult(**fields)  # type: ignore[arg-type]

    def test_counts(self) -> None:
        result = self.result()
        assert result.row_count == 4
        assert result.accepted_count == 2

    def test_clean_and_dirty(self) -> None:
        assert not self.result().is_clean
        assert self.result(quarantined=()).is_clean

    def test_a_re_run_is_all_duplicate(self) -> None:
        rerun = self.result(accepted=(), quarantined=(), duplicates=(2, 3, 4))
        assert rerun.is_all_duplicate

    def test_a_mixed_run_is_not(self) -> None:
        assert not self.result().is_all_duplicate

    def test_an_empty_run_is_not_all_duplicate(self) -> None:
        assert not self.result(accepted=(), quarantined=(), duplicates=()).is_all_duplicate

    def test_outcome_by_line(self) -> None:
        result = self.result()
        assert result.outcome_of(2) is RowOutcome.ACCEPTED
        assert result.outcome_of(4) is RowOutcome.QUARANTINED
        assert result.outcome_of(5) is RowOutcome.DUPLICATE
        assert result.outcome_of(99) is None

    def test_reasons(self) -> None:
        assert self.result().reasons() == ("no ticket number",)

    def test_describe(self) -> None:
        text = self.result().describe()
        assert "batches-2024-06-12.csv through MARCOTTE-V4" in text
        assert "2 accepted, 1 quarantined, 1 already on file" in text
        assert "columns not mapped: operator" in text
        assert "line 4: no ticket number" in text

    def test_describe_without_unmapped_columns(self) -> None:
        assert "not mapped" not in self.result(unmapped_columns=()).describe()

    def test_outcome_prints_its_own_value(self) -> None:
        assert str(RowOutcome.DUPLICATE) == "duplicate"


@pytest.mark.parametrize("line", [2, 3])
def test_every_accepted_line_reports_accepted(line: int) -> None:
    result = IngestResult("P", "f.csv", (accepted(2), accepted(3, "881205")))
    assert result.outcome_of(line) is RowOutcome.ACCEPTED
