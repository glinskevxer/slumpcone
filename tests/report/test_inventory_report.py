from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.plant.inventory import InventoryLedger, Movement, MovementKind
from slumpcone.plant.silo import Silo, SiloState
from slumpcone.report.inventory_report import (
    adjustment_summary,
    counts_by_state,
    drawdown_count,
    fill_across,
    render_inventory_report,
    render_silos,
    render_usage,
    reorder_list,
    silo_status,
    total_held,
    usage_by_material,
)
from slumpcone.units.quantity import Quantity

START = date(2024, 6, 1)
END = date(2024, 6, 10)


def silo(code: str = "SI-1", material: str = "CEM-I", level: float = 120000.0) -> Silo:
    return Silo(
        code,
        f"Vessel {code}",
        material,
        Quantity(200000, "lb"),
        Quantity(level, "lb"),
        Quantity(30000, "lb"),
    )


def movement(
    kind: MovementKind, pounds: float, day: int, code: str = "SI-1", material: str = "CEM-I"
) -> Movement:
    return Movement(
        "PL-1",
        code,
        material,
        datetime(2024, 6, 1) + timedelta(days=day),
        kind,
        Quantity(pounds, "lb"),
    )


def ledger() -> InventoryLedger:
    return InventoryLedger(
        [
            movement(MovementKind.RECEIPT, 48000.0, 0),
            movement(MovementKind.DRAWDOWN, 40000.0, 2),
            movement(MovementKind.DRAWDOWN, 60000.0, 6),
            movement(MovementKind.DRAWDOWN, 5000.0, 3, "SI-2", "SCM-F"),
        ]
    )


class CaseStatus:
    def test_usage_and_cover(self) -> None:
        statuses = silo_status([silo()], ledger(), START, END)
        assert statuses[0].daily_usage is not None
        assert statuses[0].daily_usage.value == pytest.approx(10000.0)
        assert statuses[0].days_of_cover == pytest.approx(12.0)

    def test_a_silo_with_no_usage_has_no_cover(self) -> None:
        statuses = silo_status([silo("SI-3", "FA-1")], ledger(), START, END)
        assert statuses[0].days_of_cover is None
        assert statuses[0].cover_text == "-"

    def test_statuses_come_back_in_code_order(self) -> None:
        statuses = silo_status([silo("SI-2"), silo("SI-1")], ledger(), START, END)
        assert [status.silo.code for status in statuses] == ["SI-1", "SI-2"]

    def test_a_short_window_raises_the_daily_rate(self) -> None:
        short = silo_status([silo()], ledger(), date(2024, 6, 1), date(2024, 6, 3))
        long = silo_status([silo()], ledger(), START, END)
        assert short[0].daily_usage is not None
        assert long[0].daily_usage is not None
        assert short[0].daily_usage > long[0].daily_usage


class CaseReorder:
    def test_a_comfortable_silo_is_not_listed(self) -> None:
        statuses = silo_status([silo()], ledger(), START, END)
        assert reorder_list(statuses) == ()

    def test_a_low_silo_is_listed(self) -> None:
        statuses = silo_status([silo(level=20000.0)], ledger(), START, END)
        assert len(reorder_list(statuses)) == 1

    def test_a_silo_with_too_little_cover_is_listed(self) -> None:
        statuses = silo_status([silo(level=40000.0)], ledger(), START, END)
        assert statuses[0].days_of_cover == pytest.approx(4.0)
        assert reorder_list(statuses) == ()
        tighter = silo_status([silo(level=25000.0)], ledger(), START, END)
        assert len(reorder_list(tighter)) == 1

    def test_tightest_cover_first(self) -> None:
        statuses = silo_status(
            [silo("SI-1", level=10000.0), silo("SI-2", "SCM-F", level=1000.0)],
            ledger(),
            START,
            END,
        )
        assert [status.silo.code for status in reorder_list(statuses)] == ["SI-1", "SI-2"]


class CaseUsage:
    def test_by_material(self) -> None:
        totals = usage_by_material(ledger(), START, END)
        assert totals["CEM-I"] == Quantity(100000, "lb")
        assert totals["SCM-F"] == Quantity(5000, "lb")

    def test_receipts_are_not_usage(self) -> None:
        totals = usage_by_material(ledger(), START, END)
        assert totals["CEM-I"].value == pytest.approx(100000.0)

    def test_a_window_outside_everything(self) -> None:
        assert usage_by_material(ledger(), date(2024, 7, 1), date(2024, 7, 31)) == {}

    def test_render(self) -> None:
        text = render_usage(usage_by_material(ledger(), START, END))
        assert "material" in text.splitlines()[0]
        assert "CEM-I" in text


class CaseAdjustments:
    def test_a_ledger_with_no_corrections(self) -> None:
        text = adjustment_summary(ledger())
        assert len(text.splitlines()) == 2

    def test_a_correction_is_summarised(self) -> None:
        book = ledger()
        book.reconcile("SI-1", Quantity(40000, "lb"), datetime(2024, 6, 8))
        text = adjustment_summary(book)
        assert "SI-1" in text
        assert "1" in text


class CaseRendering:
    def test_the_silo_table(self) -> None:
        text = render_silos(silo_status([silo()], ledger(), START, END))
        assert "silo" in text.splitlines()[0]
        assert "cover" in text.splitlines()[0]
        assert "SI-1" in text

    def test_the_whole_report(self) -> None:
        text = render_inventory_report("PL-1", [silo()], ledger(), START, END)
        assert "Inventory at PL-1" in text
        assert "2024-06-01 to 2024-06-10" in text
        assert "Usage" in text
        assert "Reorder" not in text

    def test_a_report_with_a_reorder_section(self) -> None:
        text = render_inventory_report("PL-1", [silo(level=20000.0)], ledger(), START, END)
        assert "Reorder" in text


class CaseTotals:
    def test_counts_by_state_includes_the_empty_ones(self) -> None:
        tally = counts_by_state(silo_status([silo()], ledger(), START, END))
        assert tally[SiloState.WORKING] == 1
        assert tally[SiloState.EMPTY] == 0

    def test_total_held(self) -> None:
        assert total_held([silo(), silo("SI-2", "SCM-F", 40000.0)]) == Quantity(160000, "lb")

    def test_fill_across_the_yard(self) -> None:
        assert fill_across([silo(), silo("SI-2", "SCM-F", 40000.0)]).value == pytest.approx(
            40.0
        )

    def test_fill_across_nothing(self) -> None:
        assert fill_across([]).value == pytest.approx(0.0)

    def test_drawdown_count(self) -> None:
        assert drawdown_count(ledger(), "SI-1") == 2
        assert drawdown_count(ledger(), "SI-9") == 0
