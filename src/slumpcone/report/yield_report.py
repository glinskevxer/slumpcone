"""The yield report, which is the only check that the customer got a yard.

Everything else the register measures is about whether the concrete is any
good. This one is about whether there was enough of it, and it is the check
plants run least and get complained about most.

Two numbers per load. Relative yield says whether a cubic yard of ordered
concrete came to a cubic yard in the forms. Gravimetric air says how much of
the shortfall is air, which matters because the two failures have opposite
remedies: over-yielding on air is fixed at the admixture dispenser, and
under-yielding on weight is fixed at the scales.

When the gravimetric air and the pressure meter disagree by more than about a
percent, neither number is wrong. A specific gravity on file is.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from slumpcone.fresh.tests import FreshTest, FreshTestKind
from slumpcone.mixdesign.proportions import Proportions
from slumpcone.mixdesign.volumes import compute_volumes, gravimetric_air, relative_yield
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.rate import MassPerVolume

# How far the two air methods may disagree before a specific gravity is suspect.
AIR_METHOD_TOLERANCE = Percent(1.0)

# Relative yield outside this band is worth a note on the report.
YIELD_BAND = (0.98, 1.02)


@dataclass(frozen=True, slots=True)
class YieldRow:
    """One unit weight test turned into a yield reading."""

    ticket_number: str
    unit_weight: MassPerVolume
    relative_yield: float
    gravimetric_air: Percent
    measured_air: Percent | None = None

    @property
    def air_difference(self) -> Percent | None:
        """Gravimetric less pressure meter, when both were run."""
        if self.measured_air is None:
            return None
        return self.gravimetric_air - self.measured_air

    @property
    def air_methods_disagree(self) -> bool:
        """True when the two air readings are too far apart to both be right."""
        difference = self.air_difference
        return difference is not None and abs(difference).value > AIR_METHOD_TOLERANCE.value

    @property
    def is_short(self) -> bool:
        """True when the load yielded less than it was sold as."""
        return self.relative_yield < YIELD_BAND[0]

    @property
    def is_over(self) -> bool:
        """True when the load yielded more, which is concrete given away."""
        return self.relative_yield > YIELD_BAND[1]

    @property
    def note(self) -> str:
        """A short phrase for the report line."""
        notes: list[str] = []
        if self.is_short:
            notes.append("short")
        if self.is_over:
            notes.append("over")
        if self.air_methods_disagree:
            notes.append("air methods disagree")
        return ", ".join(notes) or "ok"


def yield_rows(
    tests: Sequence[FreshTest],
    proportions: Proportions,
    specific_gravities: Mapping[str, float],
) -> tuple[YieldRow, ...]:
    """Turn the unit weight tests in a set into yield readings.

    Air readings are matched to unit weight readings by ticket, because a load
    is tested once for both and the two arrive as separate records.
    """
    breakdown = compute_volumes(proportions, specific_gravities)
    air_by_ticket: dict[str, Percent] = {}
    for test in tests:
        if test.kind.is_air and test.air is not None:
            air_by_ticket.setdefault(test.ticket_number, test.air)
    rows: list[YieldRow] = []
    for test in tests:
        if test.kind is not FreshTestKind.UNIT_WEIGHT or test.unit_weight is None:
            continue
        # A zero density cannot reach here: the test record refuses one on the
        # way in, so there is no second guard for it.
        density = test.unit_weight
        rows.append(
            YieldRow(
                test.ticket_number,
                density,
                relative_yield(density, breakdown),
                gravimetric_air(density, breakdown),
                air_by_ticket.get(test.ticket_number),
            )
        )
    return tuple(sorted(rows, key=lambda row: row.ticket_number))


def render_yield(rows: Sequence[YieldRow]) -> str:
    """The per load table."""
    columns = (
        Column("ticket"),
        Column("unit weight", Align.RIGHT),
        Column("rel yield", Align.RIGHT),
        Column("air, gravimetric", Align.RIGHT),
        Column("air, meter", Align.RIGHT),
        Column("note"),
    )
    body = [
        [
            row.ticket_number,
            row.unit_weight.format(1),
            f"{row.relative_yield:.3f}",
            row.gravimetric_air.format(1),
            "-" if row.measured_air is None else row.measured_air.format(1),
            row.note,
        ]
        for row in rows
    ]
    return render_table(columns, body)


def yield_summary(rows: Sequence[YieldRow]) -> str:
    """The counts under the table."""
    if not rows:
        return render_pairs([("loads", 0)])
    average = sum(row.relative_yield for row in rows) / len(rows)
    return render_pairs(
        [
            ("loads", len(rows)),
            ("average relative yield", f"{average:.3f}"),
            ("short", sum(1 for row in rows if row.is_short)),
            ("over", sum(1 for row in rows if row.is_over)),
            ("air methods disagree", sum(1 for row in rows if row.air_methods_disagree)),
        ]
    )


def render_yield_report(
    mix_code: str,
    tests: Sequence[FreshTest],
    proportions: Proportions,
    specific_gravities: Mapping[str, float],
) -> str:
    """The whole yield report for one mixture."""
    rows = yield_rows(tests, proportions, specific_gravities)
    return "\n".join(
        [
            heading(f"Yield for {mix_code}"),
            render_yield(rows),
            "",
            yield_summary(rows),
        ]
    )
