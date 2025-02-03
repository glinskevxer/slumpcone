from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tests.cli.support import run

RECORDER = (
    "Ticket,Plant,Mix,Batch Time,CY,Unit\n"
    "881204,PL-1,4000P-57,2024-06-12 07:42,9.0,TR-114\n"
    "881205,PL-1,4000P-57,2024-06-12 08:15,7.5,TR-114\n"
)

BAD_RECORDER = RECORDER + ",PL-1,4000P-57,2024-06-12 09:00,nine,TR-114\n"

FIELD = "Ticket,Sample Time,Slump,Air %,Temp F,Tech\n881204,2024-06-12 08:05,4.5,6.2,78,DK\n"

RECEIPTS = (
    "Ref,Plant,Bin,Product,Delivery Time,Net Weight,Vendor,Mill Cert\n"
    "RCV-2211,PL-1,SI-1,CEM-I,2024-06-11 05:40,48000,Ashfield,MC-2024-0412\n"
)


def write(tmp_path: Path, name: str, text: str) -> str:
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return str(target)


class CaseProfiles:
    def test_it_lists_them(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "import", "profiles")
        assert "BATCH-RECORDER" in result.output
        assert "LAB-BREAKS" in result.output
        assert "required" in result.output


class CaseRun:
    def test_a_clean_file(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        path = write(tmp_path, "recorder.csv", RECORDER)
        result = run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        assert result.exit_code == 0
        assert "2 accepted" in result.output
        assert "run 1" in result.output

    def test_a_file_with_a_bad_row(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        path = write(tmp_path, "recorder.csv", BAD_RECORDER)
        result = run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        assert "1 quarantined" in result.output
        assert "as a number" in result.output

    def test_a_re_run_is_all_duplicate(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        path = write(tmp_path, "recorder.csv", RECORDER)
        run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        result = run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        assert "0 accepted" in result.output
        assert "2 already on file" in result.output

    def test_apply_writes_deliveries(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        path = write(tmp_path, "recorder.csv", RECORDER)
        result = run(
            runner, register, "import", "run", path, "--profile", "BATCH-RECORDER", "--apply"
        )
        assert "2 record(s) written" in result.output
        listing = run(
            runner, register, "delivery", "list", "--from", "2024-06-01", "--to", "2024-06-30"
        )
        assert "881204" in listing.output

    def test_apply_writes_fresh_tests(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        path = write(tmp_path, "field.csv", FIELD)
        run(runner, register, "import", "run", path, "--profile", "FIELD-TESTS", "--apply")
        listing = run(runner, register, "field", "list", "881204")
        assert "slump" in listing.output
        assert "air_pressure" in listing.output

    def test_apply_writes_receipts(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        path = write(tmp_path, "receipts.csv", RECEIPTS)
        run(
            runner, register, "import", "run", path, "--profile", "MATERIAL-RECEIPTS", "--apply"
        )
        listing = run(
            runner,
            register,
            "inventory",
            "receipts",
            "--plant",
            "PL-1",
            "--from",
            "2024-06-01",
            "--to",
            "2024-06-30",
        )
        assert "RCV-2211" in listing.output

    def test_an_unknown_profile(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        path = write(tmp_path, "recorder.csv", RECORDER)
        result = run(runner, register, "import", "run", path, "--profile", "NOTHING")
        assert result.exit_code != 0

    def test_a_missing_file(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        result = run(
            runner,
            register,
            "import",
            "run",
            str(tmp_path / "gone.csv"),
            "--profile",
            "BATCH-RECORDER",
        )
        assert result.exit_code != 0

    def test_a_file_that_cannot_be_mapped(
        self, runner: CliRunner, register: str, tmp_path: Path
    ) -> None:
        path = write(tmp_path, "wrong.csv", "a,b\n1,2\n")
        result = run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        assert result.exit_code != 0
        assert "needs" in result.output


class CaseHistory:
    def test_runs(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        path = write(tmp_path, "recorder.csv", RECORDER)
        run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        result = run(runner, register, "import", "runs", "--profile", "BATCH-RECORDER")
        assert "recorder.csv" in result.output
        assert "accepted" in result.output

    def test_quarantine(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        path = write(tmp_path, "recorder.csv", BAD_RECORDER)
        run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        result = run(runner, register, "import", "quarantine", "--profile", "BATCH-RECORDER")
        assert "Quarantine under BATCH-RECORDER" in result.output
        assert "as a number" in result.output

    def test_forget(self, runner: CliRunner, register: str, tmp_path: Path) -> None:
        path = write(tmp_path, "recorder.csv", RECORDER)
        run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        result = run(runner, register, "import", "forget", "1")
        assert "run 1 forgotten" in result.output
        again = run(runner, register, "import", "run", path, "--profile", "BATCH-RECORDER")
        assert "2 accepted" in again.output

    def test_forgetting_an_unknown_run(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "import", "forget", "99")
        assert result.exit_code != 0
