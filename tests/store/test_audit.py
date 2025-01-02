from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.store.audit import GENESIS, AuditEvent, AuditLog
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate

START = datetime(2024, 6, 12, 7, 42)


@pytest.fixture()
def log() -> AuditLog:
    database = Database.in_memory()
    migrate(database)
    return AuditLog(database)


def stock(log: AuditLog) -> None:
    log.record("DK", "ticket written", "ticket 881204", "9 yd3", at=START)
    log.record(
        "DK", "ticket written", "ticket 881205", "7.5 yd3", at=START + timedelta(minutes=35)
    )
    log.record(
        "County engineer", "submittal approved", "SUB-118-03", at=START + timedelta(hours=2)
    )


class CaseEvent:
    def test_the_actor_is_normalised(self) -> None:
        event = AuditEvent(START, "  County   engineer ", "approved", "SUB-1")
        assert event.actor == "County engineer"

    def test_an_action_is_folded(self) -> None:
        assert AuditEvent(START, "DK", " Ticket Written ", "T").action == "ticket written"

    def test_an_event_needs_an_action(self) -> None:
        with pytest.raises(ValidationError, match="needs a action"):
            AuditEvent(START, "DK", "   ", "T")

    def test_an_event_needs_a_subject(self) -> None:
        with pytest.raises(ValidationError, match="needs a subject"):
            AuditEvent(START, "DK", "written", "  ")

    def test_describe(self) -> None:
        event = AuditEvent(START, "DK", "ticket written", "ticket 881204", "9 yd3")
        assert "2024-06-12 07:42:00" in event.describe()
        assert "ticket 881204" in event.describe()
        assert "9 yd3" in event.describe()

    def test_describe_without_a_detail(self) -> None:
        assert AuditEvent(START, "DK", "written", "T").describe().endswith("T")


class CaseRecording:
    def test_one_event(self, log: AuditLog) -> None:
        event = log.record("DK", "ticket written", "ticket 881204", at=START)
        assert event.identifier > 0
        assert event.digest != GENESIS
        assert log.count() == 1

    def test_the_first_event_chains_from_the_genesis(self, log: AuditLog) -> None:
        event = log.record("DK", "written", "T", at=START)
        assert event.digest == event.digest_after(GENESIS)

    def test_the_second_chains_from_the_first(self, log: AuditLog) -> None:
        first = log.record("DK", "written", "T", at=START)
        second = log.record("DK", "written", "U", at=START + timedelta(minutes=1))
        assert second.digest == second.digest_after(first.digest)

    def test_an_event_with_no_timestamp_gets_one(self, log: AuditLog) -> None:
        assert log.record("DK", "written", "T").at is not None


class CaseReading:
    def test_all_is_oldest_first(self, log: AuditLog) -> None:
        stock(log)
        assert [event.subject for event in log.all()][0] == "ticket 881204"

    def test_for_subject(self, log: AuditLog) -> None:
        stock(log)
        assert len(log.for_subject("ticket 881204")) == 1

    def test_by_actor(self, log: AuditLog) -> None:
        stock(log)
        assert len(log.by_actor("DK")) == 2
        assert len(log.by_actor("County engineer")) == 1

    def test_between(self, log: AuditLog) -> None:
        stock(log)
        assert len(log.between(date(2024, 6, 12), date(2024, 6, 12))) == 3
        assert log.between(date(2024, 7, 1), date(2024, 7, 31)) == ()

    def test_get(self, log: AuditLog) -> None:
        stock(log)
        assert log.get(1).subject == "ticket 881204"

    def test_an_unknown_event(self, log: AuditLog) -> None:
        with pytest.raises(NotFoundError, match="99"):
            log.get(99)


class CaseChain:
    def test_an_untouched_log_verifies(self, log: AuditLog) -> None:
        stock(log)
        assert log.is_intact
        assert log.verify() == ()

    def test_an_empty_log_verifies(self, log: AuditLog) -> None:
        assert log.is_intact

    def test_an_edited_row_is_caught(self, log: AuditLog) -> None:
        stock(log)
        log._db.execute("UPDATE audit_event SET detail = 'tampered' WHERE id = 1")
        assert not log.is_intact
        assert 1 in log.verify()

    def test_an_edit_in_the_middle_is_caught(self, log: AuditLog) -> None:
        stock(log)
        log._db.execute("UPDATE audit_event SET actor = 'somebody else' WHERE id = 2")
        assert 2 in log.verify()

    def test_a_deleted_row_breaks_the_chain(self, log: AuditLog) -> None:
        stock(log)
        log._db.execute("DELETE FROM audit_event WHERE id = 2")
        assert not log.is_intact

    def test_appending_after_a_break_does_not_repair_it(self, log: AuditLog) -> None:
        stock(log)
        log._db.execute("UPDATE audit_event SET detail = 'tampered' WHERE id = 1")
        log.record("DK", "written", "V")
        assert 1 in log.verify()
