"""The two lookups every repository was writing out by hand.

Thirty of the read methods in this package opened the same way: run a query,
check for ``None``, raise :class:`NotFoundError` naming the kind and the
identity. Seventeen of the write methods opened the mirror of it: probe for a
row, raise :class:`ConflictError` if one is there. Both are three lines that say
one thing, and both were being retyped rather than reused.

That mattered for more than tidiness. Two of the hand written versions had
drifted: one named the kind differently in the probe and in the error, and one
checked truthiness rather than ``is None``, which is the same thing for a row
object today and stops being the same thing the moment a row is empty. Putting
the shape in one place makes that class of drift impossible rather than
unlikely.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.store.db import Database

Parameters = Sequence[Any] | dict[str, Any]


def require_one(
    database: Database,
    sql: str,
    parameters: Parameters,
    kind: str,
    identity: str,
) -> sqlite3.Row:
    """The row a statement returns, or a :class:`NotFoundError` naming it.

    ``kind`` and ``identity`` are what the error says, not what the query says,
    so a lookup that joins three tables still reports the thing the caller
    actually asked for.
    """
    row = database.query_one(sql, parameters)
    if row is None:
        raise NotFoundError(kind, identity)
    return row


def refuse_existing(
    database: Database,
    sql: str,
    parameters: Parameters,
    kind: str,
    identity: str,
) -> None:
    """Raise :class:`ConflictError` when a probe finds anything at all.

    The probe should select a constant rather than columns. What is in the row
    is never read, and selecting ``*`` on a wide table to throw it away is the
    kind of thing that looks free until the table is not small.
    """
    if database.query_one(sql, parameters) is not None:
        raise ConflictError(kind, identity)


def exists(database: Database, sql: str, parameters: Parameters = ()) -> bool:
    """Whether a probe finds anything.

    The same question as :func:`refuse_existing` asks, for the callers that want
    to branch on the answer rather than refuse.
    """
    return database.query_one(sql, parameters) is not None
