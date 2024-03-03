"""Hand rolled migrations, in order, with a checksum on each one.

There is no framework here on purpose. The register is one SQLite file that
lives on the plant's own machine, and a migration tool that needs a network and
a virtualenv of its own is worse than a list of numbered files.

What the list does have is a checksum. Every applied migration records the hash
of the SQL that was applied, and the runner refuses to go on if a file has been
edited since. Editing an applied migration is the way a schema silently
diverges between the plant and the lab, and it is not recoverable once two
registers disagree.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from slumpcone.store.db import Database, StoreError

_FILENAME = re.compile(r"^(?P<version>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")

BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """One numbered step, and the SQL it runs."""

    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        """A hash of the SQL, insensitive to trailing whitespace only.

        Deliberately sensitive to everything else. Reformatting an applied
        migration is a change to it, whatever the author intended.
        """
        normalised = "\n".join(line.rstrip() for line in self.sql.strip().splitlines())
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    @property
    def filename(self) -> str:
        """The file this migration was read from."""
        return f"{self.version:04d}_{self.name}.sql"

    def __str__(self) -> str:
        return f"{self.version:04d} {self.name}"


def _read_from(directory: Path) -> tuple[Migration, ...]:
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise StoreError(f"migration file {path.name!r} is not named NNNN_name.sql")
        found.append(
            Migration(int(match.group("version")), match.group("name"), path.read_text("utf-8"))
        )
    versions = [m.version for m in found]
    if len(set(versions)) != len(versions):
        raise StoreError("two migrations share a version number")
    if versions != sorted(versions):
        raise StoreError("migrations are out of order")
    for position, version in enumerate(versions, start=1):
        if version != position:
            raise StoreError(f"migration {version:04d} leaves a gap at {position:04d}")
    return tuple(found)


def load_migrations() -> tuple[Migration, ...]:
    """Every migration shipped with the package, in version order."""
    directory = resources.files("slumpcone.store") / "schema"
    with resources.as_file(directory) as path:
        return _read_from(Path(path))


def applied(database: Database) -> dict[int, str]:
    """Version to checksum for everything already applied."""
    database.execute_script(BOOTSTRAP)
    rows = database.query("SELECT version, checksum FROM schema_migration ORDER BY version")
    return {int(row["version"]): str(row["checksum"]) for row in rows}


def pending(database: Database) -> tuple[Migration, ...]:
    """Migrations not yet applied to this register, in order."""
    done = applied(database)
    return tuple(m for m in load_migrations() if m.version not in done)


def verify(database: Database) -> None:
    """Refuse to go on when an applied migration no longer matches its file."""
    done = applied(database)
    by_version = {m.version: m for m in load_migrations()}
    for version, checksum in sorted(done.items()):
        migration = by_version.get(version)
        if migration is None:
            raise StoreError(
                f"the register has migration {version:04d} applied and the package "
                "does not ship it"
            )
        if migration.checksum != checksum:
            raise StoreError(
                f"migration {migration} has been edited since it was applied; "
                f"the register holds {checksum[:12]} and the file is {migration.checksum[:12]}"
            )


def migrate(database: Database, *, up_to: int | None = None) -> tuple[Migration, ...]:
    """Apply every pending migration, returning the ones that ran.

    Each migration runs in its own transaction together with the row that
    records it, so a failure part way leaves the register on the last version
    that fully applied rather than somewhere in between.
    """
    verify(database)
    ran: list[Migration] = []
    for migration in pending(database):
        if up_to is not None and migration.version > up_to:
            break
        with database.transaction():
            database.execute_script(migration.sql)
            database.execute(
                "INSERT INTO schema_migration (version, name, checksum, applied_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                (migration.version, migration.name, migration.checksum),
            )
        ran.append(migration)
    return tuple(ran)


def current_version(database: Database) -> int:
    """The highest applied version, or zero on an empty register."""
    done = applied(database)
    return max(done) if done else 0


def open_register(path: str | Path) -> Database:
    """Open a register and bring it up to the current schema."""
    database = Database.open(path)
    migrate(database)
    return database
