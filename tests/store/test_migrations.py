from __future__ import annotations

from pathlib import Path

import pytest

from slumpcone.store.db import Database, StoreError
from slumpcone.store.migrations import (
    Migration,
    _read_from,
    applied,
    current_version,
    load_migrations,
    migrate,
    open_register,
    pending,
    verify,
)


@pytest.fixture()
def db() -> Database:
    return Database.in_memory()


class CaseMigrationRecord:
    def test_checksum_ignores_trailing_whitespace(self) -> None:
        one = Migration(1, "a", "CREATE TABLE t (a INTEGER);")
        two = Migration(1, "a", "CREATE TABLE t (a INTEGER);   \n")
        assert one.checksum == two.checksum

    def test_checksum_notices_a_real_edit(self) -> None:
        one = Migration(1, "a", "CREATE TABLE t (a INTEGER);")
        two = Migration(1, "a", "CREATE TABLE t (a TEXT);")
        assert one.checksum != two.checksum

    def test_filename_and_text(self) -> None:
        migration = Migration(7, "batches", "")
        assert migration.filename == "0007_batches.sql"
        assert str(migration) == "0007 batches"


class CaseLoading:
    def test_the_package_ships_migrations(self) -> None:
        migrations = load_migrations()
        assert migrations
        assert migrations[0].version == 1

    def test_versions_are_contiguous_from_one(self) -> None:
        versions = [m.version for m in load_migrations()]
        assert versions == list(range(1, len(versions) + 1))

    def test_a_badly_named_file_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "materials.sql").write_text("SELECT 1;")
        with pytest.raises(StoreError, match="not named"):
            _read_from(tmp_path)

    def test_a_gap_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "0001_a.sql").write_text("SELECT 1;")
        (tmp_path / "0003_b.sql").write_text("SELECT 1;")
        with pytest.raises(StoreError, match="gap"):
            _read_from(tmp_path)

    def test_an_empty_directory_loads_nothing(self, tmp_path: Path) -> None:
        assert _read_from(tmp_path) == ()


class CaseMigrating:
    def test_an_empty_register_is_at_version_zero(self, db: Database) -> None:
        assert current_version(db) == 0

    def test_migrate_applies_everything(self, db: Database) -> None:
        ran = migrate(db)
        assert len(ran) == len(load_migrations())
        assert current_version(db) == len(ran)
        assert pending(db) == ()

    def test_migrate_is_idempotent(self, db: Database) -> None:
        migrate(db)
        assert migrate(db) == ()

    def test_up_to_stops_where_it_is_told(self, db: Database) -> None:
        ran = migrate(db, up_to=1)
        assert [m.version for m in ran] == [1]
        assert current_version(db) == 1

    def test_the_applied_table_records_the_checksum(self, db: Database) -> None:
        migrate(db)
        record = applied(db)
        for migration in load_migrations():
            assert record[migration.version] == migration.checksum

    def test_the_first_migration_creates_the_material_tables(self, db: Database) -> None:
        migrate(db, up_to=1)
        assert "material" in db.table_names()
        assert "material_certificate" in db.table_names()
        assert "code" in db.column_names("material")


class CaseVerification:
    def test_a_clean_register_verifies(self, db: Database) -> None:
        migrate(db)
        verify(db)

    def test_an_edited_migration_is_caught(self, db: Database) -> None:
        migrate(db, up_to=1)
        db.execute("UPDATE schema_migration SET checksum = 'deadbeef' WHERE version = 1")
        with pytest.raises(StoreError, match="edited since"):
            verify(db)

    def test_a_migration_the_package_no_longer_ships_is_caught(self, db: Database) -> None:
        migrate(db)
        db.execute(
            "INSERT INTO schema_migration (version, name, checksum, applied_at) "
            "VALUES (999, 'ghost', 'x', datetime('now'))"
        )
        with pytest.raises(StoreError, match="does not ship it"):
            verify(db)

    def test_migrate_refuses_to_run_over_a_broken_register(self, db: Database) -> None:
        migrate(db, up_to=1)
        db.execute("UPDATE schema_migration SET checksum = 'deadbeef' WHERE version = 1")
        with pytest.raises(StoreError):
            migrate(db)


class CaseOpenRegister:
    def test_open_register_migrates_on_the_way_in(self, tmp_path: Path) -> None:
        with open_register(tmp_path / "register.sqlite3") as database:
            assert current_version(database) == len(load_migrations())
            assert "material" in database.table_names()
