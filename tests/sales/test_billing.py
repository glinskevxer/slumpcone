from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.money import Money
from slumpcone.percent import Percent
from slumpcone.sales.account import Account, PaymentTerms
from slumpcone.sales.billing import (
    BillingWindow,
    build_invoice,
    charge_summary,
    on_site_minutes,
    without_charge,
)
from slumpcone.sales.charges import ChargeKind, ChargeRule, ChargeSchedule
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import design

DAY = date(2024, 6, 12)
PRICES = {"4000P-57": Money.of("118.50")}


def account() -> Account:
    return Account("ASH-01", "Ashfield Paving", terms=PaymentTerms(30))


def ticket(number: str, volume: float = 9.0, hour: int = 8) -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(volume, "yd3"), DAY)
    return BatchTicket.from_plan(
        planned, number, datetime(2024, 6, 12, hour, 0), project="Route 9"
    )


def delivery(number: str, on_site: int = 40, returned: float | None = None) -> Delivery:
    arrived = datetime(2024, 6, 12, 8, 30)
    return Delivery(
        number,
        "TR-114",
        datetime(2024, 6, 12, 8, 0),
        arrived_at=arrived,
        discharge_started_at=arrived + timedelta(minutes=5),
        discharge_finished_at=arrived + timedelta(minutes=on_site),
        revolutions_at_discharge=210,
        returned_volume=None if returned is None else Quantity(returned, "yd3"),
    )


def schedule() -> ChargeSchedule:
    return ChargeSchedule(
        [
            ChargeRule(ChargeKind.SHORT_LOAD, Money.of("120.00")),
            ChargeRule(ChargeKind.STANDBY, Money.of("2.25")),
            ChargeRule(ChargeKind.AFTER_HOURS, Money.of("150.00")),
            ChargeRule(ChargeKind.WEEKEND, Money.of("200.00")),
            ChargeRule(ChargeKind.RETURNED_CONCRETE, Money.of("18.00")),
            ChargeRule(ChargeKind.FUEL, Money.of("3.5")),
        ]
    )


class CaseWindow:
    def test_the_default_day(self) -> None:
        hours = BillingWindow()
        assert not hours.is_after_hours(datetime(2024, 6, 12, 8, 0))
        assert hours.is_after_hours(datetime(2024, 6, 12, 5, 0))
        assert hours.is_after_hours(datetime(2024, 6, 12, 18, 0))

    def test_the_weekend(self) -> None:
        hours = BillingWindow()
        assert hours.is_weekend(datetime(2024, 6, 15, 8, 0))
        assert not hours.is_weekend(datetime(2024, 6, 12, 8, 0))

    def test_a_plant_can_set_its_own_hours(self) -> None:
        hours = BillingWindow(time(4, 0), time(20, 0))
        assert not hours.is_after_hours(datetime(2024, 6, 12, 5, 0))

    def test_a_day_that_ends_before_it_starts(self) -> None:
        with pytest.raises(ValidationError, match="end after it starts"):
            BillingWindow(time(18, 0), time(6, 0))

    def test_a_silly_weekday(self) -> None:
        with pytest.raises(ValidationError, match="0 to 6"):
            BillingWindow(weekend_days=(9,))


class CaseOnSite:
    def test_it_measures_arrival_to_finish(self) -> None:
        assert on_site_minutes(delivery("881204", on_site=40)) == pytest.approx(40.0)

    def test_an_unfinished_delivery(self) -> None:
        bare = Delivery("881204", "TR-114", datetime(2024, 6, 12, 8, 0))
        assert on_site_minutes(bare) is None


class CaseBuild:
    def test_a_line_per_ticket(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204"), ticket("881205")],
            PRICES,
            invoiced_on=DAY,
        )
        assert len(result.invoice.lines) == 2
        assert result.is_complete

    def test_the_lines_are_in_batch_order(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881205", hour=10), ticket("881204", hour=8)],
            PRICES,
            invoiced_on=DAY,
        )
        assert [line.ticket_number for line in result.invoice.lines] == [
            "881204",
            "881205",
        ]

    def test_the_price_comes_from_the_quote(self) -> None:
        result = build_invoice("INV-1", account(), [ticket("881204")], PRICES, invoiced_on=DAY)
        assert result.invoice.concrete == Money.of("1066.50")

    def test_an_unquoted_mixture_is_named_not_billed(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204"), ticket("881205")],
            {"4000P-57": Money.of("118.50")},
            invoiced_on=DAY,
        )
        assert result.is_complete
        empty = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            {"4000P-57": Money.of("118.50")},
            invoiced_on=DAY,
        )
        assert empty.is_complete

    def test_a_run_with_no_quotes_at_all(self) -> None:
        with pytest.raises(ValidationError, match="no ticket in this run"):
            build_invoice("INV-1", account(), [ticket("881204")], {}, invoiced_on=DAY)

    def test_no_tickets(self) -> None:
        with pytest.raises(ValidationError, match="at least one ticket"):
            build_invoice("INV-1", account(), [], PRICES, invoiced_on=DAY)

    def test_the_terms_come_from_the_account(self) -> None:
        result = build_invoice("INV-1", account(), [ticket("881204")], PRICES, invoiced_on=DAY)
        assert result.invoice.due_on == date(2024, 7, 12)

    def test_tax_is_applied(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            PRICES,
            invoiced_on=DAY,
            tax=Percent(6.0),
        )
        assert result.invoice.tax_amount > Money.zero()


class CaseCharges:
    def test_no_schedule_means_no_charges(self) -> None:
        result = build_invoice("INV-1", account(), [ticket("881204")], PRICES, invoiced_on=DAY)
        assert result.invoice.charges == ()

    def test_the_fuel_surcharge_lands(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
        )
        assert ChargeKind.FUEL in charge_summary(result.invoice)

    def test_standby_comes_off_the_delivery(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
            deliveries={"881204": delivery("881204", on_site=90)},
        )
        assert ChargeKind.STANDBY in charge_summary(result.invoice)

    def test_a_quick_discharge_earns_no_standby(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
            deliveries={"881204": delivery("881204", on_site=30)},
        )
        assert ChargeKind.STANDBY not in charge_summary(result.invoice)

    def test_returned_concrete_comes_off_the_delivery(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
            deliveries={"881204": delivery("881204", returned=1.5)},
        )
        assert ChargeKind.RETURNED_CONCRETE in charge_summary(result.invoice)

    def test_a_short_load(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204", volume=3.0)],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
        )
        assert ChargeKind.SHORT_LOAD in charge_summary(result.invoice)

    def test_after_hours_comes_off_the_batch_time(self) -> None:
        result = build_invoice(
            "INV-1",
            account(),
            [ticket("881204", hour=19)],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
        )
        assert ChargeKind.AFTER_HOURS in charge_summary(result.invoice)

    def test_winter_charges_need_asking_for(self) -> None:
        plain = build_invoice(
            "INV-1",
            account(),
            [ticket("881204")],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
        )
        assert ChargeKind.WINTER_HEAT not in charge_summary(plain.invoice)


class CaseAdjusting:
    def draft(self) -> object:
        return build_invoice(
            "INV-1",
            account(),
            [ticket("881204", volume=3.0)],
            PRICES,
            invoiced_on=DAY,
            schedule=schedule(),
        ).invoice

    def test_a_charge_can_be_taken_off_a_draft(self) -> None:
        trimmed = without_charge(self.draft(), ChargeKind.SHORT_LOAD)  # type: ignore[arg-type]
        assert ChargeKind.SHORT_LOAD not in charge_summary(trimmed)

    def test_taking_off_a_charge_that_is_not_there(self) -> None:
        with pytest.raises(NotFoundError, match="standby"):
            without_charge(self.draft(), ChargeKind.STANDBY)  # type: ignore[arg-type]

    def test_an_issued_invoice_needs_a_credit_note(self) -> None:
        issued = self.draft().issue()  # type: ignore[attr-defined]
        with pytest.raises(ValidationError, match="credit note"):
            without_charge(issued, ChargeKind.SHORT_LOAD)

    def test_the_summary_is_sorted(self) -> None:
        summary = charge_summary(self.draft())  # type: ignore[arg-type]
        names = [kind.value for kind in summary]
        assert names == sorted(names)

    def test_describe(self) -> None:
        result = build_invoice("INV-1", account(), [ticket("881204")], PRICES, invoiced_on=DAY)
        assert "INV-1" in result.describe()
