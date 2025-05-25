from __future__ import annotations

from pathlib import Path

import pytest

from slumpcone.demo import seed
from slumpcone.register import Register
from slumpcone.store.db import Database
from slumpcone.store.maintenance import (
    IntegrityReport,
    MaintenanceError,
    SpaceReport,
    back_up,
    backups_in,
    integrity,
    prune_backups,
    restore,
    space,
    timestamped_backup,
    vacuum,
)


@pytest.fixture()
def on_disk(tmp_path: Path) -> Database:
    register = Register.open(tmp_path / "register.sqlite3")
    seed(register)
    return register.database


class CaseIntegrity:
    def test_a_fresh_register_is_sound(self, on_disk: Database) -> None:
        report = integrity(on_disk)
        assert report.is_sound
        assert report.pages_ok
        assert report.keys_ok

    def test_it_says_so(self, on_disk: Database) -> None:
        assert "sound" in integrity(on_disk).describe()

    def test_an_orphan_row_is_caught(self, on_disk: Database) -> None:
        on_disk.execute("PRAGMA foreign_keys = OFF")
        on_disk.execute(
            "INSERT INTO plant_scale (plant_code, code, name, capacity_lb, "
            "graduation_lb, weighs, last_calibrated, calibration_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("PL-NOPE", "SC-9", "ghost", 20000.0, 5.0, "cement", "2024-01-01", 365),
        )
        report = integrity(on_disk)
        assert not report.keys_ok
        assert not report.is_sound
        assert "orphaned row" in report.describe()

    def test_the_orphan_names_its_table(self, on_disk: Database) -> None:
        on_disk.execute("PRAGMA foreign_keys = OFF")
        on_disk.execute(
            "INSERT INTO plant_scale (plant_code, code, name, capacity_lb, "
            "graduation_lb, weighs, last_calibrated, calibration_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("PL-NOPE", "SC-9", "ghost", 20000.0, 5.0, "cement", "2024-01-01", 365),
        )
        assert "plant_scale" in integrity(on_disk).orphan_rows[0]

    def test_pages_and_keys_are_separate_questions(self) -> None:
        report = IntegrityReport(False, ("broken page",), ())
        assert report.keys_ok
        assert not report.pages_ok
        assert not report.is_sound
        assert "page problem" in report.describe()


class CaseSpace:
    def test_it_reads_the_file(self, on_disk: Database) -> None:
        report = space(on_disk)
        assert report.page_size > 0
        assert report.total_pages > 0
        assert report.total_bytes == report.page_size * report.total_pages

    def test_a_fresh_register_wastes_almost_nothing(self, on_disk: Database) -> None:
        assert space(on_disk).free_share < 0.5

    def test_a_small_file_is_not_worth_vacuuming(self, on_disk: Database) -> None:
        assert not space(on_disk).is_worth_vacuuming

    def test_a_big_wasteful_file_is(self) -> None:
        report = SpaceReport(4096, 10_000, 5_000)
        assert report.is_worth_vacuuming
        assert report.free_share == pytest.approx(0.5)

    def test_a_wasteful_but_tiny_file_is_not(self) -> None:
        assert not SpaceReport(4096, 100, 50).is_worth_vacuuming

    def test_an_empty_file(self) -> None:
        report = SpaceReport(4096, 0, 0)
        assert report.free_share == pytest.approx(0.0)
        assert not report.is_worth_vacuuming

    def test_describe(self) -> None:
        assert "KiB" in SpaceReport(4096, 10_000, 5_000).describe()


class CaseBackup:
    def test_it_writes_a_file(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "copy.sqlite3")
        assert made.exists()
        assert made.stat().st_size > 0

    def test_the_copy_carries_the_rows(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "copy.sqlite3")
        with Database.open(made) as copy:
            assert copy.scalar("SELECT count(*) FROM batch_ticket") == 4

    def test_the_copy_is_sound(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "copy.sqlite3")
        with Database.open(made) as copy:
            assert integrity(copy).is_sound

    def test_it_refuses_to_overwrite(self, on_disk: Database, tmp_path: Path) -> None:
        back_up(on_disk, tmp_path / "copy.sqlite3")
        with pytest.raises(MaintenanceError) as caught:
            back_up(on_disk, tmp_path / "copy.sqlite3")
        assert caught.value.code == "BACKUP_TARGET_EXISTS"

    def test_it_makes_the_directory(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "deep" / "down" / "copy.sqlite3")
        assert made.exists()

    def test_a_timestamped_backup_lands_in_the_folder(
        self, on_disk: Database, tmp_path: Path
    ) -> None:
        made = timestamped_backup(on_disk, tmp_path / "backups")
        assert made.parent == tmp_path / "backups"
        assert made.name.startswith("register-")

    def test_the_stem_can_be_chosen(self, on_disk: Database, tmp_path: Path) -> None:
        made = timestamped_backup(on_disk, tmp_path / "backups", stem="nightly")
        assert made.name.startswith("nightly-")


class CaseRestore:
    def test_it_puts_a_backup_back(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "copy.sqlite3")
        put = restore(made, tmp_path / "restored.sqlite3")
        with Database.open(put) as back:
            assert back.scalar("SELECT count(*) FROM batch_ticket") == 4

    def test_a_backup_that_is_not_there(self, tmp_path: Path) -> None:
        with pytest.raises(MaintenanceError) as caught:
            restore(tmp_path / "nope.sqlite3", tmp_path / "out.sqlite3")
        assert caught.value.code == "RESTORE_NO_BACKUP"

    def test_it_refuses_to_clobber(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "copy.sqlite3")
        target = tmp_path / "register.sqlite3"
        with pytest.raises(MaintenanceError) as caught:
            restore(made, target)
        assert caught.value.code == "RESTORE_WOULD_CLOBBER"

    def test_force_writes_over(self, on_disk: Database, tmp_path: Path) -> None:
        made = back_up(on_disk, tmp_path / "copy.sqlite3")
        put = restore(made, tmp_path / "register.sqlite3", force=True)
        assert put.exists()

    def test_an_unsound_backup_is_refused(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.sqlite3"
        with Database.open(broken) as database:
            database.execute("PRAGMA foreign_keys = OFF")
            database.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            database.execute(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent(id))"
            )
            database.execute("INSERT INTO child (id, parent_id) VALUES (1, 99)")
        with pytest.raises(MaintenanceError) as caught:
            restore(broken, tmp_path / "out.sqlite3")
        assert caught.value.code == "RESTORE_BACKUP_UNSOUND"

    def test_a_refused_restore_writes_nothing(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.sqlite3"
        with Database.open(broken) as database:
            database.execute("PRAGMA foreign_keys = OFF")
            database.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            database.execute(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent(id))"
            )
            database.execute("INSERT INTO child (id, parent_id) VALUES (1, 99)")
        with pytest.raises(MaintenanceError):
            restore(broken, tmp_path / "out.sqlite3")
        assert not (tmp_path / "out.sqlite3").exists()


class CaseVacuum:
    def test_it_reports_what_it_started_from(self, on_disk: Database) -> None:
        before = vacuum(on_disk)
        assert before.total_pages > 0

    def test_it_leaves_the_register_sound(self, on_disk: Database) -> None:
        vacuum(on_disk)
        assert integrity(on_disk).is_sound

    def test_the_rows_survive(self, on_disk: Database) -> None:
        vacuum(on_disk)
        assert on_disk.scalar("SELECT count(*) FROM batch_ticket") == 4

    def test_it_refuses_when_there_is_nothing_to_reclaim(self, on_disk: Database) -> None:
        with pytest.raises(MaintenanceError) as caught:
            vacuum(on_disk, minimum_free_share=0.9)
        assert caught.value.code == "VACUUM_NOT_WORTH_IT"

    def test_the_refusal_names_the_two_figures(self, on_disk: Database) -> None:
        with pytest.raises(MaintenanceError) as caught:
            vacuum(on_disk, minimum_free_share=0.9)
        assert "90.0%" in str(caught.value)


class CasePruning:
    def test_nothing_in_an_empty_folder(self, tmp_path: Path) -> None:
        assert backups_in(tmp_path / "nope") == ()
        assert prune_backups(tmp_path, keep=3) == ()

    def test_it_lists_what_is_there(self, on_disk: Database, tmp_path: Path) -> None:
        folder = tmp_path / "backups"
        for name in ("a", "b", "c"):
            back_up(on_disk, folder / f"{name}.sqlite3")
        assert len(backups_in(folder)) == 3

    def test_it_keeps_the_newest(self, on_disk: Database, tmp_path: Path) -> None:
        folder = tmp_path / "backups"
        for name in ("a", "b", "c", "d"):
            back_up(on_disk, folder / f"{name}.sqlite3")
        gone = prune_backups(folder, keep=2)
        assert [path.name for path in gone] == ["a.sqlite3", "b.sqlite3"]
        assert [path.name for path in backups_in(folder)] == ["c.sqlite3", "d.sqlite3"]

    def test_keeping_more_than_there_are(self, on_disk: Database, tmp_path: Path) -> None:
        folder = tmp_path / "backups"
        back_up(on_disk, folder / "a.sqlite3")
        assert prune_backups(folder, keep=10) == ()

    def test_keeping_nothing_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(MaintenanceError) as caught:
            prune_backups(tmp_path, keep=0)
        assert caught.value.code == "PRUNE_KEEPS_NOTHING"

    def test_a_refused_prune_deletes_nothing(self, on_disk: Database, tmp_path: Path) -> None:
        folder = tmp_path / "backups"
        back_up(on_disk, folder / "a.sqlite3")
        with pytest.raises(MaintenanceError):
            prune_backups(folder, keep=-1)
        assert len(backups_in(folder)) == 1
