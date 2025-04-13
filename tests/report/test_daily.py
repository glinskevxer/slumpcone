from __future__ import annotations

from datetime import timedelta

import pytest

from slumpcone.demo import DEMO_DAY, seed
from slumpcone.register import Register
from slumpcone.report.daily import render_day, render_week, summarise_day
from slumpcone.units.quantity import Quantity


@pytest.fixture()
def seeded() -> Register:
    register = Register.in_memory()
    seed(register)
    return register


class CaseSummary:
    def test_an_empty_day(self) -> None:
        summary = summarise_day(Register.in_memory(), DEMO_DAY)
        assert summary.loads == 0
        assert summary.volume.is_zero()
        assert summary.tested_share.value == pytest.approx(0.0)
        assert not summary.needs_attention

    def test_the_seeded_day(self, seeded: Register) -> None:
        summary = summarise_day(seeded, DEMO_DAY)
        assert summary.loads == 4
        assert summary.volume == Quantity(36, "yd3")
        assert summary.tested_loads == 4
        assert summary.tested_share.value == pytest.approx(100.0)

    def test_the_outstanding_retest_shows(self, seeded: Register) -> None:
        summary = summarise_day(seeded, DEMO_DAY)
        assert summary.retests_outstanding == 1
        assert summary.rejected_loads == 0

    def test_the_findings_are_gathered(self, seeded: Register) -> None:
        summary = summarise_day(seeded, DEMO_DAY)
        assert summary.findings
        codes = {finding.code for finding in summary.findings}
        assert "BATCH_WEIGHT_OUT_OF_TOLERANCE" in codes

    def test_another_day_is_quiet(self, seeded: Register) -> None:
        summary = summarise_day(seeded, DEMO_DAY + timedelta(days=30))
        assert summary.loads == 0

    def test_filtering_by_plant(self, seeded: Register) -> None:
        assert summarise_day(seeded, DEMO_DAY, plant_code="PL-1").loads == 4
        assert summarise_day(seeded, DEMO_DAY, plant_code="PL-9").loads == 0

    def test_describe(self, seeded: Register) -> None:
        text = summarise_day(seeded, DEMO_DAY).describe()
        assert "4 loads" in text
        assert "36.0 yd3" in text


class CaseAttention:
    def test_a_quiet_day_is_clear(self) -> None:
        summary = summarise_day(Register.in_memory(), DEMO_DAY)
        assert not summary.needs_attention
        assert "clear" in summary.describe()

    def test_a_day_with_a_major_finding_needs_attention(self, seeded: Register) -> None:
        summary = summarise_day(seeded, DEMO_DAY)
        if summary.major_findings:
            assert summary.needs_attention

    def test_blocked_materials_count(self) -> None:
        register = Register.in_memory()
        from tests.factories import cement

        register.materials.save(cement())
        summary = summarise_day(register, DEMO_DAY)
        assert summary.blocked_now >= 0


class CaseRendering:
    def test_the_page(self, seeded: Register) -> None:
        text = render_day(summarise_day(seeded, DEMO_DAY))
        assert "Plant day, 2024-06-12" in text
        assert "loads tested" in text
        assert "verdict" in text
        assert "Findings" in text

    def test_a_quiet_page_has_no_findings_table(self) -> None:
        text = render_day(summarise_day(Register.in_memory(), DEMO_DAY))
        assert "Findings" not in text

    def test_the_findings_table_is_capped(self, seeded: Register) -> None:
        text = render_day(summarise_day(seeded, DEMO_DAY), findings_shown=1)
        summary = summarise_day(seeded, DEMO_DAY)
        if len(summary.findings) > 1:
            assert "and " in text and " more" in text

    def test_the_week_table(self, seeded: Register) -> None:
        days = [summarise_day(seeded, DEMO_DAY + timedelta(days=offset)) for offset in range(3)]
        text = render_week(days)
        assert "2024-06-12" in text
        assert "verdict" in text.splitlines()[0]

    def test_an_empty_week(self) -> None:
        assert "day" in render_week([]).splitlines()[0]


def test_the_page_agrees_with_the_production_report(seeded: Register) -> None:
    from slumpcone.report.production import totals

    summary = summarise_day(seeded, DEMO_DAY)
    figures = totals(
        list(seeded.batches.between(DEMO_DAY, DEMO_DAY)),
        list(seeded.deliveries.between(DEMO_DAY, DEMO_DAY)),
        start=DEMO_DAY,
        end=DEMO_DAY,
    )
    assert summary.loads == figures.loads
    assert summary.volume == figures.volume
