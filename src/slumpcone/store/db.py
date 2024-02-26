"""The SQLite connection, with the pragmas that make it behave.

Three settings matter and none of them is on by default. Foreign keys are off
unless you turn them on, which means a delete that should have been refused
quietly orphans rows. The journal defaults to a mode that blocks readers while
the batch computer writes. And the busy timeout is zero, so two processes
touching the register at once produces a locked error rather than a short wait.

The register is small -- a busy plant writes a few hundred rows a day -- so
none of this is about throughput. It is about the failures being loud.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from slumpcone.errors import ConflictError, SlumpconeError

BUSY_TIMEOUT_MS = 5000


class StoreError(SlumpconeError):
    """The database refused an operation."""


class Database:
    """A connection to the register."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._configure()

    def _configure(self) -> None:
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        cursor.close()

    @classmethod
    def open(cls, path: str | Path) -> Database:
        """Open, or create, the register at ``path``."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            str(target), isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES
        )
        database = cls(connection)
        database.execute("PRAGMA journal_mode = WAL")
        return database

    @classmethod
    def in_memory(cls) -> Database:
        """A register that lives only as long as this process. Tests use it."""
        connection = sqlite3.connect(
            ":memory:", isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES
        )
        return cls(connection)

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for the migration runner."""
        return self._connection

    def execute(
        self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Cursor:
        """Run one statement and return its cursor."""
        try:
            return self._connection.execute(sql, parameters)
        except sqlite3.IntegrityError as exc:
            raise self._as_conflict(exc) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"{exc} while running: {sql.strip().splitlines()[0]}") from exc

    def execute_many(
        self, sql: str, rows: Iterable[Sequence[Any] | dict[str, Any]]
    ) -> sqlite3.Cursor:
        """Run one statement over many parameter sets."""
        try:
            return self._connection.executemany(sql, rows)
        except sqlite3.IntegrityError as exc:
            raise self._as_conflict(exc) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"{exc} while running: {sql.strip().splitlines()[0]}") from exc

    def execute_script(self, sql: str) -> None:
        """Run a whole script. Used only by migrations."""
        try:
            self._connection.executescript(sql)
        except sqlite3.Error as exc:
            raise StoreError(f"{exc} while running a script") from exc

    def query(
        self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()
    ) -> list[sqlite3.Row]:
        """Every row a statement returns."""
        return self.execute(sql, parameters).fetchall()

    def query_one(
        self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        """The first row a statement returns, or ``None``."""
        row: sqlite3.Row | None = self.execute(sql, parameters).fetchone()
        return row

    def scalar(self, sql: str, parameters: Sequence[Any] | dict[str, Any] = ()) -> Any:
        """The first column of the first row, or ``None``."""
        row = self.query_one(sql, parameters)
        if row is None:
            return None
        return row[0]

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """Run a block inside one transaction, rolling back on any exception.

        Nesting is not supported and is not silently tolerated. A nested call
        would commit the outer work at the inner exit, which is exactly the
        bug this context manager exists to prevent.
        """
        if self._connection.in_transaction:
            raise StoreError("a transaction is already open on this connection")
        self._connection.execute("BEGIN")
        try:
            yield self
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def table_names(self) -> tuple[str, ...]:
        """Every table in the register, sorted, excluding SQLite's own."""
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return tuple(str(row["name"]) for row in rows)

    def has_table(self, name: str) -> bool:
        """True when a table of that name exists."""
        return name in self.table_names()

    def column_names(self, table: str) -> tuple[str, ...]:
        """Every column of a table, in declaration order."""
        rows = self.query(f"PRAGMA table_info({table})")
        return tuple(str(row["name"]) for row in rows)

    def close(self) -> None:
        """Close the connection."""
        self._connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @staticmethod
    def _as_conflict(exc: sqlite3.IntegrityError) -> SlumpconeError:
        text = str(exc)
        if "UNIQUE constraint failed" in text:
            target = text.split(":", 1)[-1].strip()
            return ConflictError("row", target)
        return StoreError(text)
