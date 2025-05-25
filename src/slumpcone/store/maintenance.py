"""Backing the register up, checking it, and reclaiming what it wastes.

A plant's register is one file on the batch computer, and the batch computer is
in a dusty room next to the mixer. It will be lost. So the interesting question
is not whether backups exist but whether the ones that exist can be restored,
and that turns on one detail people get wrong constantly.

**Copying the file while anything is writing does not produce a backup.** It
produces a file that opens, reads, and is missing whatever was mid transaction,
which is exactly the day nobody notices until the restore. SQLite has a backup
API that takes a consistent snapshot of a live database, and it is the only
thing here that writes a backup. There is no copy path to reach for by mistake.

The checks are two and they are different. ``integrity_check`` asks whether the
pages are internally consistent, which is a question about the file. The foreign
key check asks whether the rows point at rows that exist, which is a question
about the data, and a register can fail one and pass the other in either
direction. Both run, and both are reported.

Vacuum is last because it is the one that can make things worse: it rewrites the
whole file, which needs room for a second copy, and on a nearly full disk it
fails halfway. So it says how much it would reclaim before it does anything.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from slumpcone.errors import RuleViolationError
from slumpcone.store.db import Database


class MaintenanceError(RuleViolationError):
    """A maintenance operation that cannot be done safely."""


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """What the two checks said."""

    pages_ok: bool
    page_problems: tuple[str, ...]
    orphan_rows: tuple[str, ...]

    @property
    def keys_ok(self) -> bool:
        """Whether every reference points at a row that is there."""
        return not self.orphan_rows

    @property
    def is_sound(self) -> bool:
        """Both checks passed."""
        return self.pages_ok and self.keys_ok

    def describe(self) -> str:
        """One line."""
        if self.is_sound:
            return "register sound: pages consistent, every reference resolves"
        parts = []
        if not self.pages_ok:
            parts.append(f"{len(self.page_problems)} page problem(s)")
        if not self.keys_ok:
            parts.append(f"{len(self.orphan_rows)} orphaned row(s)")
        return "register NOT sound: " + ", ".join(parts)


@dataclass(frozen=True, slots=True)
class SpaceReport:
    """How much of the file is not carrying anything."""

    page_size: int
    total_pages: int
    free_pages: int

    @property
    def total_bytes(self) -> int:
        """How large the file is, as SQLite sees it."""
        return self.page_size * self.total_pages

    @property
    def free_bytes(self) -> int:
        """How much a vacuum would reclaim."""
        return self.page_size * self.free_pages

    @property
    def free_share(self) -> float:
        """Free space as a fraction of the file."""
        if not self.total_pages:
            return 0.0
        return self.free_pages / self.total_pages

    @property
    def is_worth_vacuuming(self) -> bool:
        """Whether there is enough waste to justify rewriting the file."""
        return self.free_share >= 0.10 and self.free_bytes >= 1_000_000

    def describe(self) -> str:
        """One line."""
        return (
            f"{self.total_bytes / 1024:.0f} KiB, {self.free_bytes / 1024:.0f} KiB free "
            f"({self.free_share * 100:.1f}%)"
        )


def integrity(database: Database) -> IntegrityReport:
    """Run both checks and report what each said."""
    pages = [str(row[0]) for row in database.query("PRAGMA integrity_check")]
    problems = tuple(line for line in pages if line != "ok")
    orphans = tuple(
        f"{row['table']} row {row['rowid']} references missing {row['parent']}"
        for row in database.query("PRAGMA foreign_key_check")
    )
    return IntegrityReport(not problems, problems, orphans)


def space(database: Database) -> SpaceReport:
    """How much of the file is free pages."""
    return SpaceReport(
        int(database.scalar("PRAGMA page_size") or 0),
        int(database.scalar("PRAGMA page_count") or 0),
        int(database.scalar("PRAGMA freelist_count") or 0),
    )


def back_up(database: Database, destination: str | Path) -> Path:
    """Take a consistent snapshot of a live register.

    This uses SQLite's own backup, which holds a read lock only as long as it
    needs each page and copes with the plant writing throughout. Do not replace
    it with a file copy.
    """
    target = Path(destination)
    if target.exists():
        raise MaintenanceError(
            "BACKUP_TARGET_EXISTS", f"{target} is already there, and a backup never overwrites"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(target)) as receiving:
        database.connection.backup(receiving)
    return target


def timestamped_backup(
    database: Database, directory: str | Path, stem: str = "register"
) -> Path:
    """A backup named for the moment it was taken."""
    folder = Path(directory)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return back_up(database, folder / f"{stem}-{stamp}.sqlite3")


def restore(backup: str | Path, destination: str | Path, *, force: bool = False) -> Path:
    """Put a backup back, refusing to clobber a register by accident.

    The backup is opened and checked before anything is written, because the one
    time this runs is the one time a corrupt backup would be worst.
    """
    source = Path(backup)
    target = Path(destination)
    if not source.exists():
        raise MaintenanceError("RESTORE_NO_BACKUP", f"{source} is not there")
    if target.exists() and not force:
        raise MaintenanceError(
            "RESTORE_WOULD_CLOBBER",
            f"{target} already exists, pass force to write over it",
        )
    with Database.open(source) as opened:
        report = integrity(opened)
    if not report.is_sound:
        raise MaintenanceError(
            "RESTORE_BACKUP_UNSOUND", f"{source} does not pass its own checks"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def vacuum(database: Database, *, minimum_free_share: float = 0.0) -> SpaceReport:
    """Rewrite the file to reclaim free pages.

    Returns the space report from *before* the vacuum, because that is the
    figure worth recording: afterwards there is nothing to reclaim by
    definition.
    """
    before = space(database)
    if before.free_share < minimum_free_share:
        raise MaintenanceError(
            "VACUUM_NOT_WORTH_IT",
            f"only {before.free_share * 100:.1f}% of the file is free, "
            f"below the {minimum_free_share * 100:.1f}% asked for",
        )
    database.execute("VACUUM")
    return before


def backups_in(directory: str | Path) -> tuple[Path, ...]:
    """Every backup in a directory, newest name last."""
    folder = Path(directory)
    if not folder.exists():
        return ()
    return tuple(sorted(folder.glob("*.sqlite3")))


def prune_backups(directory: str | Path, keep: int) -> tuple[Path, ...]:
    """Delete all but the newest ``keep`` backups, and say what went.

    Keeping zero is refused. A prune that can empty the directory is a prune
    that will, on the day somebody types the wrong number.
    """
    if keep < 1:
        raise MaintenanceError("PRUNE_KEEPS_NOTHING", "a prune has to keep at least one backup")
    found = backups_in(directory)
    doomed = found[: max(0, len(found) - keep)]
    for path in doomed:
        path.unlink()
    return doomed
