"""What is actually running, for the message somebody pastes into a bug report.

``--version`` gives the package version, which answers about a third of the
questions a report raises. The rest are the ones nobody thinks to ask and
everybody needs: which SQLite the register is being written by, which Python,
and which schema version the register on this machine is at.

That last one is the important one. A plant on last quarter's build and this
quarter's register file will see failures that make no sense from the package
version alone, and the two numbers are kept in different places on purpose. So
they are printed together, and the report says whether they agree.
"""

from __future__ import annotations

import platform
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from slumpcone import __version__
from slumpcone.store.migrations import load_migrations


@dataclass(frozen=True, slots=True)
class Versions:
    """Everything worth pasting into a bug report."""

    package: str
    python: str
    sqlite: str
    system: str
    migrations_known: int
    register_path: str | None = None
    register_version: int | None = None

    @property
    def register_is_current(self) -> bool | None:
        """Whether the file on disk is at the schema this build expects.

        ``None`` when there is no register to compare against, which is a
        different answer from "no" and is what somebody running the command
        before creating one should see.
        """
        if self.register_version is None:
            return None
        return self.register_version == self.migrations_known

    @property
    def register_standing(self) -> str:
        """The comparison in words."""
        current = self.register_is_current
        if current is None:
            return "no register read"
        if current:
            return "current"
        if self.register_version is not None and self.register_version < self.migrations_known:
            behind = self.migrations_known - self.register_version
            return f"{behind} migration(s) behind this build"
        return "ahead of this build, which is a newer build's register"

    def as_pairs(self) -> list[tuple[str, object]]:
        """The lines, in the order somebody would read them."""
        pairs: list[tuple[str, object]] = [
            ("slumpcone", self.package),
            ("python", self.python),
            ("sqlite", self.sqlite),
            ("system", self.system),
            ("migrations in this build", self.migrations_known),
        ]
        if self.register_path is not None:
            pairs.extend(
                [
                    ("register", self.register_path),
                    (
                        "register schema",
                        "not created yet"
                        if self.register_version is None
                        else self.register_version,
                    ),
                    ("standing", self.register_standing),
                ]
            )
        return pairs

    def describe(self) -> str:
        """One line, for a log."""
        return (
            f"slumpcone {self.package}, python {self.python}, "
            f"sqlite {self.sqlite}, schema {self.migrations_known}"
        )


def collect(register_path: Path | None = None) -> Versions:
    """Gather everything, reading the register only if it is there.

    A missing register is not an error here. Somebody running this is usually
    trying to find out why something else did not work, and a version command
    that fails is no help at all.
    """
    schema: int | None = None
    if register_path is not None and register_path.exists():
        try:
            from slumpcone.store.db import Database
            from slumpcone.store.migrations import current_version

            with Database.open(register_path) as database:
                schema = current_version(database)
        except Exception:  # noqa: BLE001 - a version report never fails
            schema = None
    return Versions(
        __version__,
        platform.python_version(),
        sqlite3.sqlite_version,
        f"{platform.system()} {platform.machine()}",
        len(load_migrations()),
        None if register_path is None else str(register_path),
        schema,
    )
