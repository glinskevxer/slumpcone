from __future__ import annotations

import pytest

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.money import Money
from slumpcone.sales.charges import (
    AppliedCharge,
    ChargeBasis,
    ChargeKind,
    ChargeRule,
    ChargeSchedule,
    charges_total,
    share_of_load,
)
from slumpcone.units.quantity import Quantity

VALUE = Money.of("1066.50")


def schedule(**overrides: object) -> ChargeSchedule:
    rules = [
        ChargeRule(ChargeKind.SHORT_LOAD, Money.of("120.00")),
        ChargeRule(ChargeKind.STANDBY, Money.of("2.25")),
        ChargeRule(ChargeKind.AFTER_HOURS, Money.of("150.00")),
        ChargeRule(ChargeKind.WEEKEND, Money.of("200.00")),
        ChargeRule(ChargeKind.WINTER_HEAT, Money.of("6.00")),
        ChargeRule(ChargeKind.RETURNED_CONCRETE, Money.of("18.00")),
        ChargeRule(ChargeKind.FUEL, Money.of("3.5")),
    ]
    return ChargeSchedule(rules, **overrides)  # type: ignore[arg-type]


class CaseKinds:
    def test_parse(self) -> None:
        assert ChargeKind.parse("short load") is ChargeKind.SHORT_LOAD
        assert ChargeKind.parse("WINTER_HEAT") is ChargeKind.WINTER_HEAT

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="charge kind"):
            ChargeKind.parse("goodwill")

    def test_the_natural_bases(self) -> None:
        assert ChargeKind.SHORT_LOAD.natural_basis is ChargeBasis.PER_LOAD
        assert ChargeKind.STANDBY.natural_basis is ChargeBasis.PER_MINUTE
        assert ChargeKind.FUEL.natural_basis is ChargeBasis.PERCENT_OF_CONCRETE
        assert ChargeKind.WINTER_HEAT.natural_basis is ChargeBasis.PER_UNIT

    def test_every_kind_has_one(self) -> None:
        for kind in ChargeKind:
            assert isinstance(kind.natural_basis, ChargeBasis)

    def test_they_print_their_own_values(self) -> None:
        assert str(ChargeKind.AFTER_HOURS) == "after hours"
        assert str(ChargeBasis.PER_MINUTE) == "per minute"


class CaseRules:
    def test_the_basis_defaults_to_the_natural_one(self) -> None:
        assert ChargeRule(ChargeKind.STANDBY, Money.of("2.25")).reckoned_on is (
            ChargeBasis.PER_MINUTE
        )

    def test_a_basis_can_be_overridden(self) -> None:
        rule = ChargeRule(ChargeKind.SHORT_LOAD, Money.of("15.00"), ChargeBasis.PER_UNIT)
        assert rule.reckoned_on is ChargeBasis.PER_UNIT

    def test_a_negative_rate_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            ChargeRule(ChargeKind.FUEL, Money.of("-1.00"))

    def test_per_load_ignores_the_quantity(self) -> None:
        rule = ChargeRule(ChargeKind.SHORT_LOAD, Money.of("120.00"))
        assert rule.apply(1.0, VALUE) == Money.of("120.00")
        assert rule.apply(4.0, VALUE) == Money.of("120.00")

    def test_per_load_with_nothing_charges_nothing(self) -> None:
        rule = ChargeRule(ChargeKind.SHORT_LOAD, Money.of("120.00"))
        assert rule.apply(0.0, VALUE).is_zero()

    def test_per_minute_multiplies(self) -> None:
        rule = ChargeRule(ChargeKind.STANDBY, Money.of("2.25"))
        assert rule.apply(20.0, VALUE) == Money.of("45.00")

    def test_a_percentage_is_of_the_concrete(self) -> None:
        rule = ChargeRule(ChargeKind.FUEL, Money.of("3.5"))
        assert rule.apply(1.0, Money.of("1000.00")) == Money.of("35.00")

    def test_a_negative_quantity_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            ChargeRule(ChargeKind.STANDBY, Money.of("2.25")).apply(-1.0, VALUE)

    def test_describe(self) -> None:
        assert "per minute" in ChargeRule(ChargeKind.STANDBY, Money.of("2.25")).describe()
        assert "% of the concrete" in ChargeRule(ChargeKind.FUEL, Money.of("3.5")).describe()


class CaseSchedule:
    def test_length_and_kinds(self) -> None:
        assert len(schedule()) == 7
        assert ChargeKind.STANDBY in schedule().kinds()

    def test_add_replaces(self) -> None:
        built = schedule()
        built.add(ChargeRule(ChargeKind.FUEL, Money.of("5.0")))
        assert built.rule(ChargeKind.FUEL).rate == Money.of("5.00")
        assert len(built) == 7

    def test_a_missing_rule(self) -> None:
        with pytest.raises(NotFoundError, match="washout"):
            schedule().rule(ChargeKind.WASHOUT)

    def test_has(self) -> None:
        assert schedule().has(ChargeKind.FUEL)
        assert not schedule().has(ChargeKind.WASHOUT)

    def test_a_bad_threshold(self) -> None:
        with pytest.raises(ValidationError, match="threshold is a volume"):
            ChargeSchedule((), small_load_below=Quantity(5, "lb"))

    def test_a_negative_allowance(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            ChargeSchedule((), standby_grace_minutes=-1.0)


class CaseAllowance:
    def test_the_allowance_grows_with_the_load(self) -> None:
        built = schedule()
        assert built.unloading_allowance(Quantity(9, "yd3")) == pytest.approx(50.0)
        assert built.unloading_allowance(Quantity(3, "yd3")) == pytest.approx(20.0)

    def test_inside_the_allowance_is_no_standby(self) -> None:
        assert schedule().standby_minutes(Quantity(9, "yd3"), 40.0) == pytest.approx(0.0)

    def test_past_it_is_charged(self) -> None:
        assert schedule().standby_minutes(Quantity(9, "yd3"), 70.0) == pytest.approx(20.0)

    def test_negative_time_on_site(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            schedule().standby_minutes(Quantity(9, "yd3"), -1.0)


class CaseCharges:
    def test_a_plain_full_load_carries_only_fuel(self) -> None:
        applied = schedule().charges_for(Quantity(9, "yd3"), VALUE)
        assert [charge.kind for charge in applied] == [ChargeKind.FUEL]

    def test_a_short_load(self) -> None:
        applied = schedule().charges_for(Quantity(3, "yd3"), VALUE)
        kinds = [charge.kind for charge in applied]
        assert ChargeKind.SHORT_LOAD in kinds
        assert "under 5.0 yd3" in applied[0].reason

    def test_standby(self) -> None:
        applied = schedule().charges_for(Quantity(9, "yd3"), VALUE, on_site_minutes=70.0)
        standby = next(c for c in applied if c.kind is ChargeKind.STANDBY)
        assert standby.amount == Money.of("45.00")
        assert "past a 50 minute allowance" in standby.reason

    def test_no_standby_inside_the_allowance(self) -> None:
        applied = schedule().charges_for(Quantity(9, "yd3"), VALUE, on_site_minutes=40.0)
        assert all(charge.kind is not ChargeKind.STANDBY for charge in applied)

    def test_after_hours_and_weekend(self) -> None:
        applied = schedule().charges_for(
            Quantity(9, "yd3"), VALUE, after_hours=True, weekend=True
        )
        kinds = [charge.kind for charge in applied]
        assert ChargeKind.AFTER_HOURS in kinds
        assert ChargeKind.WEEKEND in kinds

    def test_winter_charges_are_per_unit(self) -> None:
        applied = schedule().charges_for(Quantity(9, "yd3"), VALUE, winter=True)
        heat = next(c for c in applied if c.kind is ChargeKind.WINTER_HEAT)
        assert heat.amount == Money.of("54.00")

    def test_returned_concrete(self) -> None:
        applied = schedule().charges_for(
            Quantity(9, "yd3"), VALUE, returned=Quantity(1.5, "yd3")
        )
        returned = next(c for c in applied if c.kind is ChargeKind.RETURNED_CONCRETE)
        assert returned.amount == Money.of("27.00")
        assert "1.50 yd3 came back" in returned.reason

    def test_nothing_returned_charges_nothing(self) -> None:
        applied = schedule().charges_for(Quantity(9, "yd3"), VALUE, returned=Quantity(0, "yd3"))
        assert all(charge.kind is not ChargeKind.RETURNED_CONCRETE for charge in applied)

    def test_a_rule_the_schedule_does_not_carry_is_skipped(self) -> None:
        thin = ChargeSchedule([ChargeRule(ChargeKind.FUEL, Money.of("3.5"))])
        applied = thin.charges_for(Quantity(2, "yd3"), VALUE, on_site_minutes=200.0)
        assert [charge.kind for charge in applied] == [ChargeKind.FUEL]

    def test_a_bad_load_size(self) -> None:
        with pytest.raises(ValidationError, match="load size is a volume"):
            schedule().charges_for(Quantity(9, "lb"), VALUE)


class CaseTotals:
    def test_the_total(self) -> None:
        applied = schedule().charges_for(Quantity(3, "yd3"), Money.of("355.50"))
        assert charges_total(applied) > Money.of("120.00")

    def test_an_empty_total(self) -> None:
        assert charges_total([]).is_zero()

    def test_the_share_of_the_load(self) -> None:
        applied = schedule().charges_for(Quantity(3, "yd3"), Money.of("355.50"))
        assert share_of_load(applied, Money.of("355.50")).value > 30.0

    def test_a_share_of_nothing(self) -> None:
        assert share_of_load([], Money.zero()).value == pytest.approx(0.0)

    def test_describe(self) -> None:
        charge = AppliedCharge(ChargeKind.STANDBY, 20.0, Money.of("45.00"), "20 minutes")
        assert "standby" in charge.describe()
        assert "(20 minutes)" in charge.describe()

    def test_describe_without_a_reason(self) -> None:
        charge = AppliedCharge(ChargeKind.FUEL, 1.0, Money.of("35.00"))
        assert charge.describe().endswith("$35.00")
