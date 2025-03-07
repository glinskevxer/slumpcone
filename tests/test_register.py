from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.errors import NotFoundError
from slumpcone.register import COUNTED_TABLES, Register
from slumpcone.store.db import StoreError
from slumpcone.store.migrations import load_migrations
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import cement, design

DAY = date(2024, 6, 12)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


class CaseOpening:
    def test_in_memory(self, register: Register) -> None:
        assert register.path == ":memory:"
        assert register.materials.all() == ()

    def test_a_file_register_is_created_and_migrated(self, tmp_path: Path) -> None:
        target = tmp_path / "register.sqlite3"
        with Register.open(target) as register:
            assert register.health().is_current
        assert target.exists()

    def test_a_file_register_reopens(self, tmp_path: Path) -> None:
        target = tmp_path / "register.sqlite3"
        with Register.open(target) as register:
            register.materials.save(cement())
        with Register.open(target) as register:
            assert register.materials.get("CEM-I").code == "CEM-I"

    def test_the_database_is_exposed(self, register: Register) -> None:
        assert register.database.scalar("SELECT 1") == 1


class CaseRepositories:
    def test_every_repository_is_wired(self, register: Register) -> None:
        for name in (
            "materials",
            "plants",
            "mixes",
            "batches",
            "fresh",
            "strength",
            "deliveries",
            "projects",
            "orders",
            "inventory",
            "ingest",
            "prices",
            "audit",
            "hardened",
            "maturity",
        ):
            assert getattr(register, name) is not None

    def test_they_share_one_connection(self, register: Register) -> None:
        register.materials.save(cement())
        assert register.database.scalar("SELECT count(*) FROM material") == 1

    def test_a_missing_record_still_raises_from_the_repository(
        self, register: Register
    ) -> None:
        with pytest.raises(NotFoundError):
            register.materials.get("CEM-IX")


class CaseHealth:
    def test_a_fresh_register_is_current_and_empty(self, register: Register) -> None:
        health = register.health()
        assert health.is_current
        assert health.is_empty
        assert health.schema_version == len(load_migrations())
        assert health.expected_version == health.schema_version

    def test_every_counted_table_is_reported(self, register: Register) -> None:
        assert set(register.health().counts) == set(COUNTED_TABLES)

    def test_a_row_moves_the_count(self, register: Register) -> None:
        register.materials.save(cement())
        health = register.health()
        assert health.counts["material"] == 1
        assert health.total_rows == 1
        assert not health.is_empty

    def test_an_edited_migration_is_caught_by_the_health_check(
        self, register: Register
    ) -> None:
        register.database.execute(
            "UPDATE schema_migration SET checksum = 'deadbeef' WHERE version = 1"
        )
        with pytest.raises(StoreError, match="edited since"):
            register.health()

    def test_the_path_is_carried(self, tmp_path: Path) -> None:
        target = tmp_path / "register.sqlite3"
        with Register.open(target) as register:
            assert register.health().path == str(target)


class CaseDaySummary:
    def test_an_empty_day(self, register: Register) -> None:
        summary = register.day_summary(DAY)
        assert summary["tickets"] == 0
        assert summary["fresh tests"] == 0

    def test_a_ticket_shows_up(self, register: Register) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        register.batches.save(
            BatchTicket.from_plan(planned, "881204", datetime(2024, 6, 12, 7, 42))
        )
        assert register.day_summary(DAY)["tickets"] == 1

    def test_another_day_is_empty(self, register: Register) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        register.batches.save(
            BatchTicket.from_plan(planned, "881204", datetime(2024, 6, 12, 7, 42))
        )
        assert register.day_summary(date(2024, 6, 13))["tickets"] == 0


class CaseClosing:
    def test_the_context_manager_closes(self, tmp_path: Path) -> None:
        target = tmp_path / "register.sqlite3"
        register = Register.open(target)
        with register:
            register.materials.save(cement())
        with pytest.raises(Exception):  # noqa: B017, PT011
            register.database.scalar("SELECT 1")
