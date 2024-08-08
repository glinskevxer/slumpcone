"""The inventory ledger, which is a list of movements and not a level.

A silo carries a running level because the batch computer needs one number to
look at. The ledger is the record behind it, and the two are not the same thing:
the level is where the plant thinks it is, and the ledger is how it got there.

Keeping the movements means a reconciliation is a movement of its own rather
than an edit. When a silo is probed and reads eight thousand pounds light, that
eight thousand is a fact worth keeping. Typed over the top of the level it
disappears, and the plant loses the only evidence that something is leaking,
mis-weighing or being taken.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.units.quantity import Quantity


class MovementKind(Enum):
    """What kind of movement a ledger line records."""

    RECEIPT = "receipt"
    DRAWDOWN = "drawdown"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    WASTE = "waste"
    ADJUSTMENT = "adjustment"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> MovementKind:
        """Read a movement kind off a ledger export."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown movement kind {text!r}", field="kind")

    @property
    def adds(self) -> bool:
        """True when this kind puts material into the vessel."""
        return self in {MovementKind.RECEIPT, MovementKind.TRANSFER_IN}

    @property
    def removes(self) -> bool:
        """True when this kind takes material out."""
        return self in {
            MovementKind.DRAWDOWN,
            MovementKind.TRANSFER_OUT,
            MovementKind.WASTE,
        }

    @property
    def is_signed(self) -> bool:
        """True when the quantity carries its own sign.

        An adjustment does, because it can go either way. Everything else has a
        direction fixed by its kind and a negative quantity on one of those is
        a data error rather than a movement backwards.
        """
        return self is MovementKind.ADJUSTMENT


@dataclass(frozen=True, slots=True)
class Movement:
    """One line of the ledger."""

    plant_code: str
    silo_code: str
    material_code: str
    at: datetime
    kind: MovementKind
    quantity: Quantity
    reference: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        for label, field_name in (
            ("plant_code", "plant_code"),
            ("silo_code", "silo_code"),
            ("material_code", "material_code"),
        ):
            object.__setattr__(
                self, label, normalize_code(getattr(self, label), field=field_name)
            )
        if self.reference is not None:
            object.__setattr__(
                self, "reference", normalize_code(self.reference, field="reference")
            )
        if self.quantity.dimension.value != "mass":
            raise ValidationError("a movement quantity is a mass", field="quantity")
        if not self.kind.is_signed and self.quantity.value < 0.0:
            raise ValidationError(
                f"a {self.kind} cannot be negative; use an adjustment", field="quantity"
            )

    @property
    def signed(self) -> Quantity:
        """The quantity with the sign its kind implies."""
        if self.kind.removes:
            return -self.quantity
        return self.quantity

    def describe(self) -> str:
        """One line for a ledger listing."""
        reference = f"  {self.reference}" if self.reference else ""
        return (
            f"{self.at.date().isoformat()}  {self.silo_code}  {self.kind}  "
            f"{self.signed.format(0)}{reference}"
        )


class InventoryLedger:
    """Every movement across a plant's vessels."""

    def __init__(self, movements: Iterable[Movement] = ()) -> None:
        self._movements: list[Movement] = sorted(
            movements, key=lambda entry: (entry.at, entry.silo_code)
        )

    def __len__(self) -> int:
        return len(self._movements)

    def __iter__(self) -> Iterator[Movement]:
        return iter(self._movements)

    def record(self, movement: Movement) -> Movement:
        """Add a movement, keeping the ledger in time order."""
        self._movements.append(movement)
        self._movements.sort(key=lambda entry: (entry.at, entry.silo_code))
        return movement

    def movements_for(
        self, silo_code: str, *, until: datetime | None = None
    ) -> tuple[Movement, ...]:
        """Every movement on one vessel, oldest first."""
        key = normalize_code(silo_code, field="silo_code")
        return tuple(
            entry
            for entry in self._movements
            if entry.silo_code == key and (until is None or entry.at <= until)
        )

    def balance(self, silo_code: str, *, until: datetime | None = None) -> Quantity:
        """What the ledger says is in a vessel."""
        total = Quantity.zero("lb")
        for entry in self.movements_for(silo_code, until=until):
            total = total + entry.signed.to("lb")
        return total

    def usage(self, silo_code: str, start: datetime, end: datetime) -> Quantity:
        """How much came out of a vessel over a window."""
        total = Quantity.zero("lb")
        for entry in self.movements_for(silo_code, until=end):
            if entry.at >= start and entry.kind.removes:
                total = total + entry.quantity.to("lb")
        return total

    def reconcile(
        self, silo_code: str, measured: Quantity, at: datetime, *, reference: str | None = None
    ) -> Movement | None:
        """Record the difference between the ledger and a measured level.

        Returns ``None`` when the two already agree, so a plant that probes a
        silo every week does not accumulate a pile of zero adjustments.
        """
        if measured.dimension.value != "mass":
            raise ValidationError("a measured level is a mass", field="measured")
        history = self.movements_for(silo_code, until=at)
        if not history:
            raise ValidationError(
                f"no movements on {silo_code} to reconcile against", field="silo_code"
            )
        difference = measured.to("lb") - self.balance(silo_code, until=at)
        if difference.is_zero():
            return None
        template = history[-1]
        return self.record(
            Movement(
                template.plant_code,
                template.silo_code,
                template.material_code,
                at,
                MovementKind.ADJUSTMENT,
                difference,
                reference=reference,
                notes="reconciliation against a measured level",
            )
        )

    def silo_codes(self) -> tuple[str, ...]:
        """Every vessel the ledger has a movement for, sorted."""
        return tuple(sorted({entry.silo_code for entry in self._movements}))

    def adjustments(self, silo_code: str) -> tuple[Movement, ...]:
        """Every reconciliation on one vessel, oldest first."""
        return tuple(
            entry
            for entry in self.movements_for(silo_code)
            if entry.kind is MovementKind.ADJUSTMENT
        )
