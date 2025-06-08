"""Reading and writing technicians and their cards.

A card is keyed on its own number rather than on the person, because that is how
the certifying body issues it and because a number that turns up under two names
is a thing a plant wants to hear about rather than silently accept.

The expiry queries live here rather than in the caller for one reason: the query
that finds a lapsed card and the query that finds one about to lapse are one
character apart in SQL, and getting them the wrong way round produces a report
that looks fine and is exactly backwards.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.people.certification import (
    Certification,
    Grade,
    Technician,
    TestKind,
    uncovered,
    who_may_run,
)
from slumpcone.store.db import Database
from slumpcone.store.guards import require_one


class PeopleRepository:
    """Technicians and certifications, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, technician: Technician) -> Technician:
        """File a technician with every card they hold, replacing what is there."""
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO technician (code, name, employer) VALUES (?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET name = excluded.name, "
                "employer = excluded.employer",
                (technician.code, technician.name, technician.employer),
            )
            self._db.execute(
                "DELETE FROM certification WHERE technician_code = ?", (technician.code,)
            )
            for card in technician.certifications:
                self._db.execute(
                    "INSERT INTO certification (number, technician_code, grade, "
                    "issued_on, expires_on) VALUES (?, ?, ?, ?, ?)",
                    (
                        card.number,
                        technician.code,
                        card.grade.value,
                        card.issued_on.isoformat(),
                        card.expires_on.isoformat(),
                    ),
                )
        return technician

    def get(self, code: str) -> Technician:
        """One technician with their cards, oldest expiry first."""
        key = normalize_code(code, field="technician_code")
        row = require_one(
            self._db,
            "SELECT * FROM technician WHERE code = ?",
            (key,),
            "technician",
            key,
        )
        cards = self._db.query(
            "SELECT * FROM certification WHERE technician_code = ? ORDER BY expires_on",
            (key,),
        )
        return Technician(
            key,
            str(row["name"]),
            tuple(
                Certification(
                    Grade(str(card["grade"])),
                    str(card["number"]),
                    date.fromisoformat(str(card["issued_on"])),
                    date.fromisoformat(str(card["expires_on"])),
                )
                for card in cards
            ),
            str(row["employer"]),
        )

    def all(self) -> tuple[Technician, ...]:
        """Everybody on file, in code order."""
        rows = self._db.query("SELECT code FROM technician ORDER BY code")
        return tuple(self.get(str(row["code"])) for row in rows)

    def forget(self, code: str) -> None:
        """Drop a technician and their cards."""
        key = normalize_code(code, field="technician_code")
        cursor = self._db.execute("DELETE FROM technician WHERE code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("technician", key)

    def holder_of(self, number: str) -> Technician:
        """Whose card this is."""
        key = normalize_code(number, field="certification_number")
        row = require_one(
            self._db,
            "SELECT technician_code FROM certification WHERE number = ?",
            (key,),
            "certification",
            key,
        )
        return self.get(str(row["technician_code"]))

    def lapsed(self, on: date) -> tuple[tuple[str, Certification], ...]:
        """Every card that has run out, soonest lapsed last."""
        rows = self._db.query(
            "SELECT * FROM certification WHERE expires_on < ? ORDER BY expires_on",
            (on.isoformat(),),
        )
        return tuple(self._pairs(rows))

    def expiring(self, on: date, *, days: int = 60) -> tuple[tuple[str, Certification], ...]:
        """Every card that is still good and runs out inside a window.

        The boundary is inclusive at both ends: a card expiring today is still
        current and is still reported, because today is when somebody can do
        something about it.
        """
        rows = self._db.query(
            "SELECT * FROM certification WHERE expires_on >= ? AND expires_on <= ? "
            "ORDER BY expires_on",
            (on.isoformat(), (on + timedelta(days=days)).isoformat()),
        )
        return tuple(self._pairs(rows))

    def _pairs(self, rows: Sequence[sqlite3.Row]) -> list[tuple[str, Certification]]:
        """Rows as technician code and card."""
        return [
            (
                str(row["technician_code"]),
                Certification(
                    Grade(str(row["grade"])),
                    str(row["number"]),
                    date.fromisoformat(str(row["issued_on"])),
                    date.fromisoformat(str(row["expires_on"])),
                ),
            )
            for row in rows
        ]

    def may_run(self, kind: TestKind, on: date) -> tuple[Technician, ...]:
        """Everybody certified for one test today."""
        return who_may_run(self.all(), kind, on)

    def gaps(self, on: date, kinds: Iterable[TestKind] | None = None) -> tuple[TestKind, ...]:
        """The tests nobody on file may run today."""
        return uncovered(self.all(), list(kinds) if kinds is not None else list(TestKind), on)
