"""Money, which is not a float.

A cubic yard of concrete is priced to the cent and a day's production is a few
hundred yards, so the rounding error in binary floating point shows up in the
third decimal place of a daily total and in the first decimal place of a
monthly one. Every amount here is a Decimal, quantised to the currency's own
minor unit, and every arithmetic operation says what it does about rounding.

Splitting an amount is the operation worth being careful about. Dividing a
hundred and one cents three ways gives thirty four, thirty four and thirty
three, not three amounts that add up to a hundred and two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from slumpcone.errors import ValidationError

DEFAULT_CURRENCY = "USD"

# How many decimal places each currency this package knows carries.
_MINOR_UNITS: dict[str, int] = {"USD": 2, "CAD": 2, "EUR": 2, "GBP": 2, "JPY": 0}

_TEXT = re.compile(r"^\s*(?P<sign>[-+])?\s*[$£€]?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]+)?)\s*$")


def minor_units(currency: str) -> int:
    """How many decimal places a currency carries."""
    code = currency.strip().upper()
    if code not in _MINOR_UNITS:
        raise ValidationError(f"unknown currency {currency!r}", field="currency")
    return _MINOR_UNITS[code]


@dataclass(frozen=True, slots=True, eq=False, order=False)
class Money:
    """An amount in one currency, exact to that currency's minor unit."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        code = self.currency.strip().upper()
        places = minor_units(code)
        object.__setattr__(self, "currency", code)
        try:
            value = Decimal(self.amount)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError(f"{self.amount!r} is not an amount", field="amount") from exc
        if not value.is_finite():
            raise ValidationError("an amount has to be finite", field="amount")
        object.__setattr__(
            self, "amount", value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        )

    @classmethod
    def of(cls, amount: float | str | int, currency: str = DEFAULT_CURRENCY) -> Money:
        """Build from a number or a string, without going through binary float."""
        return cls(Decimal(str(amount)), currency)

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Money:
        """Nothing, in a currency, so it can still be added."""
        return cls(Decimal(0), currency)

    @classmethod
    def parse(cls, text: str, currency: str = DEFAULT_CURRENCY) -> Money:
        """Read ``"$1,234.56"`` or ``"-12.50"``."""
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as an amount", field="amount")
        digits = match.group("amount").replace(",", "")
        sign = -1 if match.group("sign") == "-" else 1
        return cls(Decimal(digits) * sign, currency)

    def _same_currency(self, other: Money, verb: str) -> None:
        if other.currency != self.currency:
            raise ValidationError(
                f"cannot {verb} {other.currency} and {self.currency}", field="currency"
            )

    def __add__(self, other: Money) -> Money:
        self._same_currency(other, "add")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other, "subtract")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: float | int | Decimal) -> Money:
        return Money(self.amount * Decimal(str(factor)), self.currency)

    __rmul__ = __mul__

    def __truediv__(self, divisor: float | int | Decimal) -> Money:
        value = Decimal(str(divisor))
        if value == 0:
            raise ValidationError("division by zero", field="amount")
        return Money(self.amount / value, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.currency == other.currency and self.amount == other.amount

    def __hash__(self) -> int:
        return hash((self.currency, self.amount))

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other, "order")
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._same_currency(other, "order")
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        return not self <= other

    def __ge__(self, other: Money) -> bool:
        return not self < other

    def __bool__(self) -> bool:
        return self.amount != 0

    def is_zero(self) -> bool:
        """True when there is nothing here."""
        return self.amount == 0

    def ratio_to(self, other: Money) -> float:
        """This amount divided by another, as a plain number."""
        self._same_currency(other, "compare")
        if other.amount == 0:
            raise ValidationError("division by a zero amount", field="amount")
        return float(self.amount / other.amount)

    def split(self, ways: int) -> tuple[Money, ...]:
        """Divide into ``ways`` parts that add back up to the original.

        The remainder goes to the earliest parts, a cent each, which is the
        convention every ledger uses and the only one where the parts total the
        whole.
        """
        if ways <= 0:
            raise ValidationError("cannot split into fewer than one part", field="ways")
        places = minor_units(self.currency)
        unit = Decimal(1).scaleb(-places)
        total_units = int((self.amount / unit).to_integral_value(rounding=ROUND_HALF_UP))
        base, remainder = divmod(abs(total_units), ways)
        sign = -1 if total_units < 0 else 1
        parts = [base + (1 if index < remainder else 0) for index in range(ways)]
        return tuple(Money(Decimal(part * sign) * unit, self.currency) for part in parts)

    def format(self, *, symbol: bool = True) -> str:
        """Print with a thousands separator and the currency's own places."""
        places = minor_units(self.currency)
        prefix = {"USD": "$", "CAD": "$", "EUR": "€", "GBP": "£"}.get(self.currency, "")
        body = f"{self.amount:,.{places}f}"
        if not symbol or not prefix:
            return f"{body} {self.currency}" if not symbol else body
        return (
            f"{prefix}{body}"
            if self.amount >= 0
            else f"-{prefix}{abs(self.amount):,.{places}f}"
        )

    def __str__(self) -> str:
        return self.format()

    def __repr__(self) -> str:
        return f"Money({str(self.amount)!r}, {self.currency!r})"


def total(amounts: list[Money], currency: str = DEFAULT_CURRENCY) -> Money:
    """Add up a list, which may be empty."""
    running = Money.zero(currency)
    for amount in amounts:
        running = running + amount
    return running
