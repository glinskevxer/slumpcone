from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from slumpcone.errors import ConflictError
from slumpcone.store.db import Database, StoreError


@pytest.fixture()
def db() -> Database:
    database = Database.in_memory()
    database.execute_script(
        """
        CREATE TABLE parent (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE);
        CREATE TABLE child (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER NOT NULL REFERENCES parent(id)
        );
        """
    )
    return database


class CaseOpening:
    def test_in_memory(self) -> None:
        with Database.in_memory() as database:
            assert database.scalar("SELECT 1") == 1

    def test_open_creates_the_parent_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "register.sqlite3"
        with Database.open(target) as database:
            database.execute("CREATE TABLE t (a INTEGER)")
        assert target.exists()

    def test_a_file_register_persists(self, tmp_path: Path) -> None:
        target = tmp_path / "register.sqlite3"
        with Database.open(target) as database:
            database.execute("CREATE TABLE t (a INTEGER)")
            database.execute("INSERT INTO t VALUES (7)")
        with Database.open(target) as database:
            assert database.scalar("SELECT a FROM t") == 7

    def test_the_connection_is_exposed_for_the_migration_runner(self) -> None:
        with Database.in_memory() as database:
            assert isinstance(database.connection, sqlite3.Connection)


class CasePragmas:
    def test_foreign_keys_are_on(self, db: Database) -> None:
        assert db.scalar("PRAGMA foreign_keys") == 1

    def test_a_dangling_reference_is_refused(self, db: Database) -> None:
        with pytest.raises(StoreError, match="FOREIGN KEY"):
            db.execute("INSERT INTO child (parent_id) VALUES (99)")

    def test_the_busy_timeout_is_set(self, db: Database) -> None:
        assert db.scalar("PRAGMA busy_timeout") == 5000


class CaseQuerying:
    def test_rows_come_back_by_name(self, db: Database) -> None:
        db.execute("INSERT INTO parent (code) VALUES ('A')")
        row = db.query_one("SELECT code FROM parent")
        assert row is not None
        assert row["code"] == "A"

    def test_query_returns_every_row(self, db: Database) -> None:
        db.execute_many("INSERT INTO parent (code) VALUES (?)", [("A",), ("B",)])
        assert len(db.query("SELECT * FROM parent")) == 2

    def test_query_one_returns_none_when_there_is_nothing(self, db: Database) -> None:
        assert db.query_one("SELECT * FROM parent") is None

    def test_scalar_returns_none_when_there_is_nothing(self, db: Database) -> None:
        assert db.scalar("SELECT code FROM parent") is None

    def test_named_parameters(self, db: Database) -> None:
        db.execute("INSERT INTO parent (code) VALUES (:code)", {"code": "A"})
        assert db.scalar("SELECT code FROM parent WHERE code = :code", {"code": "A"}) == "A"


class CaseErrors:
    def test_a_unique_collision_becomes_a_conflict(self, db: Database) -> None:
        db.execute("INSERT INTO parent (code) VALUES ('A')")
        with pytest.raises(ConflictError, match="parent.code"):
            db.execute("INSERT INTO parent (code) VALUES ('A')")

    def test_a_unique_collision_in_a_batch_becomes_a_conflict(self, db: Database) -> None:
        with pytest.raises(ConflictError):
            db.execute_many("INSERT INTO parent (code) VALUES (?)", [("A",), ("A",)])

    def test_a_broken_statement_names_itself(self, db: Database) -> None:
        with pytest.raises(StoreError, match="no such table"):
            db.execute("SELECT * FROM nowhere")

    def test_a_broken_batch_names_itself(self, db: Database) -> None:
        with pytest.raises(StoreError, match="no such table"):
            db.execute_many("INSERT INTO nowhere VALUES (?)", [("A",)])

    def test_a_broken_script_is_reported(self, db: Database) -> None:
        with pytest.raises(StoreError, match="script"):
            db.execute_script("CREATE TABLE parent (id INTEGER)")

    def test_a_not_null_violation_is_not_reported_as_a_conflict(self, db: Database) -> None:
        with pytest.raises(StoreError, match="NOT NULL"):
            db.execute("INSERT INTO parent (code) VALUES (NULL)")


class CaseTransactions:
    def test_a_committed_block_sticks(self, db: Database) -> None:
        with db.transaction():
            db.execute("INSERT INTO parent (code) VALUES ('A')")
        assert db.scalar("SELECT count(*) FROM parent") == 1

    def test_a_failed_block_rolls_back(self, db: Database) -> None:
        with pytest.raises(RuntimeError), db.transaction():
            db.execute("INSERT INTO parent (code) VALUES ('A')")
            raise RuntimeError("stop")
        assert db.scalar("SELECT count(*) FROM parent") == 0

    def test_nesting_is_refused_rather_than_tolerated(self, db: Database) -> None:
        with (
            db.transaction(),
            pytest.raises(StoreError, match="already open"),
            db.transaction(),
        ):
            pass


class CaseIntrospection:
    def test_table_names_are_sorted_and_exclude_sqlite_internals(self, db: Database) -> None:
        assert db.table_names() == ("child", "parent")

    def test_has_table(self, db: Database) -> None:
        assert db.has_table("parent")
        assert not db.has_table("nowhere")

    def test_column_names_are_in_declaration_order(self, db: Database) -> None:
        assert db.column_names("child") == ("id", "parent_id")
