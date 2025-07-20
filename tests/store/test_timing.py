from __future__ import annotations

import pytest

from slumpcone.demo import seed
from slumpcone.register import Register
from slumpcone.store.timing import (
    PROBES,
    PlanReading,
    Probe,
    run_all,
    run_probe,
    unclean,
)


@pytest.fixture()
def seeded() -> Register:
    register = Register.in_memory()
    seed(register)
    return register


class CaseProbes:
    def test_every_shipped_probe_uses_an_index(self, seeded: Register) -> None:
        assert unclean(run_all(seeded.database)) == ()

    def test_every_probe_names_at_least_one_search(self, seeded: Register) -> None:
        for reading in run_all(seeded.database):
            assert reading.searched, reading.name

    def test_there_is_a_reading_per_probe(self, seeded: Register) -> None:
        assert len(run_all(seeded.database)) == len(PROBES)

    def test_the_probes_have_distinct_names(self) -> None:
        names = [probe.name for probe in PROBES]
        assert len(set(names)) == len(names)

    def test_a_timing_comes_back(self, seeded: Register) -> None:
        assert all(one.milliseconds >= 0.0 for one in run_all(seeded.database))

    def test_the_row_count_is_the_real_one(self, seeded: Register) -> None:
        probe = next(one for one in PROBES if one.name == "tickets in a window")
        assert run_probe(seeded.database, probe).rows == 4


class CaseCatchingAScan:
    def test_a_query_with_no_index_is_caught(self, seeded: Register) -> None:
        probe = Probe(
            "notes on a ticket",
            "SELECT * FROM batch_ticket WHERE notes = ?",
            ("nothing",),
        )
        reading = run_probe(seeded.database, probe)
        assert not reading.is_clean
        assert "batch_ticket" in reading.unexpected_scans

    def test_a_scan_can_be_allowed(self, seeded: Register) -> None:
        probe = Probe(
            "notes on a ticket",
            "SELECT * FROM batch_ticket WHERE notes = ?",
            ("nothing",),
            frozenset({"batch_ticket"}),
        )
        assert run_probe(seeded.database, probe).is_clean

    def test_the_describe_names_the_table(self, seeded: Register) -> None:
        probe = Probe(
            "notes on a ticket",
            "SELECT * FROM batch_ticket WHERE notes = ?",
            ("nothing",),
        )
        assert "scans batch_ticket" in run_probe(seeded.database, probe).describe()

    def test_a_clean_reading_describes_as_ok(self, seeded: Register) -> None:
        probe = next(one for one in PROBES if one.name == "tickets in a window")
        assert "ok" in run_probe(seeded.database, probe).describe()

    def test_unclean_picks_only_the_bad(self, seeded: Register) -> None:
        bad = Probe("bad", "SELECT * FROM batch_ticket WHERE notes = ?", ("x",))
        good = next(one for one in PROBES if one.name == "tickets in a window")
        readings = [run_probe(seeded.database, one) for one in (good, bad)]
        assert [one.name for one in unclean(readings)] == ["bad"]

    def test_nothing_to_look_at(self) -> None:
        assert unclean([]) == ()


class CaseTheTwoIndexesThisFound:
    def test_a_window_of_tickets_searches(self, seeded: Register) -> None:
        probe = next(one for one in PROBES if one.name == "tickets in a window")
        reading = run_probe(seeded.database, probe)
        assert "batch_ticket" in reading.searched
        assert reading.scanned == ()

    def test_certificates_by_expiry_searches(self, seeded: Register) -> None:
        probe = next(one for one in PROBES if one.name == "certificates by expiry")
        reading = run_probe(seeded.database, probe)
        assert "material_certificate" in reading.searched

    def test_the_indexes_are_on_file(self, seeded: Register) -> None:
        rows = seeded.database.query(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name IN (?, ?)",
            ("ticket_by_date", "certificate_by_expiry"),
        )
        assert len(rows) == 2


def test_a_reading_with_no_allowance_is_dirty_on_any_scan() -> None:
    reading = PlanReading("x", 1.0, 0, ("batch_ticket",), ())
    assert not reading.is_clean
    assert reading.unexpected_scans == ("batch_ticket",)
