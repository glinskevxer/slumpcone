from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


class CasePlans:
    def test_a_seeded_register_passes(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "register", "plans")
        assert result.exit_code == 0
        assert "probe(s) use an index" in result.output

    def test_an_empty_register_passes_too(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "register", "plans").exit_code == 0

    def test_only_the_bad_ones_show_by_default(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "register", "plans")
        assert "tickets in a window" not in result.output

    def test_all_shows_every_probe(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "register", "plans", "--all")
        assert "tickets in a window" in result.output
        assert "certificates by expiry" in result.output

    def test_the_timings_print(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "demo", "seed")
        result = run(runner, register, "register", "plans", "--all")
        assert "ms" in result.output
        assert "searches" in result.output
