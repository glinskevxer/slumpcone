from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.money import Money
from slumpcone.sales.account import Account, AccountStatus, PaymentTerms

INVOICED = date(2024, 6, 12)


def account(**overrides: object) -> Account:
    fields: dict[str, object] = {
        "code": "ASH-01",
        "name": "Ashfield Paving",
        "credit_limit": Money.of("25000.00"),
        "contact": "Dee Kelso",
    }
    fields.update(overrides)
    return Account(**fields)  # type: ignore[arg-type]


class CaseStatus:
    def test_parse(self) -> None:
        assert AccountStatus.parse("on hold") is AccountStatus.ON_HOLD
        assert AccountStatus.parse("CASH-ONLY") is AccountStatus.CASH_ONLY

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="account status"):
            AccountStatus.parse("dubious")

    def test_which_statuses_take_orders(self) -> None:
        assert AccountStatus.OPEN.takes_orders
        assert AccountStatus.CASH_ONLY.takes_orders
        assert not AccountStatus.ON_HOLD.takes_orders
        assert not AccountStatus.CLOSED.takes_orders

    def test_cash_only_needs_paying_first(self) -> None:
        assert AccountStatus.CASH_ONLY.needs_payment_first
        assert not AccountStatus.OPEN.needs_payment_first

    def test_it_prints_its_own_value(self) -> None:
        assert str(AccountStatus.ON_HOLD) == "on_hold"


class CaseTerms:
    def test_a_plain_term(self) -> None:
        terms = PaymentTerms(30)
        assert terms.due_on(INVOICED) == date(2024, 7, 12)
        assert terms.describe() == "net 30"
        assert not terms.has_discount

    def test_cash_on_delivery(self) -> None:
        terms = PaymentTerms(0)
        assert terms.is_on_delivery
        assert terms.describe() == "cash on delivery"

    def test_a_discount_term(self) -> None:
        terms = PaymentTerms(30, 10, 2.0)
        assert terms.has_discount
        assert terms.describe() == "2/10 net 30"
        assert terms.discount_until(INVOICED) == date(2024, 6, 22)

    def test_the_discount_is_earned_inside_the_window(self) -> None:
        terms = PaymentTerms(30, 10, 2.0)
        earned = terms.discount_on(Money.of("1000.00"), date(2024, 6, 20), INVOICED)
        assert earned == Money.of("20.00")

    def test_it_is_not_earned_after_it(self) -> None:
        terms = PaymentTerms(30, 10, 2.0)
        assert terms.discount_on(Money.of("1000.00"), date(2024, 6, 30), INVOICED).is_zero()

    def test_no_discount_earns_nothing(self) -> None:
        assert PaymentTerms(30).discount_on(Money.of("1000.00"), INVOICED, INVOICED).is_zero()

    def test_negative_terms_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            PaymentTerms(-1)

    def test_a_discount_window_outlasting_the_term(self) -> None:
        with pytest.raises(ValidationError, match="outlast the term"):
            PaymentTerms(10, 30, 2.0)

    def test_a_silly_discount(self) -> None:
        with pytest.raises(ValidationError, match="share of the invoice"):
            PaymentTerms(30, 10, 120.0)


class CaseAccount:
    def test_names_are_normalised(self) -> None:
        built = account(code=" ash 01 ", name="  Ashfield   Paving ")
        assert built.code == "ASH-01"
        assert built.name == "Ashfield Paving"

    def test_a_negative_credit_limit(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            account(credit_limit=Money.of("-1.00"))

    def test_available_credit(self) -> None:
        assert account().available_credit(Money.of("10000.00")) == Money.of("15000.00")

    def test_no_limit_means_no_figure(self) -> None:
        assert account(credit_limit=None).available_credit(Money.of("1.00")) is None
        assert not account(credit_limit=None).has_credit_limit

    def test_a_balance_in_another_currency(self) -> None:
        with pytest.raises(ValidationError, match="the limit is in"):
            account().available_credit(Money.of("1.00", "EUR"))

    def test_an_order_inside_the_limit(self) -> None:
        assert account().blocking_reasons(Money.of("10000.00"), Money.of("5000.00")) == ()

    def test_an_order_past_the_limit(self) -> None:
        reasons = account().blocking_reasons(Money.of("24000.00"), Money.of("5000.00"))
        assert any("credit is left" in reason for reason in reasons)

    def test_an_account_on_hold(self) -> None:
        reasons = account(status=AccountStatus.ON_HOLD).blocking_reasons(
            Money.zero(), Money.of("100.00")
        )
        assert reasons == ("the account is on_hold",)

    def test_both_reasons_at_once(self) -> None:
        reasons = account(status=AccountStatus.CLOSED).blocking_reasons(
            Money.of("24000.00"), Money.of("5000.00")
        )
        assert len(reasons) == 2

    def test_require_credit_passes(self) -> None:
        account().require_credit(Money.of("1000.00"), Money.of("500.00"))

    def test_require_credit_refuses(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            account().require_credit(Money.of("24000.00"), Money.of("5000.00"))
        assert caught.value.code == "ACCOUNT_BLOCKED"

    def test_an_account_with_no_limit_never_blocks_on_credit(self) -> None:
        bare = account(credit_limit=None)
        bare.require_credit(Money.of("999999.00"), Money.of("5000.00"))

    def test_describe(self) -> None:
        line = account(terms=PaymentTerms(30, 10, 2.0)).describe()
        assert "ASH-01" in line
        assert "2/10 net 30" in line
        assert "$25,000.00" in line
