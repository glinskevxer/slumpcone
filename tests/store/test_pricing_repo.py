from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.money import Money
from slumpcone.pricing import MaterialPrice
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.store.pricing_repo import PricingRepository
from slumpcone.units.quantity import Quantity

DAY = date(2024, 6, 12)


@pytest.fixture()
def repo() -> PricingRepository:
    database = Database.in_memory()
    migrate(database)
    return PricingRepository(database)


def price(code: str = "CEM-I", amount: str = "142.00", **overrides: object) -> MaterialPrice:
    fields: dict[str, object] = {
        "material_code": code,
        "price": Money.of(amount),
        "per": Quantity(1, "ton"),
    }
    fields.update(overrides)
    return MaterialPrice(**fields)  # type: ignore[arg-type]


class CaseRoundTrip:
    def test_an_open_ended_price(self, repo: PricingRepository) -> None:
        repo.save(price())
        loaded = repo.for_material("cem i")[0]
        assert loaded.price == Money.of("142.00")
        assert loaded.per == Quantity(1, "ton")
        assert loaded.effective_from is None

    def test_the_amount_is_exact(self, repo: PricingRepository) -> None:
        repo.save(price(amount="142.07"))
        assert repo.for_material("CEM-I")[0].price.amount == Decimal("142.07")

    def test_a_windowed_price(self, repo: PricingRepository) -> None:
        repo.save(price(effective_from=date(2024, 6, 1), effective_to=date(2024, 6, 30)))
        loaded = repo.for_material("CEM-I")[0]
        assert loaded.effective_from == date(2024, 6, 1)
        assert loaded.effective_to == date(2024, 6, 30)

    def test_a_price_in_another_currency(self, repo: PricingRepository) -> None:
        repo.save(price(price=Money.of("120.00", "EUR")))
        assert repo.for_material("CEM-I")[0].price.currency == "EUR"

    def test_save_all(self, repo: PricingRepository) -> None:
        repo.save_all([price("CEM-I"), price("CA-57", "17.50")])
        assert repo.codes() == ("CA-57", "CEM-I")


class CaseWindows:
    def test_the_same_start_twice_is_refused(self, repo: PricingRepository) -> None:
        repo.save(price(effective_from=date(2024, 6, 1)))
        with pytest.raises(ConflictError, match="starting 2024-06-01"):
            repo.save(price(amount="151.00", effective_from=date(2024, 6, 1)))

    def test_two_open_ended_prices_are_refused(self, repo: PricingRepository) -> None:
        repo.save(price())
        with pytest.raises(ConflictError, match="with no start date"):
            repo.save(price(amount="151.00"))

    def test_a_later_window_is_allowed(self, repo: PricingRepository) -> None:
        repo.save(price(effective_from=date(2024, 1, 1)))
        repo.save(price(amount="151.00", effective_from=date(2024, 6, 1)))
        assert len(repo.for_material("CEM-I")) == 2

    def test_windows_come_back_oldest_first(self, repo: PricingRepository) -> None:
        repo.save(price(amount="151.00", effective_from=date(2024, 6, 1)))
        repo.save(price(effective_from=date(2024, 1, 1)))
        starts = [entry.effective_from for entry in repo.for_material("CEM-I")]
        assert starts == [date(2024, 1, 1), date(2024, 6, 1)]

    def test_close_out(self, repo: PricingRepository) -> None:
        repo.save(price(effective_from=date(2024, 1, 1)))
        assert repo.close_out("CEM-I", date(2024, 5, 31)) == 1
        assert repo.for_material("CEM-I")[0].effective_to == date(2024, 5, 31)

    def test_close_out_with_nothing_open(self, repo: PricingRepository) -> None:
        assert repo.close_out("CEM-I", DAY) == 0


class CaseLookups:
    def test_current(self, repo: PricingRepository) -> None:
        repo.save(price(effective_from=date(2024, 1, 1)))
        repo.save(price(amount="151.00", effective_from=date(2024, 6, 1)))
        assert repo.current("CEM-I", DAY).price == Money.of("151.00")
        assert repo.current("CEM-I", date(2024, 3, 1)).price == Money.of("142.00")

    def test_an_unpriced_material(self, repo: PricingRepository) -> None:
        with pytest.raises(NotFoundError, match="CEM-I"):
            repo.current("CEM-I", DAY)

    def test_the_whole_price_list(self, repo: PricingRepository) -> None:
        repo.save_all([price("CEM-I"), price("CA-57", "17.50")])
        prices = repo.price_list()
        assert len(prices) == 2
        assert prices.for_material("CA-57", DAY).price == Money.of("17.50")

    def test_delete_for(self, repo: PricingRepository) -> None:
        repo.save_all([price("CEM-I"), price("CA-57", "17.50")])
        assert repo.delete_for("CEM-I") == 1
        assert repo.codes() == ("CA-57",)

    def test_deleting_an_unpriced_material(self, repo: PricingRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete_for("CEM-I")
