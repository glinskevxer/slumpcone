"""The piece of paper that goes with the truck, and whether it is complete.

C94 clause 14.1 lists ten things every delivery ticket has to carry. It is a
short list and it is not negotiable: a ticket missing one of them is not a
delivery ticket, whatever else is printed on it. Clause 14.2 lists another six
that appear when the purchaser or the specification asks for them, and those are
the ones a plant discovers it needed after the pour.

So this does two jobs and keeps them apart.

It **renders** a ticket, in a layout a driver can read at the back of the truck
in the rain, which means wide labels, no columns that wrap, and the water
addition line at the bottom with room to write in.

It **checks** a ticket, and the check is not about formatting. It asks whether
each required item is actually on file, and it says which ones are not, because
a plant printing a thousand tickets a month with the truck number missing will
find out from an arbitrator rather than from the ticket.

One item cannot be checked here and it is deliberately not pretended otherwise.
Clause 14.1(10) is water added at the job by the receiver, with their initials.
That is written on the paper, after printing, by somebody standing in a puddle.
What can be checked is whether the printed ticket left a place for it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from slumpcone.batching.ticket import BatchTicket
from slumpcone.delivery.record import Delivery
from slumpcone.mixdesign.design import MixDesign
from slumpcone.plant.plant import Plant
from slumpcone.textout import heading, render_pairs

LABEL_WIDTH = 26


class Clause(Enum):
    """Which clause of C94 asks for an item."""

    REQUIRED = "14.1"
    ON_REQUEST = "14.2"

    def __str__(self) -> str:
        return self.value

    @property
    def is_required(self) -> bool:
        """Whether every ticket has to carry this, always."""
        return self is Clause.REQUIRED


@dataclass(frozen=True, slots=True)
class TicketItem:
    """One thing the standard asks a ticket to carry."""

    number: str
    clause: Clause
    label: str
    value: str

    @property
    def is_present(self) -> bool:
        """Whether the ticket actually carries it."""
        return bool(self.value.strip())

    def describe(self) -> str:
        """One line."""
        return f"C94 {self.clause}({self.number}) {self.label}: {self.value or 'MISSING'}"


@dataclass(frozen=True, slots=True)
class PrintedTicket:
    """A ticket laid out, with what the standard asks for checked off."""

    ticket_number: str
    items: tuple[TicketItem, ...]
    water_line: bool

    @property
    def required(self) -> tuple[TicketItem, ...]:
        """The clause 14.1 items."""
        return tuple(one for one in self.items if one.clause.is_required)

    @property
    def missing(self) -> tuple[TicketItem, ...]:
        """Required items the ticket does not carry."""
        return tuple(one for one in self.required if not one.is_present)

    @property
    def optional_present(self) -> tuple[TicketItem, ...]:
        """Clause 14.2 items that happen to be there."""
        return tuple(one for one in self.items if not one.clause.is_required and one.is_present)

    @property
    def is_complete(self) -> bool:
        """Whether this would stand as a delivery ticket."""
        return not self.missing and self.water_line

    def render(self) -> str:
        """The ticket, laid out for the back of the truck."""
        lines = [heading(f"Delivery ticket {self.ticket_number}")]
        lines.append(
            render_pairs(
                [(one.label, one.value or "-") for one in self.items if one.is_present],
                width=LABEL_WIDTH,
            )
        )
        if self.water_line:
            lines.extend(
                [
                    "",
                    "Water added at the job, C94 14.1(10). To be written in and",
                    "initialled by the receiver before discharge.",
                    "",
                    "  amount ______________  initials __________  time __________",
                ]
            )
        return "\n".join(lines)

    def describe(self) -> str:
        """One line."""
        if self.is_complete:
            return f"{self.ticket_number}: complete under C94 14.1"
        return f"{self.ticket_number}: {len(self.missing)} required item(s) missing"


def build_ticket(
    ticket: BatchTicket,
    plant: Plant,
    *,
    design: MixDesign | None = None,
    delivery: Delivery | None = None,
    water_line: bool = True,
) -> PrintedTicket:
    """Lay a ticket out and check it against C94 clause 14.

    The design and the delivery are optional because the ticket has to print
    without them: a load batched at five in the morning has no delivery record
    yet, and a printed ticket that waits for one is a truck standing on the yard.
    What their absence costs is the clause 14.2 items, and the check says so.
    """
    revolutions = (
        ""
        if delivery is None or delivery.revolutions_on_arrival is None
        else str(delivery.revolutions_on_arrival)
    )
    cement = ""
    if design is not None:
        cement = design.proportions.cement.format(0)
    admixtures = ""
    if design is not None and design.proportions.admixtures:
        admixtures = ", ".join(str(one) for one in design.proportions.admixtures)
    items = (
        TicketItem("1", Clause.REQUIRED, "plant", plant.name),
        TicketItem("2", Clause.REQUIRED, "ticket number", ticket.number),
        TicketItem("3", Clause.REQUIRED, "date", ticket.batched_at.date().isoformat()),
        TicketItem("4", Clause.REQUIRED, "truck", ticket.truck_code or ""),
        TicketItem("5", Clause.REQUIRED, "purchaser", ticket.purchaser or ""),
        TicketItem("6", Clause.REQUIRED, "job", ticket.project or ""),
        TicketItem(
            "7",
            Clause.REQUIRED,
            "class of concrete",
            f"{ticket.mix_code} rev {ticket.mix_revision}",
        ),
        TicketItem("8", Clause.REQUIRED, "volume", ticket.volume.format(2)),
        TicketItem(
            "9",
            Clause.REQUIRED,
            "loaded at",
            ticket.batched_at.isoformat(sep=" ", timespec="minutes"),
        ),
        TicketItem("10", Clause.REQUIRED, "water added at the job", "on the form"),
        TicketItem("a", Clause.ON_REQUEST, "revolution counter", revolutions),
        TicketItem("b", Clause.ON_REQUEST, "cement content", cement),
        TicketItem("c", Clause.ON_REQUEST, "admixtures", admixtures),
        TicketItem(
            "d",
            Clause.ON_REQUEST,
            "water held back",
            "" if ticket.water_held_back is None else ticket.water_held_back.format(0),
        ),
        TicketItem(
            "e",
            Clause.ON_REQUEST,
            "cumulative volume",
            "" if ticket.cumulative_volume is None else ticket.cumulative_volume.format(1),
        ),
    )
    return PrintedTicket(ticket.number, items, water_line)


def incomplete(printed: Sequence[PrintedTicket]) -> tuple[PrintedTicket, ...]:
    """The tickets that would not stand, most missing first."""
    return tuple(
        sorted(
            (one for one in printed if not one.is_complete),
            key=lambda one: (-len(one.missing), one.ticket_number),
        )
    )
