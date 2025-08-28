from __future__ import annotations

from pathlib import Path

import pytest

from slumpcone.tools.check_docs import (
    DIFF_LINES,
    REFERENCE,
    check,
    difference,
    expected_reference,
    main,
)

HERE = Path(__file__).resolve().parents[1]


class CaseTheRealReference:
    def test_the_file_on_disk_matches_the_commands(self) -> None:
        code, lines = check(HERE / REFERENCE)
        assert code == 0, "\n".join(lines)

    def test_it_says_so(self) -> None:
        _, lines = check(HERE / REFERENCE)
        assert "matches the commands" in lines[0]

    def test_the_generated_text_is_not_empty(self) -> None:
        assert len(expected_reference()) > 10_000


class CaseDrift:
    def test_two_identical_texts_have_no_diff(self) -> None:
        assert difference("a\nb\n", "a\nb\n") == ()

    def test_a_change_shows(self) -> None:
        lines = difference("a\nb\n", "a\nc\n")
        assert any(line.startswith("-b") for line in lines)
        assert any(line.startswith("+c") for line in lines)

    def test_a_stale_file_fails(self, tmp_path: Path) -> None:
        stale = tmp_path / "commands.md"
        stale.write_text("# Command reference\n\nnothing like it\n")
        code, lines = check(stale)
        assert code == 1
        assert "has drifted" in lines[-1]

    def test_it_names_the_command_to_run(self, tmp_path: Path) -> None:
        stale = tmp_path / "commands.md"
        stale.write_text("stale\n")
        _, lines = check(stale)
        assert "register reference --out docs/commands.md" in lines[-1]

    def test_a_long_diff_is_trimmed(self, tmp_path: Path) -> None:
        stale = tmp_path / "commands.md"
        stale.write_text("\n".join(f"line {index}" for index in range(500)))
        _, lines = check(stale)
        assert any("more line(s)" in line for line in lines)
        assert len(lines) < DIFF_LINES + 10

    def test_a_missing_file_fails(self, tmp_path: Path) -> None:
        code, lines = check(tmp_path / "nope.md")
        assert code == 1
        assert "is not there" in lines[0]

    def test_it_never_writes(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.md"
        check(missing)
        assert not missing.exists()

    def test_a_stale_file_is_left_alone(self, tmp_path: Path) -> None:
        stale = tmp_path / "commands.md"
        stale.write_text("stale\n")
        check(stale)
        assert stale.read_text() == "stale\n"


class CaseMain:
    def test_it_passes_on_the_real_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main([str(HERE / REFERENCE)]) == 0
        assert "matches" in capsys.readouterr().out

    def test_it_fails_on_a_stale_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stale = tmp_path / "commands.md"
        stale.write_text("stale\n")
        assert main([str(stale)]) == 1
        assert "drifted" in capsys.readouterr().out

    def test_it_defaults_to_the_reference_path(self) -> None:
        assert Path("docs/commands.md") == REFERENCE
