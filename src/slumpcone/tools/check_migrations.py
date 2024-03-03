"""Apply every migration to an empty register, then check it is idempotent.

CI runs this. It catches the two failures a unit test does not: a migration
whose SQL is valid on its own but not against the schema the earlier ones
leave, and a migration list that has been renumbered so an existing register
cannot be brought forward.
"""

from __future__ import annotations

import sys

from slumpcone.store.db import Database
from slumpcone.store.migrations import (
    current_version,
    load_migrations,
    migrate,
    pending,
    verify,
)


def main() -> int:
    """Return zero when every migration applies cleanly to an empty register."""
    migrations = load_migrations()
    if not migrations:
        print("no migrations found")
        return 1
    with Database.in_memory() as database:
        ran = migrate(database)
        if len(ran) != len(migrations):
            print(f"applied {len(ran)} of {len(migrations)} migrations")
            return 1
        verify(database)
        if pending(database):
            print("migrations are still pending after a full run")
            return 1
        again = migrate(database)
        if again:
            print(f"a second run applied {len(again)} migrations, which is not idempotent")
            return 1
        tables = database.table_names()
        print(f"applied {len(ran)} migrations to version {current_version(database)}")
        print(f"{len(tables)} tables: {', '.join(tables)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
