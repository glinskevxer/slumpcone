from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.errors import NotFoundError, RuleViolationError
from slumpcone.money import Money
from slumpcone.percent import Percent
from slumpcone.sales.account import PaymentTerms
from slumpcone.sales.charges import AppliedCharge, ChargeKind
from slumpcone.sales.invoice import Invoice, InvoiceLine, InvoiceStatus, Payment
from slumpcone.store.batch_repo import BatchRepository
from slumpcone.store.db import Database
from slumpcone.store.invoice_repo import InvoiceRepository
from slumpcone.store.migrations import migrate
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

INVOICED = date(2024, 6, 12)


@pytest.fixture()
def database() -> Database:
    db = Database.in_memory()
    migrate(db)
    return db


@pytest.fixture()
def repo(database: Database) -> InvoiceRepository:
    return InvoiceRepository(database)


def invoice(number: str = "INV-2211", **overrides: object) -> Invoice:
    fields: dict[str, object] = {
        "number": number,
        "account_code": "ASH-01",
        "invoiced_on": INVOICED,
        "lines": (
            InvoiceLine("881204", "4000P-57", Quantity(9, "yd3"), Money.of("118.50")),
            InvoiceLine("881205", "4000P-57", Quantity(7, "yd3"), Money.of("118.50")),
        ),
        "charges": (AppliedCharge(ChargeKind.FUEL, 1.0, Money.of("66.36"), "3.5% surcharge"),),
        "terms": PaymentTerms(30, 10, 2.0),
        "tax": Percent(6.0),
        "project": "Route 9 shoulder",
        "notes": "night pour",
    }
    fields.update(overrides)
    return Invoice(**fields)  # type: ignore[arg-type]


def write_ticket(database: Database, number: str) -> None:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), INVOICED)
    BatchRepository(database).save(
        BatchTicket.from_plan(planned, number, datetime(2024, 6, 12, 7, 42))
    )


class CaseRoundTrip:
    def test_everything_comes_back(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        loaded = repo.get("inv 2211")
        assert loaded.account_code == "ASH-01"
        assert len(loaded.lines) == 2
        assert loaded.charges[0].reason == "3.5% surcharge"
        assert loaded.terms.describe() == "2/10 net 30"
        assert loaded.tax == Percent(6.0)
        assert loaded.project == "Route 9 shoulder"
        assert loaded.notes == "night pour"

    def test_the_totals_survive(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        assert repo.get("INV-2211").total == invoice().total

    def test_the_amounts_are_exact(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        assert repo.get("INV-2211").lines[0].unit_price == Money.of("118.50")

    def test_a_bare_invoice(self, repo: InvoiceRepository) -> None:
        repo.save(invoice(charges=(), project=None, notes="", tax=Percent(0.0)))
        loaded = repo.get("INV-2211")
        assert loaded.charges == ()
        assert loaded.project is None

    def test_payments_survive(self, repo: InvoiceRepository) -> None:
        issued = (
            invoice()
            .issue()
            .receive(Payment(date(2024, 6, 20), Money.of("1000.00"), "CHK-4471"))
        )
        repo.save(issued)
        loaded = repo.get("INV-2211")
        assert loaded.status is InvoiceStatus.PART_PAID
        assert loaded.payments[0].reference == "CHK-4471"
        assert loaded.outstanding == issued.outstanding

    def test_an_unknown_invoice(self, repo: InvoiceRepository) -> None:
        with pytest.raises(NotFoundError, match="INV-9"):
            repo.get("INV-9")


class CaseRewriting:
    def test_a_draft_can_be_rewritten(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        repo.save(invoice(lines=invoice().lines[:1]))
        assert len(repo.get("INV-2211").lines) == 1

    def test_rewriting_replaces_rather_than_appends(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        repo.save(invoice(charges=()))
        assert repo.get("INV-2211").charges == ()

    def test_an_invoice_that_took_money_cannot_be_reset(self, repo: InvoiceRepository) -> None:
        repo.save(invoice().issue().receive(Payment(date(2024, 6, 20), Money.of("100.00"))))
        with pytest.raises(RuleViolationError, match="INVOICE_SETTLED"):
            repo.save(invoice())

    def test_a_void_invoice_cannot_be_rewritten(self, repo: InvoiceRepository) -> None:
        repo.save(invoice().issue().void())
        with pytest.raises(RuleViolationError, match="INVOICE_SETTLED"):
            repo.save(invoice())

    def test_a_payment_can_still_be_added(self, repo: InvoiceRepository) -> None:
        repo.save(invoice().issue())
        loaded = repo.get("INV-2211")
        repo.save(loaded.receive(Payment(date(2024, 6, 20), Money.of("100.00"))))
        assert repo.get("INV-2211").paid == Money.of("100.00")


class CaseQueries:
    def stock(self, repo: InvoiceRepository) -> None:
        repo.save(invoice("INV-2211").issue())
        repo.save(invoice("INV-2212", invoiced_on=date(2024, 7, 2)))
        repo.save(invoice("INV-2213", account_code="ABB-02").issue())

    def test_for_account(self, repo: InvoiceRepository) -> None:
        self.stock(repo)
        assert [entry.number for entry in repo.for_account("ash 01")] == [
            "INV-2211",
            "INV-2212",
        ]

    def test_between(self, repo: InvoiceRepository) -> None:
        self.stock(repo)
        found = repo.between(date(2024, 6, 1), date(2024, 6, 30))
        assert [entry.number for entry in found] == ["INV-2211", "INV-2213"]

    def test_owed_leaves_out_the_draft(self, repo: InvoiceRepository) -> None:
        self.stock(repo)
        assert [entry.number for entry in repo.owed()] == ["INV-2211", "INV-2213"]

    def test_for_ticket(self, repo: InvoiceRepository) -> None:
        self.stock(repo)
        found = repo.for_ticket("881204")
        assert found is not None
        assert found.number == "INV-2211"

    def test_an_unbilled_ticket(self, repo: InvoiceRepository) -> None:
        assert repo.for_ticket("881299") is None

    def test_unbilled_tickets(self, repo: InvoiceRepository, database: Database) -> None:
        write_ticket(database, "881204")
        write_ticket(database, "881299")
        repo.save(invoice("INV-2211").issue())
        assert repo.unbilled_tickets(date(2024, 6, 1), date(2024, 6, 30)) == ("881299",)

    def test_delete_a_draft(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        repo.delete("INV-2211")
        with pytest.raises(NotFoundError):
            repo.get("INV-2211")

    def test_deleting_an_issued_invoice(self, repo: InvoiceRepository) -> None:
        repo.save(invoice().issue())
        with pytest.raises(RuleViolationError, match="INVOICE_NOT_A_DRAFT"):
            repo.delete("INV-2211")

    def test_deleting_takes_the_lines(self, repo: InvoiceRepository) -> None:
        repo.save(invoice())
        repo.delete("INV-2211")
        assert repo._db.scalar("SELECT count(*) FROM invoice_line") == 0
