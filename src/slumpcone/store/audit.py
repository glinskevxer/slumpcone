"""The audit log, which is append only and chained.

An inspector asking who changed a mix design in March is asking a question the
domain tables cannot answer: they hold what a record is now, not what happened
to it. The log holds the second, and it is worth nothing unless it can be shown
not to have been edited, so every entry carries a digest over its own content
and the digest of the entry before it.

That chain does not stop anybody with write access to the file from rewriting
the whole log. It stops somebody quietly changing one row in the middle, which
is the failure that actually happens: a correction made directly in the
database because the command line refused it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.identity import normalize_name
from slumpcone.store.db import Database
from slumpcone.store.rows import day_range

GENESIS = "0" * 64


def _digest(
    at: datetime, actor: str, action: str, subject: str, detail: str, previous: str
) -> str:
    payload = "".join([at.isoformat(), actor, action, subject, detail, previous])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One thing that happened."""

    at: datetime
    actor: str
    action: str
    subject: str
    detail: str = ""
    digest: str = ""
    identifier: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor", normalize_name(self.actor, field="actor"))
        for name in ("action", "subject"):
            value = getattr(self, name)
            if not str(value).strip():
                raise ValidationError(f"an event needs a {name}", field=name)
        object.__setattr__(self, "action", str(self.action).strip().lower())
        object.__setattr__(self, "subject", str(self.subject).strip())

    def digest_after(self, previous: str) -> str:
        """What this event's digest should be, given the one before it."""
        return _digest(self.at, self.actor, self.action, self.subject, self.detail, previous)

    def describe(self) -> str:
        """One line for a log listing."""
        tail = f"  {self.detail}" if self.detail else ""
        return (
            f"{self.at.isoformat(sep=' ', timespec='seconds')}  {self.actor}  "
            f"{self.action}  {self.subject}{tail}"
        )


class AuditLog:
    """The log, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def _last_digest(self) -> str:
        row = self._db.query_one("SELECT digest FROM audit_event ORDER BY id DESC LIMIT 1")
        return GENESIS if row is None else str(row["digest"])

    def record(
        self,
        actor: str,
        action: str,
        subject: str,
        detail: str = "",
        *,
        at: datetime | None = None,
    ) -> AuditEvent:
        """Append one event, chained to the one before it."""
        moment = at or datetime.now()
        event = AuditEvent(moment, actor, action, subject, detail)
        digest = event.digest_after(self._last_digest())
        cursor = self._db.execute(
            "INSERT INTO audit_event (at, actor, action, subject, detail, digest) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                moment.isoformat(),
                event.actor,
                event.action,
                event.subject,
                event.detail,
                digest,
            ),
        )
        return AuditEvent(
            moment,
            event.actor,
            event.action,
            event.subject,
            event.detail,
            digest,
            int(cursor.lastrowid or 0),
        )

    def _from_row(self, row: object) -> AuditEvent:
        mapping = dict(row)  # type: ignore[call-overload]
        return AuditEvent(
            datetime.fromisoformat(str(mapping["at"])),
            str(mapping["actor"]),
            str(mapping["action"]),
            str(mapping["subject"]),
            str(mapping["detail"]),
            str(mapping["digest"]),
            int(mapping["id"]),
        )

    def all(self) -> tuple[AuditEvent, ...]:
        """Every event, oldest first."""
        rows = self._db.query("SELECT * FROM audit_event ORDER BY id")
        return tuple(self._from_row(row) for row in rows)

    def for_subject(self, subject: str) -> tuple[AuditEvent, ...]:
        """Everything that happened to one record."""
        rows = self._db.query(
            "SELECT * FROM audit_event WHERE subject = ? ORDER BY id", (subject.strip(),)
        )
        return tuple(self._from_row(row) for row in rows)

    def by_actor(self, actor: str) -> tuple[AuditEvent, ...]:
        """Everything one person did."""
        rows = self._db.query(
            "SELECT * FROM audit_event WHERE actor = ? ORDER BY id",
            (normalize_name(actor, field="actor"),),
        )
        return tuple(self._from_row(row) for row in rows)

    def between(self, start: date, end: date) -> tuple[AuditEvent, ...]:
        """Everything that happened in a window."""
        rows = self._db.query(
            "SELECT * FROM audit_event WHERE at >= ? AND at < ? ORDER BY id",
            day_range(start, end),
        )
        return tuple(self._from_row(row) for row in rows)

    def count(self) -> int:
        """How many events are on file."""
        return int(self._db.scalar("SELECT count(*) FROM audit_event") or 0)

    def get(self, identifier: int) -> AuditEvent:
        """One event by its number."""
        row = self._db.query_one("SELECT * FROM audit_event WHERE id = ?", (identifier,))
        if row is None:
            raise NotFoundError("audit event", str(identifier))
        return self._from_row(row)

    def verify(self) -> tuple[int, ...]:
        """The numbers of any events whose digest does not match the chain.

        An empty result means every entry follows from the one before it. A
        non-empty one names the first entry that does not, and everything after
        it, because a break in the chain invalidates the rest.
        """
        broken: list[int] = []
        previous = GENESIS
        for event in self.all():
            expected = event.digest_after(previous)
            if expected != event.digest:
                broken.append(event.identifier)
            previous = event.digest
        return tuple(broken)

    @property
    def is_intact(self) -> bool:
        """True when the whole chain verifies."""
        return not self.verify()
