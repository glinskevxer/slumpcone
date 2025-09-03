from __future__ import annotations

from datetime import date, timedelta

import pytest

from slumpcone.demo import DEMO_DAY, seed
from slumpcone.doctor import Finding, Level, Report, examine
from slumpcone.people.certification import Certification, Grade, Technician
from slumpcone.percent import Percent
from slumpcone.plant.probe import ProbeCheck
from slumpcone.register import Register


@pytest.fixture()
def bare() -> Register:
    return Register.in_memory()


@pytest.fixture()
def seeded() -> Register:
    register = Register.in_memory()
    seed(register)
    return register


class CaseAnEmptyRegister:
    def test_it_is_well(self, bare: Register) -> None:
        assert examine(bare, DEMO_DAY).is_well

    def test_it_says_nothing_is_on_file(self, bare: Register) -> None:
        report = examine(bare, DEMO_DAY)
        notes = report.of_level(Level.NOTE)
        assert any("no technicians on file" in one.detail for one in notes)

    def test_a_note_does_not_stop_work(self, bare: Register) -> None:
        assert examine(bare, DEMO_DAY).is_well
        assert not Level.NOTE.stops_work

    def test_the_checks_are_counted(self, bare: Register) -> None:
        assert examine(bare, DEMO_DAY).checks_run == 3


class CaseTheDemoPlant:
    def test_the_bad_probe_is_a_failure(self, seeded: Register) -> None:
        report = examine(seeded, DEMO_DAY)
        assert any("MP-2" in one.detail for one in report.failures)

    def test_and_it_stops_work(self, seeded: Register) -> None:
        assert not examine(seeded, DEMO_DAY).is_well

    def test_the_card_running_out_is_a_warning(self, seeded: Register) -> None:
        report = examine(seeded, DEMO_DAY)
        assert any("ACI-2044" in one.detail for one in report.warnings)

    def test_the_crew_covers_every_test(self, seeded: Register) -> None:
        report = examine(seeded, DEMO_DAY)
        assert not any("nobody may run" in one.detail for one in report.findings)

    def test_after_the_card_lapses_it_becomes_a_failure(self, seeded: Register) -> None:
        later = date(2024, 7, 4)
        report = examine(seeded, later)
        assert any("ACI-2044" in one.detail for one in report.failures)

    def test_the_describe_counts_each_level(self, seeded: Register) -> None:
        text = examine(seeded, DEMO_DAY).describe()
        assert "failure(s)" in text
        assert "warning(s)" in text


class CaseTheRegisterItself:
    def test_a_sound_register_raises_nothing(self, seeded: Register) -> None:
        report = examine(seeded, DEMO_DAY)
        assert not any(one.check == "pages" for one in report.findings)
        assert not any(one.check == "references" for one in report.findings)

    def test_an_orphan_row_is_a_failure(self, seeded: Register) -> None:
        seeded.database.execute("PRAGMA foreign_keys = OFF")
        seeded.database.execute(
            "INSERT INTO plant_scale (plant_code, code, name, capacity_lb, "
            "graduation_lb, weighs, last_calibrated, calibration_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("PL-NOPE", "SC-9", "ghost", 20000.0, 5.0, "cement", "2024-01-01", 365),
        )
        report = examine(seeded, DEMO_DAY)
        assert any(one.check == "references" for one in report.failures)

    def test_a_broken_audit_chain_is_a_failure(self, seeded: Register) -> None:
        seeded.audit.record("j.mercer", "mix.save", "4000P-57")
        seeded.audit.record("j.mercer", "mix.save", "4000P-57")
        seeded.database.execute("UPDATE audit_event SET actor = ? WHERE id = 1", ("x",))
        report = examine(seeded, DEMO_DAY)
        assert any(one.check == "audit log" for one in report.failures)

    def test_the_query_plans_are_clean(self, seeded: Register) -> None:
        report = examine(seeded, DEMO_DAY)
        assert not any(one.check == "query plans" for one in report.findings)


class CaseTheCrew:
    def test_a_roster_that_covers_nothing_is_a_failure(self, bare: Register) -> None:
        bare.people.save(
            Technician(
                "T-1",
                "R. Okafor",
                (
                    Certification(
                        Grade.STRENGTH_TESTING,
                        "ACI-1",
                        date(2022, 1, 1),
                        date(2027, 1, 1),
                    ),
                ),
            )
        )
        report = examine(bare, DEMO_DAY)
        assert any("nobody may run" in one.detail for one in report.failures)

    def test_a_full_roster_raises_nothing(self, bare: Register) -> None:
        for code, grade in (("T-1", Grade.FIELD_GRADE_I), ("T-2", Grade.LAB_LEVEL_2)):
            bare.people.save(
                Technician(
                    code,
                    "Somebody",
                    (Certification(grade, f"ACI-{code}", date(2022, 1, 1), date(2027, 1, 1)),),
                )
            )
        report = examine(bare, DEMO_DAY)
        assert not any(one.check == "crew" for one in report.findings)


class CaseProbes:
    def test_an_overdue_probe_is_a_failure(self, seeded: Register) -> None:
        seeded.probes.save(
            ProbeCheck(
                "MP-3",
                DEMO_DAY - timedelta(days=120),
                Percent(4.5),
                Percent(4.4),
            ),
            "PL-1",
        )
        report = examine(seeded, DEMO_DAY)
        assert any("MP-3" in one.detail for one in report.failures)

    def test_a_probe_merely_due_is_a_warning(self, bare: Register) -> None:
        from slumpcone.demo import _plant, _silos

        bare.plants.save(_plant(), _silos())
        bare.probes.save(
            ProbeCheck(
                "MP-1",
                DEMO_DAY - timedelta(days=27),
                Percent(4.5),
                Percent(4.4),
            ),
            "PL-1",
        )
        report = examine(bare, DEMO_DAY)
        assert any("MP-1" in one.detail for one in report.warnings)


class CaseSorting:
    def test_failures_come_first(self, seeded: Register) -> None:
        levels = [one.level for one in examine(seeded, DEMO_DAY).findings]
        assert levels == sorted(
            levels, key=lambda one: {Level.FAILURE: 0, Level.WARNING: 1, Level.NOTE: 2}[one]
        )

    def test_a_finding_describes(self) -> None:
        found = Finding(Level.FAILURE, "pages", "something is wrong")
        assert found.describe() == "[failure] pages: something is wrong"

    def test_a_level_reads_as_a_word(self) -> None:
        assert str(Level.WARNING) == "warning"

    def test_only_a_failure_stops_work(self) -> None:
        assert Level.FAILURE.stops_work
        assert not Level.WARNING.stops_work

    def test_an_empty_report(self) -> None:
        report = Report(DEMO_DAY, (), 3)
        assert report.is_well
        assert "nothing found" in report.describe()
