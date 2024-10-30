from __future__ import annotations

import pytest

from slumpcone.demo import DEMO_DAY, DEMO_MIX, DEMO_PLANT, DEMO_PROJECT, seed
from slumpcone.fresh.acceptance import LoadOutcome, judge_load
from slumpcone.register import Register
from slumpcone.strength.acceptance import StrengthStatus, evaluate_strength
from slumpcone.units.quantity import Quantity


@pytest.fixture()
def seeded() -> Register:
    register = Register.in_memory()
    seed(register)
    return register


class CaseSeed:
    def test_it_reports_what_it_wrote(self) -> None:
        register = Register.in_memory()
        counts = seed(register)
        assert counts["materials"] == 7
        assert counts["tickets"] == 4
        assert counts["specimen sets"] == 3

    def test_the_materials_are_papered(self, seeded: Register) -> None:
        catalog = seeded.materials.load_catalog()
        for code in catalog.codes():
            assert catalog.is_batchable(code, DEMO_DAY)

    def test_the_plant_can_run(self, seeded: Register) -> None:
        assert seeded.plants.get(DEMO_PLANT).is_operable(DEMO_DAY)

    def test_the_silos_are_stocked(self, seeded: Register) -> None:
        assert len(seeded.plants.silos(DEMO_PLANT)) == 2

    def test_the_mix_is_on_file(self, seeded: Register) -> None:
        design = seeded.mixes.latest(DEMO_MIX)
        assert design.specified_strength == Quantity(4500, "psi")

    def test_the_project_is_on_file(self, seeded: Register) -> None:
        assert seeded.projects.get(DEMO_PROJECT).class_codes == ("SLAB",)


class CaseTheDaysWork:
    def test_four_tickets(self, seeded: Register) -> None:
        assert len(seeded.batches.between(DEMO_DAY, DEMO_DAY)) == 4

    def test_every_ticket_has_a_delivery(self, seeded: Register) -> None:
        for ticket in seeded.batches.between(DEMO_DAY, DEMO_DAY):
            assert seeded.deliveries.get(ticket.number).is_complete

    def test_one_load_fails_its_slump(self, seeded: Register) -> None:
        design = seeded.mixes.latest(DEMO_MIX)
        outcomes = []
        for ticket in seeded.batches.between(DEMO_DAY, DEMO_DAY):
            tests = seeded.fresh.for_ticket(ticket.number)
            outcomes.append(judge_load(ticket.number, tests, design).outcome)
        assert LoadOutcome.RETEST_DUE in outcomes
        assert outcomes.count(LoadOutcome.ACCEPTED) == 3

    def test_a_weight_drifts_out_of_tolerance(self, seeded: Register) -> None:
        findings = [
            result
            for ticket in seeded.batches.between(DEMO_DAY, DEMO_DAY)
            for result in ticket.out_of_tolerance
        ]
        assert findings

    def test_the_hauls_get_slower(self, seeded: Register) -> None:
        deliveries = seeded.deliveries.between(DEMO_DAY, DEMO_DAY)
        spans = [delivery.total_time for delivery in deliveries]
        assert spans[0] is not None and spans[-1] is not None
        assert spans[-1] > spans[0]


class CaseTheStrengthRecord:
    def test_three_sets_are_broken(self, seeded: Register) -> None:
        assert len(seeded.strength.tests_for_mix(DEMO_MIX)) == 3

    def test_the_record_asks_for_an_investigation(self, seeded: Register) -> None:
        tests = seeded.strength.tests_for_mix(DEMO_MIX)
        report = evaluate_strength(DEMO_MIX, tests, Quantity(4000, "psi"))
        assert report.status is StrengthStatus.INVESTIGATE
        assert report.low_tests

    def test_the_low_set_is_the_third_one(self, seeded: Register) -> None:
        tests = seeded.strength.tests_for_mix(DEMO_MIX)
        report = evaluate_strength(DEMO_MIX, tests, Quantity(4000, "psi"))
        assert report.low_tests[0].set_code == "S-4473"

    def test_it_can_be_seeded_twice_into_two_registers(self) -> None:
        first = Register.in_memory()
        second = Register.in_memory()
        seed(first)
        seed(second)
        assert first.batches.count() == second.batches.count()
