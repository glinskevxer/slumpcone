from __future__ import annotations

from datetime import date

import pytest

from slumpcone.carbon.benchmark import BenchmarkClass, BenchmarkTable
from slumpcone.carbon.factors import CarbonError, EmissionFactor, Provenance, Stage
from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.register import Register
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

TODAY = date(2024, 6, 12)


@pytest.fixture()
def register() -> Register:
    return Register.in_memory()


def factor(
    code: str = "CEM-I",
    value: float = 0.922,
    *,
    provenance: Provenance = Provenance.INDUSTRY_AVERAGE,
    published: date | None = None,
) -> EmissionFactor:
    return EmissionFactor(
        code,
        MaterialClass.CEMENT,
        value,
        Stage.A1_A3,
        provenance,
        "EPD 4471" if provenance is Provenance.PRODUCT_EPD else "",
        published,
    )


class CaseFactors:
    def test_a_factor_round_trips(self, register: Register) -> None:
        register.carbon.save_factor(factor())
        assert register.carbon.factor("CEM-I") == factor()

    def test_every_field_survives(self, register: Register) -> None:
        one = factor(provenance=Provenance.PRODUCT_EPD, published=date(2023, 1, 1))
        register.carbon.save_factor(one)
        back = register.carbon.factor("CEM-I")
        assert back.provenance is Provenance.PRODUCT_EPD
        assert back.source == "EPD 4471"
        assert back.published_on == date(2023, 1, 1)

    def test_a_missing_date_stays_missing(self, register: Register) -> None:
        register.carbon.save_factor(factor())
        assert register.carbon.factor("CEM-I").published_on is None

    def test_saving_again_replaces_rather_than_colliding(self, register: Register) -> None:
        register.carbon.save_factor(factor())
        register.carbon.save_factor(factor(value=0.700))
        assert register.carbon.factor("CEM-I").kg_co2e_per_kg == pytest.approx(0.700)

    def test_an_unknown_factor(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.carbon.factor("CEM-I")

    def test_the_code_is_normalised(self, register: Register) -> None:
        register.carbon.save_factor(factor())
        assert register.carbon.factor(" cem-i ").material_code == "CEM-I"

    def test_forgetting_one(self, register: Register) -> None:
        register.carbon.save_factor(factor())
        register.carbon.forget_factor("CEM-I")
        with pytest.raises(NotFoundError):
            register.carbon.factor("CEM-I")

    def test_forgetting_one_that_is_not_there(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.carbon.forget_factor("CEM-I")


class CaseBook:
    def test_an_empty_register_makes_an_empty_book(self, register: Register) -> None:
        assert len(register.carbon.book()) == 0

    def test_the_book_carries_everything_filed(self, register: Register) -> None:
        register.carbon.save_factor(factor("CEM-I"))
        register.carbon.save_factor(
            EmissionFactor("CA-57", MaterialClass.COARSE_AGGREGATE, 0.0075)
        )
        book = register.carbon.book()
        assert len(book) == 2
        assert book.has("CA-57")

    def test_loading_the_defaults(self, register: Register) -> None:
        added = register.carbon.load_defaults()
        assert added > 0
        assert register.carbon.book().has("OPC")

    def test_loading_twice_adds_nothing_the_second_time(self, register: Register) -> None:
        register.carbon.load_defaults()
        assert register.carbon.load_defaults() == 0

    def test_the_defaults_leave_a_filed_factor_alone(self, register: Register) -> None:
        register.carbon.save_factor(factor("OPC", 0.100))
        register.carbon.load_defaults()
        assert register.carbon.factor("OPC").kg_co2e_per_kg == pytest.approx(0.100)

    def test_stale_factors(self, register: Register) -> None:
        register.carbon.save_factor(factor("CEM-I", published=date(2017, 1, 1)))
        register.carbon.save_factor(
            EmissionFactor(
                "CA-57",
                MaterialClass.COARSE_AGGREGATE,
                0.0075,
                published_on=date(2023, 1, 1),
            )
        )
        stale = register.carbon.stale_factors(TODAY)
        assert [one.material_code for one in stale] == ["CEM-I"]


class CaseDensities:
    def test_nothing_on_file(self, register: Register) -> None:
        assert register.carbon.densities() == {}

    def test_one_round_trips(self, register: Register) -> None:
        register.carbon.save_density("AD-AE", MassPerVolume(8.4, "lb", "gal"))
        assert register.carbon.densities()["AD-AE"] == MassPerVolume(8.4, "lb", "gal")

    def test_saving_again_replaces(self, register: Register) -> None:
        register.carbon.save_density("AD-AE", MassPerVolume(8.4, "lb", "gal"))
        register.carbon.save_density("AD-AE", MassPerVolume(9.0, "lb", "gal"))
        assert register.carbon.densities()["AD-AE"].value == pytest.approx(9.0)

    def test_the_units_survive(self, register: Register) -> None:
        register.carbon.save_density("AD-WR", MassPerVolume(1.19, "kg", "L"))
        back = register.carbon.densities()["AD-WR"]
        assert back.mass_unit == "kg"
        assert back.volume_unit == "L"


class CaseTables:
    def test_a_table_round_trips(self, register: Register) -> None:
        register.carbon.save_table("buy clean", BenchmarkTable.defaults().classes)
        back = register.carbon.table("buy clean")
        assert len(back.classes) == len(BenchmarkTable.defaults().classes)

    def test_the_rows_come_back_strongest_first(self, register: Register) -> None:
        register.carbon.save_table("buy clean", BenchmarkTable.defaults().classes)
        floors = [
            row.floor.to("psi").value for row in register.carbon.table("buy clean").classes
        ]
        assert floors == sorted(floors, reverse=True)

    def test_the_labels_survive(self, register: Register) -> None:
        register.carbon.save_table(
            "buy clean", [BenchmarkClass(Quantity(4000, "psi"), 307.0, "the four thousands")]
        )
        assert register.carbon.table("buy clean").classes[0].label == "the four thousands"

    def test_a_name_collision(self, register: Register) -> None:
        register.carbon.save_table("buy clean", BenchmarkTable.defaults().classes)
        with pytest.raises(ConflictError):
            register.carbon.save_table("buy clean", BenchmarkTable.defaults().classes)

    def test_two_tables_sit_side_by_side(self, register: Register) -> None:
        register.carbon.save_table("buy clean", BenchmarkTable.defaults().classes)
        register.carbon.save_table("state dot", BenchmarkTable.defaults().classes)
        assert register.carbon.table_names() == ("buy clean", "state dot")

    def test_an_unknown_table(self, register: Register) -> None:
        with pytest.raises(NotFoundError):
            register.carbon.table("buy clean")

    def test_a_table_with_no_rows_is_refused_before_anything_is_written(
        self, register: Register
    ) -> None:
        with pytest.raises(CarbonError) as caught:
            register.carbon.save_table("empty", [])
        assert caught.value.code == "BENCHMARK_EMPTY_TABLE"
        assert register.carbon.table_names() == ()

    def test_loading_the_default_table(self, register: Register) -> None:
        table = register.carbon.load_default_table()
        assert table.name == "national average"
        assert register.carbon.table_names() == ("national average",)

    def test_the_limit_reads_back_correctly(self, register: Register) -> None:
        register.carbon.load_default_table()
        table = register.carbon.table("national average")
        assert table.limit_for(Quantity(4200, "psi")).limit_kg_per_m3 == pytest.approx(307.0)


def test_the_health_check_counts_factors(register: Register) -> None:
    register.carbon.save_factor(factor())
    assert register.health().counts["emission_factor"] == 1
