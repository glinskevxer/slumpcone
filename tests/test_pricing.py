from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.money import Money
from slumpcone.pricing import (
    CostBreakdown,
    MaterialPrice,
    PriceList,
    cheapest,
    cost_of,
    margin,
)
from slumpcone.units.quantity import Quantity
from tests.factories import proportions

DAY = date(2024, 6, 12)


def price_list() -> PriceList:
    return PriceList(
        [
            MaterialPrice("CEM-I", Money.of("142.00"), Quantity(1, "ton")),
            MaterialPrice("SCM-F", Money.of("88.00"), Quantity(1, "ton")),
            MaterialPrice("CA-57", Money.of("17.50"), Quantity(1, "ton")),
            MaterialPrice("FA-1", Money.of("14.25"), Quantity(1, "ton")),
            MaterialPrice("W-1", Money.of("0.01"), Quantity(100, "lb")),
            MaterialPrice("AD-AE", Money.of("0.09"), Quantity(1, "floz")),
            MaterialPrice("AD-WR", Money.of("0.06"), Quantity(1, "floz")),
        ]
    )


class CaseMaterialPrice:
    def test_the_code_is_normalised(self) -> None:
        assert (
            MaterialPrice("cem i", Money.of("1"), Quantity(1, "ton")).material_code == "CEM-I"
        )

    def test_a_non_positive_basis_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="per some positive amount"):
            MaterialPrice("CEM-I", Money.of("1"), Quantity(0, "ton"))

    def test_a_window_that_ends_before_it_starts(self) -> None:
        with pytest.raises(ValidationError, match="cannot end before"):
            MaterialPrice(
                "CEM-I",
                Money.of("1"),
                Quantity(1, "ton"),
                effective_from=date(2024, 6, 1),
                effective_to=date(2024, 5, 1),
            )

    def test_cost_of_an_amount(self) -> None:
        price = MaterialPrice("CEM-I", Money.of("142.00"), Quantity(1, "ton"))
        assert price.cost_of(Quantity(4230, "lb")) == Money.of("300.33")

    def test_a_charge_in_the_wrong_dimension(self) -> None:
        price = MaterialPrice("CEM-I", Money.of("142.00"), Quantity(1, "ton"))
        with pytest.raises(ValidationError, match="priced per"):
            price.cost_of(Quantity(1, "yd3"))

    def test_covers(self) -> None:
        price = MaterialPrice(
            "CEM-I",
            Money.of("142.00"),
            Quantity(1, "ton"),
            effective_from=date(2024, 6, 1),
            effective_to=date(2024, 6, 30),
        )
        assert price.covers(DAY)
        assert not price.covers(date(2024, 5, 31))
        assert not price.covers(date(2024, 7, 1))

    def test_an_open_ended_price_covers_everything(self) -> None:
        assert MaterialPrice("CEM-I", Money.of("1"), Quantity(1, "ton")).covers(DAY)

    def test_describe(self) -> None:
        text = MaterialPrice(
            "CEM-I", Money.of("142.00"), Quantity(1, "ton"), effective_from=date(2024, 6, 1)
        ).describe()
        assert "CEM-I" in text
        assert "$142.00" in text
        assert "from 2024-06-01" in text


class CasePriceList:
    def test_lookup(self) -> None:
        assert price_list().for_material("cem i", DAY).price == Money.of("142.00")

    def test_an_unpriced_material(self) -> None:
        with pytest.raises(NotFoundError, match="CEM-III"):
            price_list().for_material("CEM-III", DAY)

    def test_the_latest_price_that_has_started_wins(self) -> None:
        prices = PriceList(
            [
                MaterialPrice(
                    "CEM-I",
                    Money.of("142.00"),
                    Quantity(1, "ton"),
                    effective_from=date(2024, 1, 1),
                ),
                MaterialPrice(
                    "CEM-I",
                    Money.of("151.00"),
                    Quantity(1, "ton"),
                    effective_from=date(2024, 6, 1),
                ),
            ]
        )
        assert prices.for_material("CEM-I", DAY).price == Money.of("151.00")
        assert prices.for_material("CEM-I", date(2024, 3, 1)).price == Money.of("142.00")

    def test_codes_and_length(self) -> None:
        prices = price_list()
        assert len(prices) == 7
        assert "CEM-I" in prices.codes()

    def test_add(self) -> None:
        prices = PriceList()
        prices.add(MaterialPrice("CEM-I", Money.of("1"), Quantity(1, "ton")))
        assert len(prices) == 1


class CaseCostOf:
    def test_every_material_gets_a_line(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(9, "yd3"), DAY)
        assert len(breakdown.lines) == 7
        assert breakdown.is_complete

    def test_the_total_and_the_unit_cost(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(9, "yd3"), DAY)
        assert breakdown.total > Money.of("400.00")
        assert breakdown.per_unit == breakdown.total / 9

    def test_the_cement_is_the_biggest_line(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(1, "yd3"), DAY)
        biggest = max(breakdown.lines, key=lambda line: line.cost.amount)
        assert biggest.material_code == "CEM-I"

    def test_an_unpriced_material_is_reported(self) -> None:
        prices = PriceList([MaterialPrice("CEM-I", Money.of("142.00"), Quantity(1, "ton"))])
        breakdown = cost_of(proportions(), prices, Quantity(1, "yd3"), DAY)
        assert not breakdown.is_complete
        assert "CA-57" in breakdown.missing
        assert "AD-AE" in breakdown.missing

    def test_the_share_of_a_line(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(1, "yd3"), DAY)
        line = breakdown.line("CEM-I")
        assert line.share_of(breakdown.total).value > 40.0

    def test_a_share_of_nothing(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(1, "yd3"), DAY)
        assert breakdown.line("CEM-I").share_of(Money.zero()).value == pytest.approx(0.0)

    def test_an_unknown_line(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(1, "yd3"), DAY)
        with pytest.raises(NotFoundError):
            breakdown.line("CEM-III")

    def test_a_non_volume_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="batch size is a volume"):
            cost_of(proportions(), price_list(), Quantity(9, "lb"), DAY)

    def test_a_batch_of_nothing_has_no_unit_cost(self) -> None:
        empty = CostBreakdown(Quantity(0, "yd3"), ())
        with pytest.raises(ValidationError, match="no unit cost"):
            _ = empty.per_unit

    def test_render_and_describe(self) -> None:
        breakdown = cost_of(proportions(), price_list(), Quantity(9, "yd3"), DAY)
        assert "material" in breakdown.render().splitlines()[0]
        assert "per unit" in breakdown.describe()

    def test_describe_names_the_missing_prices(self) -> None:
        prices = PriceList([MaterialPrice("CEM-I", Money.of("142.00"), Quantity(1, "ton"))])
        breakdown = cost_of(proportions(), prices, Quantity(1, "yd3"), DAY)
        assert "no price for" in breakdown.describe()


class CaseComparisons:
    def test_margin(self) -> None:
        assert margin(Money.of("120.00"), Money.of("90.00")).value == pytest.approx(25.0)

    def test_a_negative_margin(self) -> None:
        assert margin(Money.of("80.00"), Money.of("90.00")).value < 0.0

    def test_a_sale_of_nothing(self) -> None:
        with pytest.raises(ValidationError, match="no margin"):
            margin(Money.zero(), Money.of("90.00"))

    def test_cheapest(self) -> None:
        rich = cost_of(proportions(), price_list(), Quantity(1, "yd3"), DAY)
        lean = cost_of(
            proportions(cementitious=470.0, sand=1350.0),
            price_list(),
            Quantity(1, "yd3"),
            DAY,
        )
        assert cheapest([rich, lean]) is lean

    def test_cheapest_of_nothing(self) -> None:
        with pytest.raises(ValidationError, match="nothing to compare"):
            cheapest([])
