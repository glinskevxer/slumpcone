from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.report.production import (
    by_day,
    by_mix,
    by_plant,
    by_project,
    render_group,
    render_production_report,
    render_totals,
    totals,
)
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

DAY = date(2024, 6, 12)


def ticket(
    number: str, volume: float = 9.0, day: int = 0, project: str = "Route 9 shoulder"
) -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(volume, "yd3"), DAY)
    return BatchTicket.from_plan(
        planned,
        number,
        datetime(2024, 6, 12, 7, 42) + timedelta(days=day),
        truck_code="TR-114",
        purchaser="Ashfield Paving",
        project=project,
    )


def delivery(number: str, returned: float | None) -> Delivery:
    return Delivery(
        number,
        "TR-114",
        datetime(2024, 6, 12, 7, 42),
        returned_volume=None if returned is None else Quantity(returned, "yd3"),
    )


def run() -> list[BatchTicket]:
    return [
        ticket("881204", 9.0),
        ticket("881205", 7.0),
        ticket("881206", 10.0, day=1, project="Mill Street kerb"),
    ]


class CaseTotals:
    def test_loads_and_volume(self) -> None:
        figures = totals(run())
        assert figures.loads == 3
        assert figures.volume == Quantity(26, "yd3")

    def test_average_load(self) -> None:
        assert totals(run()).average_load.value == pytest.approx(8.667, abs=1e-3)

    def test_an_empty_window(self) -> None:
        figures = totals([])
        assert figures.loads == 0
        assert figures.average_load.is_zero()
        assert figures.per_day.is_zero()
        assert figures.returned_share.value == pytest.approx(0.0)

    def test_the_days_come_from_the_tickets_when_no_window_is_given(self) -> None:
        assert totals(run()).days == 2

    def test_an_explicit_window_wins(self) -> None:
        figures = totals(run(), start=date(2024, 6, 1), end=date(2024, 6, 30))
        assert figures.days == 30
        assert figures.per_day.value == pytest.approx(26.0 / 30.0, abs=1e-3)

    def test_returned_concrete(self) -> None:
        figures = totals(run(), [delivery("881204", 0.5), delivery("881205", None)])
        assert figures.returned == Quantity(0.5, "yd3")
        assert figures.placed == Quantity(25.5, "yd3")
        assert figures.returned_share.value == pytest.approx(1.923, abs=1e-3)

    def test_a_share_rather_than_a_count(self) -> None:
        one_big = totals(run(), [delivery("881204", 6.0)])
        many_small = totals(
            run(),
            [delivery("881204", 0.5), delivery("881205", 0.5), delivery("881206", 0.5)],
        )
        assert one_big.returned_share > many_small.returned_share


class CaseGroups:
    def test_by_mix(self) -> None:
        grouped = by_mix(run())
        assert grouped["4000P-57"][0] == 3
        assert grouped["4000P-57"][1] == Quantity(26, "yd3")

    def test_by_plant(self) -> None:
        assert by_plant(run())["PL-1"][0] == 3

    def test_by_project(self) -> None:
        grouped = by_project(run())
        assert set(grouped) == {"Route 9 shoulder", "Mill Street kerb"}
        assert grouped["Mill Street kerb"][1] == Quantity(10, "yd3")

    def test_by_day(self) -> None:
        grouped = by_day(run())
        assert list(grouped) == ["2024-06-12", "2024-06-13"]
        assert grouped["2024-06-12"][0] == 2

    def test_a_missing_field_groups_under_a_dash(self) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        bare = BatchTicket.from_plan(planned, "881207", datetime(2024, 6, 12, 7, 42))
        assert "-" in by_project([bare])

    def test_groups_are_sorted(self) -> None:
        assert list(by_project(run())) == ["Mill Street kerb", "Route 9 shoulder"]


class CaseRendering:
    def test_a_group_table(self) -> None:
        text = render_group(by_mix(run()), "mix")
        assert text.splitlines()[0].startswith("mix")
        assert "4000P-57" in text
        assert "loads" in text.splitlines()[0]

    def test_an_empty_group_still_prints_a_heading(self) -> None:
        assert "loads" in render_group({}, "mix").splitlines()[0]

    def test_the_totals_block(self) -> None:
        text = render_totals(totals(run()))
        assert "loads" in text
        assert "average load" in text
        assert "returned share" in text

    def test_the_whole_report(self) -> None:
        text = render_production_report(
            run(), [delivery("881204", 0.5)], start=date(2024, 6, 1), end=date(2024, 6, 30)
        )
        assert "Production, 2024-06-01 to 2024-06-30" in text
        assert "By mix" in text
        assert "By job" in text
        assert "By day" in text

    def test_a_report_with_no_window(self) -> None:
        assert "all tickets on file" in render_production_report(run())
