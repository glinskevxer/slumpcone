from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.mixdesign.volumes import compute_volumes
from slumpcone.percent import Percent
from slumpcone.report.yield_report import (
    YieldRow,
    render_yield,
    render_yield_report,
    yield_rows,
    yield_summary,
)
from slumpcone.units.rate import MassPerVolume
from tests.factories import gravities, proportions

TAKEN = datetime(2024, 6, 12, 8, 5)
MIX = proportions(admixtures=())
GRAVITIES = gravities()
ON_DESIGN = compute_volumes(MIX, GRAVITIES).design_density


def unit_weight(ticket: str, density: MassPerVolume) -> FreshTest:
    return FreshTest(ticket, FreshTestKind.UNIT_WEIGHT, TAKEN, unit_weight=density)


def air(ticket: str, value: float) -> FreshTest:
    return FreshTest(ticket, FreshTestKind.AIR_PRESSURE, TAKEN, air=Percent(value))


class CaseRows:
    def test_a_load_on_design_yields_one(self) -> None:
        rows = yield_rows([unit_weight("881204", ON_DESIGN)], MIX, GRAVITIES)
        assert rows[0].relative_yield == pytest.approx(1.0, abs=1e-6)
        assert rows[0].note == "ok"

    def test_a_heavy_load_yields_short(self) -> None:
        rows = yield_rows([unit_weight("881204", ON_DESIGN * 1.03)], MIX, GRAVITIES)
        assert rows[0].is_short
        assert "short" in rows[0].note

    def test_a_light_load_yields_over(self) -> None:
        rows = yield_rows([unit_weight("881204", ON_DESIGN * 0.97)], MIX, GRAVITIES)
        assert rows[0].is_over
        assert "over" in rows[0].note

    def test_only_unit_weight_tests_produce_rows(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN), air("881204", 6.0)]
        assert len(yield_rows(tests, MIX, GRAVITIES)) == 1

    def test_the_air_reading_is_matched_by_ticket(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN), air("881204", 6.0)]
        rows = yield_rows(tests, MIX, GRAVITIES)
        assert rows[0].measured_air == Percent(6.0)

    def test_an_air_reading_on_another_ticket_is_not_borrowed(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN), air("881205", 6.0)]
        assert yield_rows(tests, MIX, GRAVITIES)[0].measured_air is None

    def test_rows_come_back_in_ticket_order(self) -> None:
        tests = [unit_weight("881205", ON_DESIGN), unit_weight("881204", ON_DESIGN)]
        rows = yield_rows(tests, MIX, GRAVITIES)
        assert [row.ticket_number for row in rows] == ["881204", "881205"]

    def test_a_zero_unit_weight_never_reaches_the_report(self) -> None:
        with pytest.raises(ValidationError, match="unit weight has to be positive"):
            unit_weight("881204", MassPerVolume(0, "lb", "ft3"))


class CaseAirMethods:
    def test_agreement(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN), air("881204", 6.0)]
        row = yield_rows(tests, MIX, GRAVITIES)[0]
        assert row.air_difference is not None
        assert not row.air_methods_disagree

    def test_disagreement(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN), air("881204", 2.0)]
        row = yield_rows(tests, MIX, GRAVITIES)[0]
        assert row.air_methods_disagree
        assert "air methods disagree" in row.note

    def test_no_meter_reading_means_no_comparison(self) -> None:
        row = yield_rows([unit_weight("881204", ON_DESIGN)], MIX, GRAVITIES)[0]
        assert row.air_difference is None
        assert not row.air_methods_disagree

    def test_several_notes_at_once(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN * 1.05), air("881204", 6.0)]
        row = yield_rows(tests, MIX, GRAVITIES)[0]
        assert "short" in row.note
        assert "air methods disagree" in row.note


class CaseRendering:
    def rows(self) -> tuple[YieldRow, ...]:
        tests = [
            unit_weight("881204", ON_DESIGN),
            air("881204", 6.0),
            unit_weight("881205", ON_DESIGN * 1.03),
        ]
        return yield_rows(tests, MIX, GRAVITIES)

    def test_the_table(self) -> None:
        text = render_yield(self.rows())
        assert "ticket" in text.splitlines()[0]
        assert "881204" in text
        assert "rel yield" in text.splitlines()[0]

    def test_a_missing_meter_reading_prints_a_dash(self) -> None:
        assert "-" in render_yield(self.rows())

    def test_the_summary(self) -> None:
        text = yield_summary(self.rows())
        assert "loads                 : 2" in text
        assert "short                 : 1" in text

    def test_an_empty_summary(self) -> None:
        assert yield_summary(()) == "loads: 0"

    def test_the_whole_report(self) -> None:
        tests = [unit_weight("881204", ON_DESIGN)]
        text = render_yield_report("4000P-57", tests, MIX, GRAVITIES)
        assert "Yield for 4000P-57" in text
        assert "average relative yield" in text
