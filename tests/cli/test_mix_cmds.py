from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run


def stock_materials(runner: CliRunner, register: str) -> None:
    run(
        runner,
        register,
        "material",
        "add",
        "CEM-I",
        "Portland",
        "--class",
        "cement",
        "--cement-type",
        "II",
        "--sg",
        "3.15",
    )
    run(
        runner,
        register,
        "material",
        "add",
        "SCM-F",
        "Class F ash",
        "--class",
        "scm",
        "--scm-kind",
        "fly_ash_f",
        "--sg",
        "2.35",
    )
    run(
        runner,
        register,
        "material",
        "add",
        "CA-57",
        "Number 57",
        "--class",
        "coarse_aggregate",
        "--sg",
        "2.68",
        "--absorption",
        "0.7",
        "--nms",
        "1 in",
        "--dry-rodded",
        "101.5 lb/ft3",
    )
    run(
        runner,
        register,
        "material",
        "add",
        "FA-1",
        "Sand",
        "--class",
        "fine_aggregate",
        "--sg",
        "2.63",
        "--absorption",
        "1.4",
        "--fm",
        "2.84",
    )
    run(
        runner,
        register,
        "material",
        "add",
        "W-1",
        "Water",
        "--class",
        "water",
        "--water-source",
        "potable",
    )


def add_mix(runner: CliRunner, register: str, **extra: str) -> Result:
    args = [
        "mix",
        "add",
        "4000P-57",
        "Paving mix",
        "--strength",
        "4500 psi",
        "--nms",
        "1 in",
        "--slump",
        "4 in",
        "--air",
        "6.0",
        "--exposure",
        "F2 S1",
        "--charge",
        "CEM-I:cement:470",
        "--charge",
        "SCM-F:scm:94",
        "--charge",
        "CA-57:coarse_aggregate:1780",
        "--charge",
        "FA-1:fine_aggregate:1255",
        "--charge",
        "W-1:water:250",
        "--admixture",
        "AD-AE:1.2",
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return run(runner, register, *args)


class CaseAdd:
    def test_it_files_a_design(self, runner: CliRunner, register: str) -> None:
        result = add_mix(runner, register)
        assert result.exit_code == 0
        assert "4000P-57 r1" in result.output
        assert "w/cm 0.443" in result.output

    def test_a_design_with_no_charges(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "mix",
            "add",
            "M",
            "X",
            "--strength",
            "4000 psi",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
        )
        assert result.exit_code != 0
        assert "at least one --charge" in result.output

    def test_a_malformed_charge(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "mix",
            "add",
            "M",
            "X",
            "--strength",
            "4000 psi",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
            "--charge",
            "CEM-I",
        )
        assert result.exit_code != 0
        assert "CODE:CLASS:CONTENT" in result.output

    def test_a_malformed_dose(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "mix",
            "add",
            "M",
            "X",
            "--strength",
            "4000 psi",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
            "--charge",
            "W-1:water:250",
            "--charge",
            "CEM-I:cement:470",
            "--admixture",
            "AD-AE",
        )
        assert result.exit_code != 0
        assert "CODE:DOSE" in result.output

    def test_a_charge_with_an_explicit_unit_pair(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(
            runner,
            register,
            "mix",
            "add",
            "M",
            "X",
            "--strength",
            "4000 psi",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
            "--charge",
            "CEM-I:cement:335 kg/m3",
            "--charge",
            "W-1:water:150 kg/m3",
        )
        assert result.exit_code == 0

    def test_filing_the_same_revision_twice(self, runner: CliRunner, register: str) -> None:
        add_mix(runner, register)
        result = add_mix(runner, register)
        assert result.exit_code != 0
        assert "already on file" in result.output


class CaseListAndShow:
    def test_list(self, runner: CliRunner, register: str) -> None:
        add_mix(runner, register)
        result = run(runner, register, "mix", "list")
        assert "4000P-57" in result.output
        assert "w/cm" in result.output

    def test_list_by_plant(self, runner: CliRunner, register: str) -> None:
        add_mix(runner, register, plant="PL-1")
        assert "4000P-57" in run(runner, register, "mix", "list", "--plant", "PL-1").output
        assert "4000P-57" not in run(runner, register, "mix", "list", "--plant", "PL-2").output

    def test_show(self, runner: CliRunner, register: str) -> None:
        add_mix(runner, register)
        result = run(runner, register, "mix", "show", "4000p 57")
        assert "cementitious" in result.output
        assert "CEM-I" in result.output
        assert "AD-AE" in result.output

    def test_show_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mix", "show", "4000P-58")
        assert result.exit_code != 0

    def test_revisions(self, runner: CliRunner, register: str) -> None:
        add_mix(runner, register)
        result = run(runner, register, "mix", "revisions", "4000P-57")
        assert "rev" in result.output

    def test_revisions_of_an_unknown_mix(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "mix", "revisions", "4000P-58")
        assert result.exit_code != 0


class CaseCheck:
    def test_a_conforming_design(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        add_mix(runner, register)
        result = run(runner, register, "mix", "check", "4000P-57")
        assert result.exit_code == 0
        assert "closes" in result.output
        assert "no findings" in result.output

    def test_a_design_with_findings(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        run(
            runner,
            register,
            "mix",
            "add",
            "3000W-67",
            "Wall mix",
            "--strength",
            "3000 psi",
            "--nms",
            "1 in",
            "--slump",
            "4 in",
            "--air",
            "6.0",
            "--exposure",
            "F2 S1",
            "--charge",
            "CEM-I:cement:470",
            "--charge",
            "CA-57:coarse_aggregate:1780",
            "--charge",
            "FA-1:fine_aggregate:1255",
            "--charge",
            "W-1:water:250",
        )
        result = run(runner, register, "mix", "check", "3000W-67")
        assert result.exit_code != 0
        assert "STRENGTH_BELOW_FLOOR" in result.output


class CaseProportion:
    def test_it_prints_the_working(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        result = run(
            runner,
            register,
            "mix",
            "proportion",
            "--strength",
            "4800 psi",
            "--slump",
            "4 in",
            "--cement",
            "CEM-I",
            "--coarse",
            "CA-57",
            "--fine",
            "FA-1",
            "--water",
            "W-1",
        )
        assert result.exit_code == 0
        assert "water demand" in result.output
        assert "sand fills the remaining" in result.output
        assert "water/cementitious" in result.output

    def test_with_a_replacement(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        result = run(
            runner,
            register,
            "mix",
            "proportion",
            "--strength",
            "4800 psi",
            "--slump",
            "4 in",
            "--cement",
            "CEM-I",
            "--coarse",
            "CA-57",
            "--fine",
            "FA-1",
            "--water",
            "W-1",
            "--scm",
            "SCM-F",
            "--replacement",
            "20",
        )
        assert "SCM-F" in result.output

    def test_an_unknown_material(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        result = run(
            runner,
            register,
            "mix",
            "proportion",
            "--strength",
            "4800 psi",
            "--slump",
            "4 in",
            "--cement",
            "CEM-IX",
            "--coarse",
            "CA-57",
            "--fine",
            "FA-1",
            "--water",
            "W-1",
        )
        assert result.exit_code != 0

    def test_a_strength_outside_the_table(self, runner: CliRunner, register: str) -> None:
        stock_materials(runner, register)
        result = run(
            runner,
            register,
            "mix",
            "proportion",
            "--strength",
            "9000 psi",
            "--slump",
            "4 in",
            "--cement",
            "CEM-I",
            "--coarse",
            "CA-57",
            "--fine",
            "FA-1",
            "--water",
            "W-1",
        )
        assert result.exit_code != 0
        assert "outside the" in result.output
