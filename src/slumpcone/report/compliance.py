"""The compliance calendar: everything that expires, in one list.

Five different things run out on five different clocks, and each of them is
kept in a different part of the register. Material certificates, scale
calibrations, the plant's own certification, mixer uniformity tests and mix
submittals. A plant manager does not think of those as five lists. They think
of it as "what stops me batching next month", and that is one list sorted by
date.

The list is built from the same objects the rules read, so nothing here can
disagree with the refusal a batch would get. Anything that computes an expiry
independently drifts from what actually blocks the plant, and then the calendar
is worse than not having one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum

from slumpcone.delivery.truck import Truck
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.certification import CertificateState
from slumpcone.plant.plant import Plant
from slumpcone.project.submittal import Submittal, SubmittalStatus
from slumpcone.textout import Align, Column, heading, render_pairs, render_table

# How far ahead the calendar looks by default.
HORIZON_DAYS = 45


class DueKind(Enum):
    """Which clock an item is on."""

    MATERIAL_CERTIFICATE = "material certificate"
    SCALE_CALIBRATION = "scale calibration"
    PLANT_CERTIFICATION = "plant certification"
    MIXER_UNIFORMITY = "mixer uniformity"
    MIX_SUBMITTAL = "mix submittal"

    def __str__(self) -> str:
        return self.value

    @property
    def blocks_batching(self) -> bool:
        """True when letting this lapse stops the plant rather than the paperwork."""
        return self is not DueKind.MIX_SUBMITTAL


@dataclass(frozen=True, slots=True)
class DueItem:
    """One thing with an expiry date on it."""

    kind: DueKind
    subject: str
    due_on: date
    detail: str = ""

    def days_remaining(self, on: date) -> int:
        """Days left, negative once it has lapsed."""
        return (self.due_on - on).days

    def is_overdue(self, on: date) -> bool:
        """True when the date has passed."""
        return self.due_on < on

    def describe(self, on: date) -> str:
        """One line for the calendar."""
        remaining = self.days_remaining(on)
        state = "overdue" if remaining < 0 else f"{remaining} d"
        return f"{self.due_on.isoformat()}  {self.kind}  {self.subject}  {state}"


def from_catalog(catalog: MaterialCatalog, on: date) -> tuple[DueItem, ...]:
    """Every material certificate that is current, with its expiry."""
    items: list[DueItem] = []
    for code in catalog.codes():
        for certificate in catalog.certificates_for(code):
            state = certificate.state(on)
            if state is CertificateState.NOT_YET_ISSUED:
                continue
            items.append(
                DueItem(
                    DueKind.MATERIAL_CERTIFICATE,
                    f"{code} {certificate.reference}",
                    certificate.expires,
                    str(certificate.kind),
                )
            )
    return tuple(items)


def from_plant(plant: Plant) -> tuple[DueItem, ...]:
    """The plant's own certification and every scale on it."""
    items: list[DueItem] = []
    if plant.certification_expires is not None:
        items.append(
            DueItem(
                DueKind.PLANT_CERTIFICATION,
                plant.code,
                plant.certification_expires,
                plant.name,
            )
        )
    for scale in plant.scales:
        items.append(
            DueItem(
                DueKind.SCALE_CALIBRATION,
                f"{plant.code} {scale.code}",
                scale.calibration_due,
                scale.name,
            )
        )
    return tuple(items)


def from_trucks(trucks: Sequence[Truck]) -> tuple[DueItem, ...]:
    """Every truck with a uniformity test on file."""
    items: list[DueItem] = []
    for truck in trucks:
        due = truck.uniformity_due
        if due is None:
            continue
        items.append(DueItem(DueKind.MIXER_UNIFORMITY, truck.code, due, truck.fleet or ""))
    return tuple(items)


def from_submittals(submittals: Sequence[Submittal]) -> tuple[DueItem, ...]:
    """Every approved submittal that has an expiry."""
    items: list[DueItem] = []
    for submittal in submittals:
        if submittal.status is not SubmittalStatus.APPROVED or submittal.expires_on is None:
            continue
        items.append(
            DueItem(
                DueKind.MIX_SUBMITTAL,
                f"{submittal.project_code}/{submittal.class_code} {submittal.mix_identity}",
                submittal.expires_on,
                submittal.reference,
            )
        )
    return tuple(items)


def calendar(
    items: Sequence[DueItem], on: date, *, horizon_days: int = HORIZON_DAYS
) -> tuple[DueItem, ...]:
    """Everything overdue or falling due inside the horizon, soonest first."""
    limit = on.toordinal() + horizon_days
    chosen = [item for item in items if item.due_on.toordinal() <= limit]
    return tuple(sorted(chosen, key=lambda item: (item.due_on, str(item.kind), item.subject)))


def overdue(items: Sequence[DueItem], on: date) -> tuple[DueItem, ...]:
    """Only the ones that have already lapsed."""
    return tuple(
        sorted(
            (item for item in items if item.is_overdue(on)),
            key=lambda item: (item.due_on, item.subject),
        )
    )


def blocking(items: Sequence[DueItem], on: date) -> tuple[DueItem, ...]:
    """Lapsed items that stop the plant rather than the paperwork."""
    return tuple(item for item in overdue(items, on) if item.kind.blocks_batching)


def render_calendar(items: Sequence[DueItem], on: date) -> str:
    """The calendar table."""
    columns = (
        Column("due"),
        Column("kind"),
        Column("subject"),
        Column("detail"),
        Column("days", Align.RIGHT),
    )
    rows = [
        [
            item.due_on.isoformat(),
            str(item.kind),
            item.subject,
            item.detail,
            item.days_remaining(on),
        ]
        for item in items
    ]
    return render_table(columns, rows)


def render_compliance_report(
    items: Sequence[DueItem], on: date, *, horizon_days: int = HORIZON_DAYS
) -> str:
    """The whole compliance calendar."""
    upcoming = calendar(items, on, horizon_days=horizon_days)
    lapsed = overdue(items, on)
    return "\n".join(
        [
            heading(f"Compliance calendar to {horizon_days} days"),
            render_pairs(
                [
                    ("as at", on.isoformat()),
                    ("items tracked", len(items)),
                    ("due or overdue", len(upcoming)),
                    ("blocking", len(blocking(items, on))),
                ]
            ),
            "",
            render_calendar(upcoming, on),
            "",
            heading("Overdue", underline="-"),
            render_calendar(lapsed, on),
        ]
    )
