from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tests.cli.support import run


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")


class CaseVerify:
    def test_a_fresh_register_passes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "register", "verify")
        assert result.exit_code == 0
        assert "sound" in result.output

    def test_it_reports_both_questions(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "register", "verify")
        assert "pages" in result.output
        assert "references" in result.output

    def test_it_says_whether_a_vacuum_is_worth_it(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        result = run(runner, register, "register", "verify")
        assert "not worth doing yet" in result.output


class CaseBackup:
    def test_it_writes_where_told(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        target = tmp_path / "copy.sqlite3"
        result = run(runner, register, "register", "backup", str(target))
        assert result.exit_code == 0
        assert target.exists()
        assert "KiB" in result.output

    def test_it_names_the_file_when_given_a_folder(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        folder = tmp_path / "backups"
        result = run(runner, register, "register", "backup", "--into", str(folder))
        assert result.exit_code == 0
        assert list(folder.glob("register-*.sqlite3"))

    def test_the_stem_can_be_chosen(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        folder = tmp_path / "backups"
        run(
            runner,
            register,
            "register",
            "backup",
            "--into",
            str(folder),
            "--stem",
            "nightly",
        )
        assert list(folder.glob("nightly-*.sqlite3"))

    def test_both_at_once_is_refused(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "register",
            "backup",
            str(tmp_path / "a.sqlite3"),
            "--into",
            str(tmp_path),
        )
        assert result.exit_code != 0
        assert "not both" in result.output

    def test_neither_is_refused(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "register", "backup")
        assert result.exit_code != 0

    def test_it_will_not_overwrite(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        target = tmp_path / "copy.sqlite3"
        run(runner, register, "register", "backup", str(target))
        result = run(runner, register, "register", "backup", str(target))
        assert result.exit_code != 0
        assert "BACKUP_TARGET_EXISTS" in result.output


class CaseRestore:
    def test_it_puts_one_back(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        seeded(runner, register)
        made = tmp_path / "copy.sqlite3"
        run(runner, register, "register", "backup", str(made))
        target = tmp_path / "restored.sqlite3"
        result = run(runner, register, "register", "restore", str(made), str(target))
        assert result.exit_code == 0
        assert target.exists()

    def test_the_restored_register_reads(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        made = tmp_path / "copy.sqlite3"
        run(runner, register, "register", "backup", str(made))
        target = tmp_path / "restored.sqlite3"
        run(runner, register, "register", "restore", str(made), str(target))
        assert "4" in run(runner, str(target), "register", "info").output

    def test_it_will_not_clobber(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        made = tmp_path / "copy.sqlite3"
        run(runner, register, "register", "backup", str(made))
        result = run(runner, register, "register", "restore", str(made), register)
        assert result.exit_code != 0
        assert "RESTORE_WOULD_CLOBBER" in result.output

    def test_force_writes_over(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        seeded(runner, register)
        made = tmp_path / "copy.sqlite3"
        run(runner, register, "register", "backup", str(made))
        result = run(runner, register, "register", "restore", str(made), register, "--force")
        assert result.exit_code == 0

    def test_a_backup_that_is_not_there(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        result = run(
            runner,
            register,
            "register",
            "restore",
            str(tmp_path / "nope.sqlite3"),
            str(tmp_path / "out.sqlite3"),
        )
        assert result.exit_code != 0
        assert "RESTORE_NO_BACKUP" in result.output


class CaseBackupsFolder:
    def make(self, runner: CliRunner, register: str, folder: Path, count: int) -> None:
        seeded(runner, register)
        for index in range(count):
            run(runner, register, "register", "backup", str(folder / f"{index}.sqlite3"))

    def test_an_empty_folder(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        result = run(runner, register, "register", "backups", str(tmp_path / "nope"))
        assert "0 backup(s)" in result.output

    def test_it_lists_them(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        folder = tmp_path / "backups"
        self.make(runner, register, folder, 3)
        result = run(runner, register, "register", "backups", str(folder))
        assert "3 backup(s)" in result.output
        assert "KiB" in result.output

    def test_a_dry_run_deletes_nothing(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        folder = tmp_path / "backups"
        self.make(runner, register, folder, 4)
        result = run(
            runner, register, "register", "prune", str(folder), "--keep", "2", "--dry-run"
        )
        assert "2 of 4 would go" in result.output
        assert len(list(folder.glob("*.sqlite3"))) == 4

    def test_a_prune_keeps_the_newest(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        folder = tmp_path / "backups"
        self.make(runner, register, folder, 4)
        result = run(runner, register, "register", "prune", str(folder), "--keep", "2")
        assert "2 deleted, 2 kept" in result.output
        assert {path.name for path in folder.glob("*.sqlite3")} == {
            "2.sqlite3",
            "3.sqlite3",
        }

    def test_keeping_nothing_is_refused(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        folder = tmp_path / "backups"
        self.make(runner, register, folder, 2)
        result = run(runner, register, "register", "prune", str(folder), "--keep", "0")
        assert result.exit_code != 0
        assert len(list(folder.glob("*.sqlite3"))) == 2

    def test_keeping_nothing_is_refused_on_a_dry_run_too(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        folder = tmp_path / "backups"
        self.make(runner, register, folder, 2)
        result = run(
            runner, register, "register", "prune", str(folder), "--keep", "0", "--dry-run"
        )
        assert result.exit_code != 0


class CaseVacuum:
    def test_it_runs(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "register", "vacuum")
        assert result.exit_code == 0
        assert "reclaimed" in result.output

    def test_the_register_still_reads(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        run(runner, register, "register", "vacuum")
        assert run(runner, register, "register", "verify").exit_code == 0

    def test_it_refuses_below_the_minimum(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "register", "vacuum", "--minimum", "0.9")
        assert result.exit_code != 0
        assert "VACUUM_NOT_WORTH_IT" in result.output
