from __future__ import annotations

from click.testing import CliRunner

from tests.cli.support import run


def seeded(runner: CliRunner, register: str) -> None:
    run(runner, register, "demo", "seed")
    run(runner, register, "carbon", "seed")
    for code, kind, value in (
        ("CEM-I", "cement", "0.922"),
        ("SCM-F", "scm", "0.027"),
        ("CA-57", "coarse_aggregate", "0.0075"),
        ("FA-1", "fine_aggregate", "0.0048"),
        ("W-1", "water", "0.0003"),
    ):
        run(runner, register, "carbon", "factor", code, "--class", kind, "--value", value)


class CaseSeed:
    def test_it_loads_the_defaults(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "carbon", "seed")
        assert result.exit_code == 0
        assert "factor(s) added" in result.output

    def test_it_warns_that_averages_cannot_be_declared(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(runner, register, "carbon", "seed")
        assert "cannot back a declaration" in result.output

    def test_seeding_twice_adds_nothing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "carbon", "seed")
        result = run(runner, register, "carbon", "seed")
        assert "0 factor(s) added" in result.output
        assert "already on file" in result.output


class CaseFactors:
    def test_filing_one(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "carbon",
            "factor",
            "CEM-I",
            "--class",
            "cement",
            "--value",
            "0.922",
        )
        assert result.exit_code == 0
        assert "0.9220" in result.output

    def test_an_epd_needs_a_document(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "carbon",
            "factor",
            "CEM-I",
            "--class",
            "cement",
            "--value",
            "0.922",
            "--provenance",
            "product epd",
        )
        assert result.exit_code != 0
        assert "CARBON_EPD_WITHOUT_SOURCE" in result.output

    def test_an_epd_with_a_document(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "carbon",
            "factor",
            "CEM-I",
            "--class",
            "cement",
            "--value",
            "0.922",
            "--provenance",
            "product epd",
            "--source",
            "EPD 4471",
            "--published",
            "2023-01-01",
        )
        assert result.exit_code == 0
        assert "EPD 4471" in result.output

    def test_a_class_nobody_knows(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "carbon",
            "factor",
            "X",
            "--class",
            "unobtainium",
            "--value",
            "1",
        )
        assert result.exit_code != 0

    def test_a_negative_factor(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "carbon",
            "factor",
            "CEM-I",
            "--class",
            "cement",
            "--value",
            "-1",
        )
        assert result.exit_code != 0
        assert "CARBON_FACTOR_NEGATIVE" in result.output

    def test_the_listing(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "carbon", "seed")
        result = run(runner, register, "carbon", "factors")
        assert "OPC" in result.output
        assert "factor(s)" in result.output

    def test_only_the_stale(self, runner: CliRunner, register: str) -> None:
        run(
            runner,
            register,
            "carbon",
            "factor",
            "CEM-I",
            "--class",
            "cement",
            "--value",
            "0.922",
            "--published",
            "2023-01-01",
        )
        run(
            runner,
            register,
            "carbon",
            "factor",
            "CA-57",
            "--class",
            "coarse_aggregate",
            "--value",
            "0.0075",
            "--published",
            "2017-01-01",
        )
        result = run(runner, register, "carbon", "factors", "--stale", "--on", "2024-06-12")
        assert "CA-57" in result.output
        assert "1 factor(s)" in result.output

    def test_dropping_one(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "carbon", "seed")
        result = run(runner, register, "carbon", "drop", "OPC")
        assert "dropped" in result.output

    def test_dropping_one_that_is_not_there(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "carbon", "drop", "OPC").exit_code != 0


class CaseDensity:
    def test_filing_one(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "carbon", "density", "AD-AE", "8.4 lb/gal")
        assert result.exit_code == 0
        assert "8.4" in result.output

    def test_an_unreadable_density(self, runner: CliRunner, register: str) -> None:
        assert run(runner, register, "carbon", "density", "AD-AE", "heavy").exit_code != 0


class CaseMix:
    def test_the_footprint_prints(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "mix", "4000P-57")
        assert result.exit_code == 0
        assert "per m3" in result.output
        assert "cement share" in result.output

    def test_the_lines_are_ranked(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "mix", "4000P-57")
        body = result.output.split("material")[1]
        assert body.index("CEM-I") < body.index("CA-57")

    def test_the_admixtures_are_named_as_uncounted(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "mix", "4000P-57")
        assert "not counted" in result.output

    def test_the_benchmark_verdict_prints(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "mix", "4000P-57", "--on", "2024-06-12")
        assert "not declarable" in result.output
        assert "not all product EPDs" in result.output

    def test_a_table_that_is_not_on_file(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "mix", "4000P-57", "--table", "state dot")
        assert "no benchmark table named state dot" in result.output

    def test_a_larger_volume_does_not_move_the_rate(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        one = run(runner, register, "carbon", "mix", "4000P-57")
        ten = run(runner, register, "carbon", "mix", "4000P-57", "--volume", "10 yd3")
        assert "10.00 yd3" in ten.output
        rate = [line for line in one.output.splitlines() if "per m3" in line][0]
        assert rate in ten.output

    def test_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        assert run(runner, register, "carbon", "mix", "NOPE").exit_code != 0

    def test_a_named_revision(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "mix", "4000P-57", "--revision", "1")
        assert "r1" in result.output


def a_leaner_mix(runner: CliRunner, register: str) -> None:
    """A second design carrying more ash and less cement."""
    run(
        runner,
        register,
        "mix",
        "add",
        "4000L-57",
        "leaner paving mix",
        "--strength",
        "4000 psi",
        "--nms",
        "1 in",
        "--slump",
        "4 in",
        "--air",
        "6",
        "--charge",
        "CEM-I:cement:376 lb/yd3",
        "--charge",
        "SCM-F:scm:188 lb/yd3",
        "--charge",
        "CA-57:coarse_aggregate:1780 lb/yd3",
        "--charge",
        "FA-1:fine_aggregate:1255 lb/yd3",
        "--charge",
        "W-1:water:250 lb/yd3",
    )


class CaseCompare:
    def test_one_mix_is_not_a_comparison(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "compare", "4000P-57")
        assert result.exit_code != 0
        assert "CARBON_NOTHING_TO_COMPARE" in result.output

    def test_two_mixes(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        a_leaner_mix(runner, register)
        result = run(runner, register, "carbon", "compare", "4000P-57", "4000L-57")
        assert result.exit_code == 0
        assert "lightest" in result.output

    def test_the_leaner_mix_comes_first(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        a_leaner_mix(runner, register)
        result = run(runner, register, "carbon", "compare", "4000P-57", "4000L-57")
        body = result.output.split("against lightest")[1]
        assert body.index("4000L-57") < body.index("4000P-57")

    def test_an_unknown_mix_in_the_list(self, runner: CliRunner, register: str) -> None:
        seeded(runner, register)
        result = run(runner, register, "carbon", "compare", "4000P-57", "NOPE")
        assert result.exit_code != 0

    def test_the_lightest_reads_zero_against_itself(
        self, runner: CliRunner, register: str
    ) -> None:
        seeded(runner, register)
        a_leaner_mix(runner, register)
        result = run(runner, register, "carbon", "compare", "4000P-57", "4000L-57")
        assert "0.0%" in result.output


class CaseTables:
    def test_nothing_on_file(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "carbon", "tables")
        assert "0 table(s)" in result.output

    def test_the_seeded_table(self, runner: CliRunner, register: str) -> None:
        run(runner, register, "carbon", "seed")
        result = run(runner, register, "carbon", "tables")
        assert "national average" in result.output
        assert "kg CO2e/m3" in result.output
        assert "1 table(s)" in result.output


def test_the_group_is_wired_in(runner: CliRunner, register: str) -> None:
    assert "carbon" in run(runner, register, "--help").output
