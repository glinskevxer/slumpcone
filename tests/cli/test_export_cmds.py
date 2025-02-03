from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tests.cli.support import run


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")


class CaseExport:
    def test_tickets_to_stdout(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "export",
            "tickets",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
        )
        assert result.exit_code == 0
        assert result.output.splitlines()[0].startswith("ticket,plant,mix")
        assert "881204" in result.output

    def test_tickets_to_a_file(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        seeded(runner, register)
        out = tmp_path / "tickets.csv"
        result = run(
            runner,
            register,
            "export",
            "tickets",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
            "--out",
            str(out),
        )
        assert "written to" in result.output
        assert "881204" in out.read_text()

    def test_another_delimiter(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(
            runner,
            register,
            "export",
            "tickets",
            "--from",
            "2024-06-12",
            "--to",
            "2024-06-12",
            "--delimiter",
            ";",
        )
        assert "ticket;plant" in result.output

    def test_strength(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "export", "strength", "4000P-57")
        assert "result_psi" in result.output
        assert "S-4471" in result.output

    def test_materials(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "export", "materials")
        assert "specific_gravity" in result.output
        assert "CEM-I" in result.output


class CaseMixDocument:
    def test_export_and_load_round_trip(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        out = tmp_path / "mix.json"
        run(runner, register, "export", "mix", "4000P-57", "--out", str(out))
        assert '"slumpcone.mixdesign"' in out.read_text()
        other = str(tmp_path / "other.sqlite3")
        result = run(runner, other, "export", "load-mix", str(out))
        assert result.exit_code == 0
        assert "4000P-57 r1" in result.output
        assert "4000P-57" in run(runner, other, "mix", "list").output

    def test_loading_under_a_new_revision(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        out = tmp_path / "mix.json"
        run(runner, register, "export", "mix", "4000P-57", "--out", str(out))
        result = run(runner, register, "export", "load-mix", str(out), "--revision", "2")
        assert "4000P-57 r2" in result.output

    def test_loading_the_same_revision_twice(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        seeded(runner, register)
        out = tmp_path / "mix.json"
        run(runner, register, "export", "mix", "4000P-57", "--out", str(out))
        result = run(runner, register, "export", "load-mix", str(out))
        assert result.exit_code != 0
        assert "already on file" in result.output

    def test_loading_something_that_is_not_a_document(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        result = run(runner, register, "export", "load-mix", str(bad))
        assert result.exit_code != 0
        assert "not JSON" in result.output

    def test_exporting_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "export", "mix", "4000P-58").exit_code != 0


class CaseAudit:
    def test_record_and_read(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "audit",
            "record",
            "ticket written",
            "ticket 881204",
            "--actor",
            "DK",
            "--detail",
            "9 yd3",
        )
        assert result.exit_code == 0
        assert "ticket 881204" in result.output

    def test_the_log_by_subject(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "audit",
            "record",
            "written",
            "ticket 881204",
            "--actor",
            "DK",
        )
        run(runner, register, "audit", "record", "written", "ticket 881205", "--actor", "DK")
        result = run(runner, register, "audit", "log", "--subject", "ticket 881204")
        assert "881204" in result.output
        assert "881205" not in result.output

    def test_the_log_by_actor(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "audit", "record", "written", "T", "--actor", "DK")
        run(runner, register, "audit", "record", "approved", "S", "--actor", "County")
        result = run(runner, register, "audit", "log", "--actor", "County")
        assert "approved" in result.output
        assert "written" not in result.output

    def test_verify_on_a_clean_log(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "audit", "record", "written", "T", "--actor", "DK")
        result = run(runner, register, "audit", "verify")
        assert result.exit_code == 0
        assert "intact" in result.output

    def test_verify_catches_an_edit(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "audit", "record", "written", "T", "--actor", "DK")
        import sqlite3

        connection = sqlite3.connect(register)
        connection.execute("UPDATE audit_event SET detail = 'tampered' WHERE id = 1")
        connection.commit()
        connection.close()
        result = run(runner, register, "audit", "verify")
        assert result.exit_code != 0
        assert "first break at event 1" in result.output
