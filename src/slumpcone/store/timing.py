"""Measuring the queries the reports run, and whether they use an index.

A register grows one plant day at a time and nothing goes slowly until suddenly
everything does. The failure is always the same shape: a query that reads every
row of a table, which is instant on a thousand rows and is not on two million.

So the useful check is not how long a query took on this machine today. It is
whether SQLite planned to scan a table, which is a property of the query and the
schema rather than of the hardware, and which will still be true on the plant's
own computer.

``EXPLAIN QUERY PLAN`` answers that in one word. A plan line that says SEARCH is
using an index. One that says SCAN is reading the table. A scan of a small
lookup table is fine and a scan of the ticket table is a bug waiting for a busy
year, so the probe carries which tables it is allowed to scan rather than
failing on any scan at all.

The timings are here too, because they are cheap to take at the same time and
because a plan can be right while the query is still doing too much work. They
are reported and never asserted on: a timing test that passes on a laptop and
fails in CI teaches a team to ignore the suite.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from slumpcone.store.db import Database


@dataclass(frozen=True, slots=True)
class Probe:
    """One query worth watching, and what it is allowed to do."""

    name: str
    sql: str
    parameters: tuple[Any, ...] = ()
    may_scan: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class PlanReading:
    """What SQLite said it would do, and how long it took."""

    name: str
    milliseconds: float
    rows: int
    scanned: tuple[str, ...]
    searched: tuple[str, ...]
    allowed_scans: frozenset[str] = field(default_factory=frozenset)

    @property
    def unexpected_scans(self) -> tuple[str, ...]:
        """Tables read whole that the probe did not say could be."""
        return tuple(one for one in self.scanned if one not in self.allowed_scans)

    @property
    def is_clean(self) -> bool:
        """Whether nothing was read whole that should not have been."""
        return not self.unexpected_scans

    def describe(self) -> str:
        """One line."""
        verdict = "ok" if self.is_clean else f"scans {', '.join(self.unexpected_scans)}"
        return f"{self.name}: {self.milliseconds:.2f} ms, {self.rows} row(s), {verdict}"


def _tables_in(plan: Sequence[Any], word: str) -> tuple[str, ...]:
    """The tables a plan says it will read one way.

    The plan text is not a stable interface, which is why this reads only the
    two leading words of each step rather than trying to parse it.
    """
    found: list[str] = []
    for step in plan:
        detail = str(step["detail"])
        parts = detail.split()
        if len(parts) >= 2 and parts[0] == word:
            table = parts[1]
            if table not in found:
                found.append(table)
    return tuple(found)


def run_probe(database: Database, probe: Probe) -> PlanReading:
    """Explain a query, then run it, and report both."""
    plan = database.query(f"EXPLAIN QUERY PLAN {probe.sql}", probe.parameters)
    started = time.perf_counter()
    rows = database.query(probe.sql, probe.parameters)
    elapsed = (time.perf_counter() - started) * 1000.0
    return PlanReading(
        probe.name,
        elapsed,
        len(rows),
        _tables_in(plan, "SCAN"),
        _tables_in(plan, "SEARCH"),
        probe.may_scan,
    )


# The queries the reports lean on. Parameters are chosen to match nothing in
# particular: the plan is what matters and it does not depend on the values.
PROBES: tuple[Probe, ...] = (
    Probe(
        "tickets in a window",
        "SELECT * FROM batch_ticket WHERE batched_at >= ? AND batched_at < ? "
        "ORDER BY batched_at",
        ("2024-06-12", "2024-06-13"),
    ),
    Probe(
        "tickets on one job",
        "SELECT * FROM batch_ticket WHERE project = ? ORDER BY batched_at",
        ("Route 9 shoulder",),
    ),
    Probe(
        "fresh tests for one load",
        "SELECT * FROM fresh_test WHERE ticket_number = ? ORDER BY taken_at",
        ("881204",),
    ),
    Probe(
        "specimens for one load",
        "SELECT * FROM specimen WHERE ticket_number = ?",
        ("881204",),
    ),
    Probe(
        # break_result is keyed on the specimen, so this searches the primary
        # key rather than an index of its own. Watched anyway, because the day
        # somebody adds a second break per specimen the key changes and this is
        # where it shows.
        "breaks for one specimen",
        "SELECT * FROM break_result WHERE specimen_code = ?",
        ("C-S-4471-A",),
    ),
    Probe(
        "deliveries for one truck",
        "SELECT * FROM delivery WHERE truck_code = ? ORDER BY batched_at",
        ("TR-114",),
    ),
    Probe(
        "invoices for one account",
        "SELECT * FROM invoice WHERE account_code = ? ORDER BY invoiced_on",
        ("ASH-01",),
    ),
    Probe(
        "unbilled tickets",
        "SELECT t.number FROM batch_ticket t LEFT JOIN invoice_line l "
        "ON l.ticket_number = t.number WHERE l.ticket_number IS NULL "
        "AND t.batched_at >= ? AND t.batched_at < ?",
        ("2024-06-12", "2024-06-13"),
    ),
    Probe(
        "certificates by expiry",
        "SELECT * FROM material_certificate WHERE expires <= ? ORDER BY expires",
        ("2024-12-31",),
    ),
    Probe(
        "cards by expiry",
        "SELECT * FROM certification WHERE expires_on <= ? ORDER BY expires_on",
        ("2024-12-31",),
    ),
)


def run_all(database: Database, probes: Sequence[Probe] = PROBES) -> tuple[PlanReading, ...]:
    """Run every probe."""
    return tuple(run_probe(database, probe) for probe in probes)


def unclean(readings: Sequence[PlanReading]) -> tuple[PlanReading, ...]:
    """The readings that scan something they should not."""
    return tuple(one for one in readings if not one.is_clean)
