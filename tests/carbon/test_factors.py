from __future__ import annotations

from datetime import date

import pytest

from slumpcone.carbon.factors import (
    DEFAULT_FACTORS,
    CarbonError,
    EmissionFactor,
    FactorBook,
    Provenance,
    Stage,
)
from slumpcone.materials.kinds import MaterialClass
from slumpcone.units.quantity import Quantity

TODAY = date(2024, 6, 12)


def factor(
    code: str = "OPC",
    value: float = 0.922,
    *,
    stage: Stage = Stage.A1_A3,
    provenance: Provenance = Provenance.INDUSTRY_AVERAGE,
    source: str = "",
    published_on: date | None = None,
) -> EmissionFactor:
    return EmissionFactor(
        code, MaterialClass.CEMENT, value, stage, provenance, source, published_on
    )


class CaseFactor:
    def test_it_holds_what_it_was_given(self) -> None:
        one = factor()
        assert one.material_code == "OPC"
        assert one.kg_co2e_per_kg == pytest.approx(0.922)
        assert one.stage is Stage.A1_A3

    def test_the_code_is_normalised(self) -> None:
        assert factor(" opc ").material_code == "OPC"

    def test_a_negative_factor_is_refused(self) -> None:
        with pytest.raises(CarbonError) as caught:
            factor(value=-0.1)
        assert caught.value.code == "CARBON_FACTOR_NEGATIVE"

    def test_zero_is_allowed(self) -> None:
        assert factor(value=0.0).kg_co2e_per_kg == pytest.approx(0.0)

    def test_an_epd_has_to_name_its_document(self) -> None:
        with pytest.raises(CarbonError) as caught:
            factor(provenance=Provenance.PRODUCT_EPD)
        assert caught.value.code == "CARBON_EPD_WITHOUT_SOURCE"

    def test_an_epd_with_a_document_is_fine(self) -> None:
        one = factor(provenance=Provenance.PRODUCT_EPD, source="EPD 4471")
        assert one.provenance.is_declarable

    def test_an_industry_average_is_not_declarable(self) -> None:
        assert not factor().provenance.is_declarable

    def test_emissions_convert_the_mass(self) -> None:
        # A pound is 0.45359237 kg.
        assert factor(value=1.0).emissions(Quantity(1.0, "lb")) == pytest.approx(0.45359237)

    def test_emissions_of_nothing(self) -> None:
        assert factor().emissions(Quantity(0.0, "lb")) == pytest.approx(0.0)

    def test_describe_names_the_source_when_there_is_one(self) -> None:
        assert (
            "EPD 4471"
            in factor(provenance=Provenance.PRODUCT_EPD, source="EPD 4471").describe()
        )

    def test_describe_leaves_out_an_empty_source(self) -> None:
        assert factor().describe().endswith("industry average)")


class CaseStaleness:
    def test_a_factor_with_no_date_cannot_be_shown_current(self) -> None:
        assert factor().is_stale(TODAY)

    def test_a_recent_declaration_is_current(self) -> None:
        assert not factor(published_on=date(2023, 1, 1)).is_stale(TODAY)

    def test_a_six_year_old_declaration_is_stale(self) -> None:
        assert factor(published_on=date(2018, 1, 1)).is_stale(TODAY)

    def test_the_window_can_be_tightened(self) -> None:
        one = factor(published_on=date(2023, 1, 1))
        assert one.is_stale(TODAY, years=1)


class CaseStages:
    def test_every_stage_has_a_label(self) -> None:
        for stage in Stage:
            assert stage.label

    def test_the_name_reads_as_the_lettering(self) -> None:
        assert str(Stage.A1_A3) == "A1-A3"

    def test_the_cradle_to_gate_label_says_so(self) -> None:
        assert "cradle to gate" in Stage.A1_A3.label


class CaseBook:
    def test_an_empty_book(self) -> None:
        book = FactorBook()
        assert len(book) == 0
        assert not book.has("OPC")

    def test_defaults_carry_the_common_materials(self) -> None:
        book = FactorBook.defaults()
        assert len(book) == len(DEFAULT_FACTORS)
        assert book.has("OPC")
        assert book.has("FLYASH")

    def test_a_lookup(self) -> None:
        book = FactorBook.defaults()
        assert book.get("opc").kg_co2e_per_kg == pytest.approx(0.922)

    def test_a_material_with_no_factor(self) -> None:
        with pytest.raises(CarbonError) as caught:
            FactorBook.defaults().get("UNOBTAINIUM")
        assert caught.value.code == "CARBON_NO_FACTOR"

    def test_adding_replaces(self) -> None:
        book = FactorBook.defaults()
        book.add(factor("OPC", 0.700))
        assert book.get("OPC").kg_co2e_per_kg == pytest.approx(0.700)
        assert len(book) == len(DEFAULT_FACTORS)

    def test_membership(self) -> None:
        book = FactorBook.defaults()
        assert "OPC" in book
        assert 7 not in book

    def test_missing_keeps_the_order_asked(self) -> None:
        book = FactorBook.defaults()
        assert book.missing(["OPC", "ZZ", "FLYASH", "YY"]) == ("ZZ", "YY")

    def test_nothing_missing(self) -> None:
        assert FactorBook.defaults().missing(["OPC"]) == ()

    def test_stale_is_sorted_by_code(self) -> None:
        book = FactorBook([factor("ZZ"), factor("AA")])
        assert [one.material_code for one in book.stale(TODAY)] == ["AA", "ZZ"]

    def test_a_current_declaration_is_not_stale(self) -> None:
        book = FactorBook([factor("AA", published_on=date(2023, 1, 1))])
        assert book.stale(TODAY) == ()

    def test_declarable_picks_the_epds(self) -> None:
        book = FactorBook(
            [
                factor("AA", provenance=Provenance.PRODUCT_EPD, source="EPD 1"),
                factor("BB"),
            ]
        )
        assert [one.material_code for one in book.declarable()] == ["AA"]

    def test_the_shipped_defaults_are_not_declarable(self) -> None:
        assert FactorBook.defaults().declarable() == ()

    def test_a_view_of_the_whole_book(self) -> None:
        book = FactorBook.defaults()
        view = book.as_mapping()
        assert view["OPC"].material_code == "OPC"
        assert len(view) == len(book)

    def test_the_view_is_a_copy(self) -> None:
        book = FactorBook.defaults()
        view = dict(book.as_mapping())
        view.pop("OPC")
        assert book.has("OPC")


class CaseStageAgreement:
    def test_one_stage_throughout(self) -> None:
        assert FactorBook.defaults().same_stage() is Stage.A1_A3

    def test_an_empty_book_has_no_stage(self) -> None:
        with pytest.raises(CarbonError) as caught:
            FactorBook().same_stage()
        assert caught.value.code == "CARBON_EMPTY_BOOK"

    def test_a_mixed_book_refuses_to_be_totalled(self) -> None:
        book = FactorBook([factor("AA"), factor("BB", stage=Stage.A4)])
        with pytest.raises(CarbonError) as caught:
            book.same_stage()
        assert caught.value.code == "CARBON_MIXED_STAGES"

    def test_the_refusal_names_both_stages(self) -> None:
        book = FactorBook([factor("AA"), factor("BB", stage=Stage.A4)])
        with pytest.raises(CarbonError) as caught:
            book.same_stage()
        assert "A1-A3" in str(caught.value)
        assert "A4" in str(caught.value)


def test_cement_carries_far_more_than_aggregate() -> None:
    book = FactorBook.defaults()
    assert book.get("OPC").kg_co2e_per_kg > 50 * book.get("COARSE").kg_co2e_per_kg


def test_a_limestone_cement_carries_less_than_a_plain_one() -> None:
    book = FactorBook.defaults()
    assert book.get("PLC").kg_co2e_per_kg < book.get("OPC").kg_co2e_per_kg
