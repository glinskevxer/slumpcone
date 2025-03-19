from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.money import Money
from slumpcone.percent import Percent
from slumpcone.sales.account import PaymentTerms
from slumpcone.sales.charges import AppliedCharge, ChargeKind
from slumpcone.sales.invoice import (
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Payment,
    aging,
    balance_of,
    overdue_of,
)
from slumpcone.units.quantity import Quantity

INVOICED = date(2024, 6, 12)


def line(ticket: str = "881204", volume: float = 9.0) -> InvoiceLine:
    return InvoiceLine(ticket, "4000P-57", Quantity(volume, "yd3"), Money.of("118.50"))


def invoice(**overrides: object) -> Invoice:
    fields: dict[str, object] = {
        "number": "INV-2211",
        "account_code": "ASH-01",
        "invoiced_on": INVOICED,
        "lines": (line("881204"), line("881205", 7.0)),
        "charges": (AppliedCharge(ChargeKind.FUEL, 1.0, Money.of("66.36")),),
        "terms": PaymentTerms(30),
        "tax": Percent(6.0),
        "project": "Route 9 shoulder",
    }
    fields.update(overrides)
    return Invoice(**fields)  # type: ignore[arg-type]


class CaseStatus:
    def test_which_statuses_are_owed(self) -> None:
        assert InvoiceStatus.ISSUED.is_owed
        assert InvoiceStatus.PART_PAID.is_owed
        assert not InvoiceStatus.DRAFT.is_owed
        assert not InvoiceStatus.PAID.is_owed

    def test_which_are_settled(self) -> None:
        assert InvoiceStatus.PAID.is_settled
        assert InvoiceStatus.VOID.is_settled
        assert not InvoiceStatus.ISSUED.is_settled

    def test_it_prints_its_own_value(self) -> None:
        assert str(InvoiceStatus.PART_PAID) == "part_paid"


class CaseLines:
    def test_the_amount(self) -> None:
        assert line().amount == Money.of("1066.50")

    def test_a_non_volume(self) -> None:
        with pytest.raises(ValidationError, match="invoiced quantity is a volume"):
            InvoiceLine("881204", "M", Quantity(9, "lb"), Money.of("118.50"))

    def test_a_zero_quantity(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            InvoiceLine("881204", "M", Quantity(0, "yd3"), Money.of("118.50"))

    def test_a_negative_price(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            InvoiceLine("881204", "M", Quantity(9, "yd3"), Money.of("-1.00"))

    def test_describe(self) -> None:
        assert "881204" in line().describe()
        assert "$1,066.50" in line().describe()


class CaseTotals:
    def test_the_concrete_and_the_extras(self) -> None:
        assert invoice().concrete == Money.of("1896.00")
        assert invoice().extras == Money.of("66.36")

    def test_the_subtotal_and_tax(self) -> None:
        assert invoice().subtotal == Money.of("1962.36")
        assert invoice().tax_amount == Money.of("117.74")

    def test_the_total(self) -> None:
        assert invoice().total == Money.of("2080.10")

    def test_no_tax(self) -> None:
        assert invoice(tax=Percent(0.0)).total == Money.of("1962.36")

    def test_a_silly_tax_rate(self) -> None:
        with pytest.raises(ValidationError, match="share of the invoice"):
            invoice(tax=Percent(120.0))

    def test_nothing_paid_yet(self) -> None:
        assert invoice().paid.is_zero()
        assert invoice().outstanding == invoice().total


class CasePayments:
    def issued(self) -> Invoice:
        return invoice().issue()

    def test_a_draft_cannot_take_a_payment(self) -> None:
        with pytest.raises(RuleViolationError, match="INVOICE_NOT_ISSUED"):
            invoice().receive(Payment(INVOICED, Money.of("100.00")))

    def test_a_part_payment(self) -> None:
        paid = self.issued().receive(Payment(date(2024, 6, 20), Money.of("1000.00")))
        assert paid.status is InvoiceStatus.PART_PAID
        assert paid.outstanding == Money.of("1080.10")

    def test_paying_it_off(self) -> None:
        paid = self.issued().receive(Payment(date(2024, 6, 20), Money.of("2080.10")))
        assert paid.status is InvoiceStatus.PAID
        assert paid.outstanding.is_zero()

    def test_two_part_payments_settle_it(self) -> None:
        once = self.issued().receive(Payment(date(2024, 6, 20), Money.of("1000.00")))
        twice = once.receive(Payment(date(2024, 6, 25), Money.of("1080.10")))
        assert twice.status is InvoiceStatus.PAID

    def test_overpayment(self) -> None:
        paid = self.issued().receive(Payment(date(2024, 6, 20), Money.of("2500.00")))
        assert paid.is_overpaid
        assert paid.outstanding.is_zero()

    def test_a_payment_before_the_invoice(self) -> None:
        with pytest.raises(ValidationError, match="before the invoice"):
            invoice(payments=(Payment(date(2024, 6, 1), Money.of("100.00")),))

    def test_a_payment_of_nothing(self) -> None:
        with pytest.raises(ValidationError, match="has to be positive"):
            Payment(INVOICED, Money.zero())

    def test_a_void_invoice_cannot_take_one(self) -> None:
        with pytest.raises(RuleViolationError, match="INVOICE_VOID"):
            invoice().issue().void().receive(Payment(INVOICED, Money.of("1.00")))


class CaseLifecycle:
    def test_issue(self) -> None:
        issued = invoice().issue()
        assert issued.status is InvoiceStatus.ISSUED

    def test_issuing_twice(self) -> None:
        with pytest.raises(RuleViolationError, match="INVOICE_ALREADY_ISSUED"):
            invoice().issue().issue()

    def test_an_empty_invoice_cannot_be_issued(self) -> None:
        with pytest.raises(ValidationError, match="at least one line"):
            invoice(lines=()).issue()

    def test_issuing_on_another_day_moves_the_date(self) -> None:
        issued = invoice().issue(date(2024, 6, 30))
        assert issued.invoiced_on == date(2024, 6, 30)
        assert issued.due_on == date(2024, 7, 30)

    def test_void(self) -> None:
        assert invoice().issue().void().status is InvoiceStatus.VOID

    def test_voiding_one_that_has_taken_money(self) -> None:
        paid = invoice().issue().receive(Payment(date(2024, 6, 20), Money.of("100.00")))
        with pytest.raises(RuleViolationError, match="INVOICE_HAS_PAYMENTS"):
            paid.void()


class CaseAging:
    def issued(self, **overrides: object) -> Invoice:
        return invoice(**overrides).issue()

    def test_due_date(self) -> None:
        assert invoice().due_on == date(2024, 7, 12)

    def test_not_overdue_before_the_due_date(self) -> None:
        assert not self.issued().is_overdue(date(2024, 7, 1))
        assert self.issued().aging_bucket(date(2024, 7, 1)) == "current"

    def test_overdue_after_it(self) -> None:
        assert self.issued().is_overdue(date(2024, 7, 20))
        assert self.issued().days_overdue(date(2024, 7, 20)) == 8

    def test_a_paid_invoice_is_never_overdue(self) -> None:
        paid = self.issued().receive(Payment(date(2024, 6, 20), Money.of("2080.10")))
        assert not paid.is_overdue(date(2024, 9, 1))

    def test_the_buckets(self) -> None:
        issued = self.issued()
        assert issued.aging_bucket(date(2024, 7, 20)) == "1 to 30"
        assert issued.aging_bucket(date(2024, 8, 20)) == "31 to 60"
        assert issued.aging_bucket(date(2024, 9, 20)) == "61 to 90"
        assert issued.aging_bucket(date(2024, 12, 20)) == "over 90"

    def test_a_balance_is_not_an_overdue_balance(self) -> None:
        issued = self.issued()
        on = date(2024, 7, 1)
        assert balance_of([issued]) == issued.total
        assert overdue_of([issued], on).is_zero()

    def test_both_once_it_runs_past_terms(self) -> None:
        issued = self.issued()
        on = date(2024, 7, 20)
        assert overdue_of([issued], on) == issued.total

    def test_a_draft_is_not_a_balance(self) -> None:
        assert balance_of([invoice()]).is_zero()

    def test_the_aging_table(self) -> None:
        table = aging([self.issued()], date(2024, 8, 20))
        assert table["31 to 60"] > Money.zero()
        assert table["current"].is_zero()
        assert set(table) == {"current", "1 to 30", "31 to 60", "61 to 90", "over 90"}

    def test_describe(self) -> None:
        line_text = self.issued().describe()
        assert "INV-2211" in line_text
        assert "due 2024-07-12" in line_text
