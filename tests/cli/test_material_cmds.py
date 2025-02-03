from __future__ import annotations

from click.testing import CliRunner, Result

from tests.cli.support import run


def add_cement(runner: CliRunner, register: str) -> Result:
    return run(
        runner,
        register,
        "material",
        "add",
        "CEM-I",
        "Ashfield Type I/II",
        "--class",
        "cement",
        "--cement-type",
        "II",
        "--sg",
        "3.15",
        "--supplier",
        "Ashfield Cement",
    )


def add_stone(runner: CliRunner, register: str) -> Result:
    return run(
        runner,
        register,
        "material",
        "add",
        "CA-57",
        "Number 57 limestone",
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


class CaseAdd:
    def test_a_cement(self, runner: CliRunner, register: str) -> None:
        result = add_cement(runner, register)
        assert result.exit_code == 0
        assert "CEM-I" in result.output
        assert "cement II" in result.output

    def test_an_aggregate(self, runner: CliRunner, register: str) -> None:
        result = add_stone(runner, register)
        assert result.exit_code == 0
        assert "CA-57" in result.output

    def test_a_class_that_needs_a_field_it_was_not_given(
        self, runner: CliRunner, register: str
    ) -> None:
        result = run(
            runner, register, "material", "add", "CEM-I", "Portland", "--class", "cement"
        )
        assert result.exit_code != 0
        assert "cement needs a type" in result.output

    def test_an_unknown_class(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "material", "add", "X", "Thing", "--class", "gravel-ish")
        assert result.exit_code != 0
        assert "material class" in result.output

    def test_adding_twice_updates(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        add_cement(runner, register)
        listing = run(runner, register, "material", "list")
        assert listing.output.count("CEM-I") == 1


class CaseList:
    def test_an_empty_catalogue(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "material", "list")
        assert "code" in result.output

    def test_everything(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        add_stone(runner, register)
        result = run(runner, register, "material", "list")
        assert "CEM-I" in result.output
        assert "CA-57" in result.output

    def test_filtered_by_class(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        add_stone(runner, register)
        result = run(runner, register, "material", "list", "--class", "cement")
        assert "CEM-I" in result.output
        assert "CA-57" not in result.output


class CaseShow:
    def test_a_material_with_no_paper(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        result = run(runner, register, "material", "show", "cem i", "--on", "2024-06-12")
        assert "CEM-I" in result.output
        assert "mill_certificate" in result.output
        assert "missing" in result.output

    def test_an_unknown_material(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "material", "show", "CEM-IX")
        assert result.exit_code != 0
        assert "no material on file" in result.output

    def test_a_material_with_paper(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        run(
            runner,
            register,
            "material",
            "certify",
            "CEM-I",
            "MC-1",
            "--kind",
            "mill_certificate",
            "--issued",
            "2024-06-01",
        )
        result = run(runner, register, "material", "show", "CEM-I", "--on", "2024-06-12")
        assert "MC-1" in result.output
        assert "missing" in result.output
        assert "none" in result.output


class CaseCertify:
    def test_with_an_explicit_expiry(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        result = run(
            runner,
            register,
            "material",
            "certify",
            "CEM-I",
            "MC-1",
            "--kind",
            "mill_certificate",
            "--issued",
            "2024-06-01",
            "--expires",
            "2024-07-15",
        )
        assert result.exit_code == 0
        assert "2024-07-15" in result.output

    def test_with_a_term(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        result = run(
            runner,
            register,
            "material",
            "certify",
            "CEM-I",
            "MC-1",
            "--kind",
            "mill_certificate",
            "--issued",
            "2024-06-01",
            "--days",
            "30",
        )
        assert "2024-07-01" in result.output

    def test_a_bad_date(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        result = run(
            runner,
            register,
            "material",
            "certify",
            "CEM-I",
            "MC-1",
            "--kind",
            "mill_certificate",
            "--issued",
            "01/06/2024",
        )
        assert result.exit_code != 0
        assert "YYYY-MM-DD" in result.output

    def test_certifying_an_unknown_material(self, runner: CliRunner, register: str) -> None:
        result = run(
            runner,
            register,
            "material",
            "certify",
            "CEM-IX",
            "MC-1",
            "--kind",
            "mill_certificate",
            "--issued",
            "2024-06-01",
        )
        assert result.exit_code != 0


class CaseExpiringAndBlocked:
    def test_expiring(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        run(
            runner,
            register,
            "material",
            "certify",
            "CEM-I",
            "MC-1",
            "--kind",
            "mill_certificate",
            "--issued",
            "2024-06-01",
            "--expires",
            "2024-06-20",
        )
        result = run(runner, register, "material", "expiring", "--on", "2024-06-12")
        assert "MC-1" in result.output
        assert "8" in result.output

    def test_nothing_expiring(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        result = run(runner, register, "material", "expiring", "--on", "2024-06-12")
        assert "reference" in result.output

    def test_blocked(self, runner: CliRunner, register: str) -> None:
        add_cement(runner, register)
        result = run(runner, register, "material", "blocked", "--on", "2024-06-12")
        assert "CEM-I" in result.output
        assert "mill_certificate" in result.output

    def test_nothing_blocked(self, runner: CliRunner, register: str) -> None:
        result = run(runner, register, "material", "blocked", "--on", "2024-06-12")
        assert "material" in result.output
