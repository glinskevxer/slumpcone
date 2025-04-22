from __future__ import annotations

from datetime import date

import pytest

from slumpcone.carbon.benchmark import (
    DEFAULT_CLASSES,
    Assessment,
    BenchmarkClass,
    BenchmarkTable,
    assess,
)
from slumpcone.carbon.factors import CarbonError, EmissionFactor, FactorBook, Provenance
from slumpcone.carbon.footprint import footprint_of
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.quantity import Quantity
from tests import factories

TODAY = date(2024, 6, 12)


def book(
    *, provenance: Provenance = Provenance.INDUSTRY_AVERAGE, published: date | None = None
) -> FactorBook:
    source = "EPD 4471" if provenance is Provenance.PRODUCT_EPD else ""
    pairs = [
        ("CEM-I", MaterialClass.CEMENT, 0.922),
        ("SCM-F", MaterialClass.SCM, 0.027),
        ("CA-57", MaterialClass.COARSE_AGGREGATE, 0.0075),
        ("FA-1", MaterialClass.FINE_AGGREGATE, 0.0048),
        ("W-1", MaterialClass.WATER, 0.0003),
    ]
    return FactorBook(
        EmissionFactor(
            code,
            kind,
            value,
            provenance=provenance,
            source=source,
            published_on=published,
        )
        for code, kind, value in pairs
    )


class CaseClasses:
    def test_a_row_holds_its_floor_and_limit(self) -> None:
        row = BenchmarkClass(Quantity(4000, "psi"), 307.0)
        assert row.limit_kg_per_m3 == pytest.approx(307.0)

    def test_a_row_covers_its_floor(self) -> None:
        assert BenchmarkClass(Quantity(4000, "psi"), 307.0).covers(Quantity(4000, "psi"))

    def test_a_row_does_not_cover_below_it(self) -> None:
        assert not BenchmarkClass(Quantity(4000, "psi"), 307.0).covers(Quantity(3999, "psi"))

    def test_a_zero_floor(self) -> None:
        with pytest.raises(CarbonError) as caught:
            BenchmarkClass(Quantity(0, "psi"), 307.0)
        assert caught.value.code == "BENCHMARK_FLOOR_NOT_POSITIVE"

    def test_a_zero_limit(self) -> None:
        with pytest.raises(CarbonError) as caught:
            BenchmarkClass(Quantity(4000, "psi"), 0.0)
        assert caught.value.code == "BENCHMARK_LIMIT_NOT_POSITIVE"

    def test_a_row_describes_with_its_label(self) -> None:
        row = BenchmarkClass(Quantity(4000, "psi"), 307.0, "4000 to 4999 psi")
        assert "4000 to 4999 psi" in row.describe()

    def test_a_row_without_a_label_makes_one(self) -> None:
        assert "and up" in BenchmarkClass(Quantity(4000, "psi"), 307.0).describe()


class CaseTable:
    def test_the_shipped_table(self) -> None:
        table = BenchmarkTable.defaults()
        assert len(table.classes) == len(DEFAULT_CLASSES)
        assert table.name

    def test_it_is_ordered_strongest_first(self) -> None:
        floors = [row.floor.to("psi").value for row in BenchmarkTable.defaults().classes]
        assert floors == sorted(floors, reverse=True)

    def test_an_empty_table(self) -> None:
        with pytest.raises(CarbonError) as caught:
            BenchmarkTable([])
        assert caught.value.code == "BENCHMARK_EMPTY_TABLE"

    def test_a_strength_lands_on_its_own_class(self) -> None:
        row = BenchmarkTable.defaults().limit_for(Quantity(4000, "psi"))
        assert row.limit_kg_per_m3 == pytest.approx(307.0)

    def test_the_table_steps_rather_than_interpolating(self) -> None:
        table = BenchmarkTable.defaults()
        # 4200 gets the 4000 limit, not two tenths of the way to the 5000 one.
        assert table.limit_for(Quantity(4200, "psi")).limit_kg_per_m3 == pytest.approx(307.0)
        assert table.limit_for(Quantity(4999, "psi")).limit_kg_per_m3 == pytest.approx(307.0)

    def test_the_next_class_up_is_a_step(self) -> None:
        table = BenchmarkTable.defaults()
        assert table.limit_for(Quantity(5000, "psi")).limit_kg_per_m3 == pytest.approx(342.0)

    def test_a_very_strong_mix_gets_the_top_class(self) -> None:
        table = BenchmarkTable.defaults()
        assert table.limit_for(Quantity(12000, "psi")).limit_kg_per_m3 == pytest.approx(435.0)

    def test_below_the_table(self) -> None:
        with pytest.raises(CarbonError) as caught:
            BenchmarkTable.defaults().limit_for(Quantity(2000, "psi"))
        assert caught.value.code == "BENCHMARK_BELOW_TABLE"

    def test_the_refusal_names_the_weakest_class(self) -> None:
        with pytest.raises(CarbonError) as caught:
            BenchmarkTable.defaults().limit_for(Quantity(2000, "psi"))
        assert "2500" in str(caught.value)


class CaseAssessment:
    def test_a_mix_under_its_limit(self) -> None:
        found = assess(
            footprint_of(factories.design(), book()),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            book(),
            TODAY,
        )
        assert found.under_limit
        assert found.margin > 0.0

    def test_the_margin_reads_as_a_share(self) -> None:
        found = assess(
            footprint_of(factories.design(), book()),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            book(),
            TODAY,
        )
        assert found.below_by.value == pytest.approx(
            100.0 * found.margin / found.limit.limit_kg_per_m3
        )

    def test_a_mix_over_its_limit(self) -> None:
        rich = factories.design(proportions=factories.proportions(scm=0.0, cementitious=900.0))
        found = assess(
            footprint_of(rich, book()),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            book(),
            TODAY,
        )
        assert not found.under_limit
        assert found.margin < 0.0
        assert "over the limit" in found.blockers[0]

    def test_industry_averages_cannot_be_declared(self) -> None:
        found = assess(
            footprint_of(factories.design(), book()),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            book(),
            TODAY,
        )
        assert found.under_limit
        assert not found.can_be_declared
        assert "not all product EPDs" in " ".join(found.blockers)

    def test_current_epds_can_be_declared(self) -> None:
        epds = book(provenance=Provenance.PRODUCT_EPD, published=date(2023, 1, 1))
        found = assess(
            footprint_of(factories.design(), epds),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            epds,
            TODAY,
        )
        assert found.can_be_declared
        assert found.blockers == ()

    def test_an_aged_out_epd_blocks_the_declaration(self) -> None:
        epds = book(provenance=Provenance.PRODUCT_EPD, published=date(2017, 1, 1))
        found = assess(
            footprint_of(factories.design(), epds),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            epds,
            TODAY,
        )
        assert found.under_limit
        assert not found.can_be_declared
        assert "aged out" in " ".join(found.blockers)

    def test_the_stale_list_is_sorted(self) -> None:
        epds = book(provenance=Provenance.PRODUCT_EPD, published=date(2017, 1, 1))
        found = assess(
            footprint_of(factories.design(), epds),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            epds,
            TODAY,
        )
        assert list(found.stale_factors) == sorted(found.stale_factors)

    def test_a_longer_validity_window_rescues_it(self) -> None:
        epds = book(provenance=Provenance.PRODUCT_EPD, published=date(2017, 1, 1))
        found = assess(
            footprint_of(factories.design(), epds),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            epds,
            TODAY,
            years=10,
        )
        assert found.can_be_declared

    def test_all_three_blockers_at_once(self) -> None:
        rich = factories.design(proportions=factories.proportions(scm=0.0, cementitious=900.0))
        stale = book(provenance=Provenance.INDUSTRY_AVERAGE)
        found = assess(
            footprint_of(rich, stale),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            stale,
            TODAY,
        )
        assert len(found.blockers) == 3

    def test_describe(self) -> None:
        found = assess(
            footprint_of(factories.design(), book()),
            Quantity(4500, "psi"),
            BenchmarkTable.defaults(),
            book(),
            TODAY,
        )
        assert "4000P-57" in found.describe()
        assert "not declarable" in found.describe()


def test_an_assessment_exactly_on_the_limit_clears() -> None:
    limit = BenchmarkClass(Quantity(4000, "psi"), 300.0)
    found = Assessment("X", Quantity(4000, "psi"), 300.0, limit, True)
    assert found.under_limit
    assert found.margin == pytest.approx(0.0)
    assert found.can_be_declared
