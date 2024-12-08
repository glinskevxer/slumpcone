"""What a mixture costs, and what changing it costs.

Materials are bought in the units they are delivered in and used in the units
the mix design is written in, and the two are never the same. Cement arrives by
the ton and is batched by the pound; admixture arrives by the drum and is
dispensed by the fluid ounce. The price list carries the unit it was quoted in
and the conversion happens here rather than in somebody's spreadsheet.

The number worth having is not the total. It is the cost per cubic yard broken
down by material, because that is what says whether the fly ash is paying for
itself and what a ten pound cement reduction is actually worth.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.identity import normalize_code
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.money import Money, total
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, render_pairs, render_table
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class MaterialPrice:
    """What one material costs, in the unit it is bought by."""

    material_code: str
    price: Money
    per: Quantity
    effective_from: date | None = None
    effective_to: date | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "material_code", normalize_code(self.material_code, field="material_code")
        )
        if self.per.value <= 0.0:
            raise ValidationError("a price is quoted per some positive amount", field="per")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValidationError("a price cannot end before it starts", field="effective_to")

    def covers(self, on: date) -> bool:
        """True when this price is the one in force on a day."""
        if self.effective_from is not None and on < self.effective_from:
            return False
        return not (self.effective_to is not None and on > self.effective_to)

    def cost_of(self, amount: Quantity) -> Money:
        """What ``amount`` of this material costs."""
        if amount.dimension is not self.per.dimension:
            raise ValidationError(
                f"{self.material_code} is priced per {self.per.unit} and the charge is "
                f"in {amount.unit}",
                field="amount",
            )
        return self.price * (amount.base_value / self.per.base_value)

    def describe(self) -> str:
        """One line for a price list."""
        window = ""
        if self.effective_from is not None:
            window = f"  from {self.effective_from.isoformat()}"
        return f"{self.material_code}  {self.price} per {self.per.format(0)}{window}"


class PriceList:
    """Every material's price, with the one in force on a day."""

    def __init__(self, prices: Iterable[MaterialPrice] = ()) -> None:
        self._prices: list[MaterialPrice] = list(prices)

    def __len__(self) -> int:
        return len(self._prices)

    def add(self, price: MaterialPrice) -> MaterialPrice:
        """Add a price. Several may cover one material over different windows."""
        self._prices.append(price)
        return price

    def for_material(self, material_code: str, on: date) -> MaterialPrice:
        """The price in force for one material on a day.

        The latest one that starts on or before the day wins, so a new price
        filed today does not silently reprice last month's production.
        """
        key = normalize_code(material_code, field="material_code")
        covering = [
            price for price in self._prices if price.material_code == key and price.covers(on)
        ]
        if not covering:
            raise NotFoundError("price for", key)
        return max(
            covering,
            key=lambda price: (
                price.effective_from or date.min,
                price.price.amount,
            ),
        )

    def codes(self) -> tuple[str, ...]:
        """Every material with a price on file, sorted."""
        return tuple(sorted({price.material_code for price in self._prices}))


@dataclass(frozen=True, slots=True)
class CostLine:
    """One material's contribution to the cost of a batch."""

    material_code: str
    amount: Quantity
    cost: Money

    def share_of(self, whole: Money) -> Percent:
        """This line as a share of a total."""
        if whole.is_zero():
            return Percent(0.0)
        return Percent.from_fraction(self.cost.ratio_to(whole))


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """What a batch costs, line by line."""

    volume: Quantity
    lines: tuple[CostLine, ...]
    missing: tuple[str, ...] = ()

    @property
    def total(self) -> Money:
        """Everything the batch cost."""
        return total([line.cost for line in self.lines])

    @property
    def per_unit(self) -> Money:
        """Cost per unit volume, which is the number anybody quotes."""
        if self.volume.is_zero():
            raise ValidationError("a batch of nothing has no unit cost", field="volume")
        return self.total / self.volume.value

    @property
    def is_complete(self) -> bool:
        """True when every material in the mixture had a price."""
        return not self.missing

    def line(self, material_code: str) -> CostLine:
        """One line by material code."""
        key = normalize_code(material_code, field="material_code")
        for entry in self.lines:
            if entry.material_code == key:
                return entry
        raise NotFoundError("cost line", key)

    def render(self) -> str:
        """The breakdown as a table."""
        columns = (
            Column("material"),
            Column("amount", Align.RIGHT),
            Column("cost", Align.RIGHT),
            Column("share", Align.RIGHT),
        )
        whole = self.total
        rows = [
            [
                line.material_code,
                line.amount.format(1),
                str(line.cost),
                line.share_of(whole).format(1),
            ]
            for line in self.lines
        ]
        return render_table(columns, rows)

    def describe(self) -> str:
        """The headline block."""
        pairs: list[tuple[str, object]] = [
            ("volume", self.volume.format(2)),
            ("total", str(self.total)),
            ("per unit", str(self.per_unit)),
        ]
        if self.missing:
            pairs.append(("no price for", ", ".join(self.missing)))
        return render_pairs(pairs)


def cost_of(
    proportions: Proportions, prices: PriceList, volume: Quantity, on: date
) -> CostBreakdown:
    """What one batch of a mixture costs at a day's prices.

    A material with no price is reported rather than assumed free, because a
    cost per yard that quietly leaves the cement out is worse than no cost per
    yard at all.
    """
    if volume.dimension.value != "volume":
        raise ValidationError("a batch size is a volume", field="volume")
    weights = proportions.batch_weights(volume)
    doses = proportions.admixture_charges(volume)
    lines: list[CostLine] = []
    missing: list[str] = []
    for charge in proportions.charges:
        amount = weights[charge.material_code]
        try:
            price = prices.for_material(charge.material_code, on)
        except NotFoundError:
            missing.append(charge.material_code)
            continue
        lines.append(CostLine(charge.material_code, amount, price.cost_of(amount)))
    for code, dose in sorted(doses.items()):
        try:
            price = prices.for_material(code, on)
        except NotFoundError:
            missing.append(code)
            continue
        lines.append(CostLine(code, dose, price.cost_of(dose)))
    return CostBreakdown(volume, tuple(lines), tuple(missing))


def margin(sale_price: Money, cost: Money) -> Percent:
    """Gross margin as a share of the sale price."""
    if sale_price.is_zero():
        raise ValidationError("nothing sold for nothing has no margin", field="sale_price")
    return Percent.from_fraction((sale_price - cost).ratio_to(sale_price))


def cheapest(breakdowns: Sequence[CostBreakdown]) -> CostBreakdown:
    """The lowest unit cost among several mixtures."""
    if not breakdowns:
        raise ValidationError("nothing to compare", field="breakdowns")
    return min(breakdowns, key=lambda entry: entry.per_unit.amount)
