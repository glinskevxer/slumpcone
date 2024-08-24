"""Keeping the ingest history.

Two things are worth keeping and one is not. The content hashes have to be
kept, because they are what makes a re-run cheap and safe. The quarantined rows
have to be kept, because somebody has to fix them and they need the line
numbers and the reasons in front of them.

The accepted rows are not kept here. They have already been turned into
tickets, breaks or receipts by the caller, and holding a second copy of them in
an ingest table means two records of the same fact that can disagree.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.ingest.result import IngestResult, Quarantined
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range


class IngestRepository:
    """Ingest runs, digests and quarantine, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def record(self, result: IngestResult) -> int:
        """Write a run and everything it produced, returning the run id."""
        run_at = result.run_at or datetime.now()
        with self._db.transaction():
            cursor = self._db.execute(
                "INSERT INTO ingest_run (profile_code, source_name, run_at, accepted_count, "
                "quarantined_count, duplicate_count, unmapped_columns) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result.profile_code,
                    result.source_name,
                    run_at.isoformat(),
                    len(result.accepted),
                    len(result.quarantined),
                    len(result.duplicates),
                    ",".join(result.unmapped_columns),
                ),
            )
            run_id = int(cursor.lastrowid or 0)
            for row in result.accepted:
                self._db.execute(
                    "INSERT INTO ingest_digest (digest, profile_code, run_id, line_number) "
                    "VALUES (?, ?, ?, ?)",
                    (row.digest, result.profile_code, run_id, row.line_number),
                )
            for held in result.quarantined:
                self._db.execute(
                    "INSERT INTO ingest_quarantine (run_id, line_number, reasons, values_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        run_id,
                        held.line_number,
                        " | ".join(held.reasons),
                        json.dumps(held.values, sort_keys=True),
                    ),
                )
        return run_id

    def known_digests(self, profile_code: str) -> frozenset[str]:
        """Every content hash already accepted under one profile."""
        key = normalize_code(profile_code, field="profile_code")
        rows = self._db.query("SELECT digest FROM ingest_digest WHERE profile_code = ?", (key,))
        return frozenset(str(row["digest"]) for row in rows)

    def run_count(self) -> int:
        """How many runs are on file."""
        return int(self._db.scalar("SELECT count(*) FROM ingest_run") or 0)

    def runs_for(self, profile_code: str) -> tuple[dict[str, object], ...]:
        """Every run under one profile, newest first."""
        key = normalize_code(profile_code, field="profile_code")
        rows = self._db.query(
            "SELECT * FROM ingest_run WHERE profile_code = ? ORDER BY run_at DESC, id DESC",
            (key,),
        )
        return tuple(dict(row) for row in rows)

    def runs_between(self, start: date, end: date) -> tuple[dict[str, object], ...]:
        """Every run in a window, oldest first."""
        rows = self._db.query(
            "SELECT * FROM ingest_run WHERE run_at >= ? AND run_at < ? ORDER BY run_at, id",
            day_range(start, end),
        )
        return tuple(dict(row) for row in rows)

    def quarantine_for(self, run_id: int) -> tuple[Quarantined, ...]:
        """The rows one run refused, in line order."""
        if self._db.query_one("SELECT 1 FROM ingest_run WHERE id = ?", (run_id,)) is None:
            raise NotFoundError("ingest run", str(run_id))
        rows = self._db.query(
            "SELECT * FROM ingest_quarantine WHERE run_id = ? ORDER BY line_number",
            (run_id,),
        )
        return tuple(
            Quarantined(
                int(row["line_number"]),
                tuple(str(row["reasons"]).split(" | ")) if row["reasons"] else (),
                json.loads(str(row["values_json"])),
            )
            for row in rows
        )

    def open_quarantine(self, profile_code: str) -> tuple[tuple[int, Quarantined], ...]:
        """Every quarantined row under one profile, with the run it came from."""
        key = normalize_code(profile_code, field="profile_code")
        rows = self._db.query(
            "SELECT q.* FROM ingest_quarantine q JOIN ingest_run r ON r.id = q.run_id "
            "WHERE r.profile_code = ? ORDER BY r.run_at, q.line_number",
            (key,),
        )
        return tuple(
            (
                int(row["run_id"]),
                Quarantined(
                    int(row["line_number"]),
                    tuple(str(row["reasons"]).split(" | ")) if row["reasons"] else (),
                    json.loads(str(row["values_json"])),
                ),
            )
            for row in rows
        )

    def forget_run(self, run_id: int) -> None:
        """Remove a run, its digests and its quarantine.

        Used when a file was loaded through the wrong profile: the digests have
        to go or the corrected load looks like a duplicate of the wrong one.
        """
        cursor = self._db.execute("DELETE FROM ingest_run WHERE id = ?", (run_id,))
        if cursor.rowcount == 0:
            raise NotFoundError("ingest run", str(run_id))
