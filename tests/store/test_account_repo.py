from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.money import Money
from slumpcone.sales.account import Account, AccountStatus, PaymentTerms
from slumpcone.store.account_repo import AccountRepository
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate

DAY = date(2024, 6, 12)


@pytest.fixture()
def repo() -> AccountRepository:
    database = Database.in_memory()
    migrate(database)
    return AccountRepository(database)


def account(code: str = "ASH-01", **overrides: object) -> Account:
    fields: dict[str, object] = {
        "code": code,
        "name": "Ashfield Paving",
        "terms": PaymentTerms(30, 10, 2.0),
        "credit_limit": Money.of("25000.00"),
        "contact": "Dee Kelso",
        "phone": "555 0142",
        "notes": "night deliveries only",
    }
    fields.update(overrides)
    return Account(**fields)  # type: ignore[arg-type]


class CaseRoundTrip:
    def test_everything_comes_back(self, repo: AccountRepository) -> None:
        repo.save(account())
        loaded = repo.get("ash 01")
        assert loaded.name == "Ashfield Paving"
        assert loaded.terms.describe() == "2/10 net 30"
        assert loaded.credit_limit == Money.of("25000.00")
        assert loaded.contact == "Dee Kelso"
        assert loaded.notes == "night deliveries only"

    def test_an_account_with_no_limit(self, repo: AccountRepository) -> None:
        repo.save(account(credit_limit=None, contact=None, phone=None, notes=""))
        loaded = repo.get("ASH-01")
        assert loaded.credit_limit is None
        assert loaded.contact is None

    def test_the_amount_is_exact(self, repo: AccountRepository) -> None:
        repo.save(account(credit_limit=Money.of("25000.07")))
        assert repo.get("ASH-01").credit_limit == Money.of("25000.07")

    def test_save_is_an_upsert(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.save(account(status=AccountStatus.ON_HOLD))
        assert repo.get("ASH-01").status is AccountStatus.ON_HOLD
        assert len(repo.all()) == 1

    def test_an_unknown_account(self, repo: AccountRepository) -> None:
        with pytest.raises(NotFoundError, match="ASH-09"):
            repo.get("ASH-09")

    def test_all_is_sorted(self, repo: AccountRepository) -> None:
        repo.save(account("ASH-01"))
        repo.save(account("ABB-02"))
        assert [entry.code for entry in repo.all()] == ["ABB-02", "ASH-01"]

    def test_open_accounts(self, repo: AccountRepository) -> None:
        repo.save(account("ASH-01"))
        repo.save(account("ABB-02", status=AccountStatus.CLOSED))
        assert [entry.code for entry in repo.open_accounts()] == ["ASH-01"]

    def test_delete(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.delete("ASH-01")
        assert repo.all() == ()

    def test_deleting_an_unknown_account(self, repo: AccountRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("ASH-09")


class CaseQuotes:
    def test_a_quote_round_trips(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.quote("ASH-01", "4000P-57", Money.of("118.50"))
        assert repo.quoted_price("ash 01", "4000p 57", DAY) == Money.of("118.50")

    def test_a_quote_needs_an_account(self, repo: AccountRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.quote("ASH-01", "4000P-57", Money.of("118.50"))

    def test_the_same_window_twice(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.quote("ASH-01", "4000P-57", Money.of("118.50"))
        with pytest.raises(ConflictError, match="always"):
            repo.quote("ASH-01", "4000P-57", Money.of("120.00"))

    def test_the_latest_window_that_has_started_wins(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.quote("ASH-01", "4000P-57", Money.of("118.50"), effective_from=date(2024, 1, 1))
        repo.quote("ASH-01", "4000P-57", Money.of("124.00"), effective_from=date(2024, 6, 1))
        assert repo.quoted_price("ASH-01", "4000P-57", DAY) == Money.of("124.00")
        assert repo.quoted_price("ASH-01", "4000P-57", date(2024, 3, 1)) == Money.of("118.50")

    def test_a_window_that_has_ended_is_not_used(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.quote(
            "ASH-01",
            "4000P-57",
            Money.of("118.50"),
            effective_from=date(2024, 1, 1),
            effective_to=date(2024, 5, 31),
        )
        with pytest.raises(NotFoundError):
            repo.quoted_price("ASH-01", "4000P-57", DAY)

    def test_an_unquoted_mixture(self, repo: AccountRepository) -> None:
        repo.save(account())
        with pytest.raises(NotFoundError, match="4000P-57"):
            repo.quoted_price("ASH-01", "4000P-57", DAY)

    def test_quotes_for_an_account(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.quote("ASH-01", "4000P-57", Money.of("118.50"))
        repo.quote("ASH-01", "3000W-67", Money.of("104.00"))
        assert [code for code, _ in repo.quotes_for("ASH-01")] == [
            "3000W-67",
            "4000P-57",
        ]

    def test_deleting_an_account_takes_its_quotes(self, repo: AccountRepository) -> None:
        repo.save(account())
        repo.quote("ASH-01", "4000P-57", Money.of("118.50"))
        repo.delete("ASH-01")
        assert repo._db.scalar("SELECT count(*) FROM account_quote") == 0
