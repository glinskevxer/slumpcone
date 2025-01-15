"""Material coming in to the plant.

A receipt is a weight, a supplier ticket and the vessel it went into. Two
checks matter and both are refusals rather than warnings.

The first is that the vessel is assigned to the material on the ticket. Cement
delivered into the ash silo is not a filing error, it is a contaminated silo and
several hundred yards of concrete made from an unknown blend. It happens because
the driver reads the number on the outside of the silo and the numbers are not
always what the plant thinks they are.

The second is headroom. A silo that takes more than it holds does not overflow
tidily; it lifts the roof filter and coats the yard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.percent import Percent
from slumpcone.plant.silo import Silo
from slumpcone.units.checks import require_mass, require_positive
from slumpcone.units.quantity import Quantity


@dataclass(frozen=True, slots=True)
class Receipt:
    """One delivery of material into a plant vessel."""

    reference: str
    plant_code: str
    silo_code: str
    material_code: str
    received_at: datetime
    quantity: Quantity
    supplier: str | None = None
    supplier_ticket: str | None = None
    certificate_reference: str | None = None
    moisture: Percent | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        for label, field_name in (
            ("reference", "receipt_reference"),
            ("plant_code", "plant_code"),
            ("silo_code", "silo_code"),
            ("material_code", "material_code"),
        ):
            object.__setattr__(
                self, label, normalize_code(getattr(self, label), field=field_name)
            )
        if self.supplier is not None:
            object.__setattr__(
                self, "supplier", normalize_name(self.supplier, field="supplier")
            )
        for label in ("supplier_ticket", "certificate_reference"):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, normalize_code(value, field=label))
        require_mass(self.quantity, "a received quantity", field="quantity")
        require_positive(self.quantity, "a received quantity", field="quantity")
        if self.moisture is not None and not 0.0 <= self.moisture.value <= 20.0:
            raise ValidationError(
                f"a moisture of {self.moisture} on a receipt is a probe fault", field="moisture"
            )

    @property
    def has_paper(self) -> bool:
        """True when the load arrived with a certificate reference on it."""
        return self.certificate_reference is not None

    def describe(self) -> str:
        """One line for a receiving log."""
        who = f"  {self.supplier}" if self.supplier else ""
        return (
            f"{self.reference}  {self.received_at.date().isoformat()}  "
            f"{self.material_code} into {self.silo_code}  {self.quantity.format(0)}{who}"
        )


def check_receipt(receipt: Receipt, silo: Silo) -> tuple[str, ...]:
    """Everything wrong with putting ``receipt`` into ``silo``."""
    faults: list[str] = []
    if silo.code != receipt.silo_code:
        faults.append(f"{silo.code} is not the vessel on the receipt")
    if silo.material_code != receipt.material_code:
        faults.append(
            f"{silo.code} holds {silo.material_code} and the receipt is {receipt.material_code}"
        )
    if receipt.quantity > silo.headroom:
        faults.append(
            f"{silo.code} has {silo.headroom.format(0)} of headroom and the load is "
            f"{receipt.quantity.format(0)}"
        )
    if not receipt.has_paper:
        faults.append("no certificate reference on the receipt")
    return tuple(faults)


def apply_receipt(receipt: Receipt, silo: Silo) -> Silo:
    """Put a receipt into a vessel, refusing anything the checks object to.

    The missing-certificate finding is a note rather than a refusal. Material
    arrives ahead of its paper often enough that stopping the delivery would
    stop the plant, and the material is unusable until the certificate is filed
    anyway, which the catalogue already enforces.
    """
    faults = [fault for fault in check_receipt(receipt, silo) if "certificate" not in fault]
    if faults:
        raise RuleViolationError("RECEIPT_REFUSED", "; ".join(faults))
    return silo.receive(receipt.quantity)
