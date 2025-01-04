from __future__ import annotations

from datetime import date, datetime

import pytest

from slumpcone.batching.engine import plan_batch
from slumpcone.batching.ticket import BatchTicket
from slumpcone.errors import ValidationError
from slumpcone.exporting import (
    materials_to_delimited,
    mix_from_json,
    mix_to_json,
    strength_to_delimited,
    tickets_to_delimited,
    to_delimited,
)
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from tests.batching.test_engine import papered_catalog, plant
from tests.factories import catalog, design
from tests.strength.test_acceptance import a_test

DAY = date(2024, 6, 12)


def ticket() -> BatchTicket:
    planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
    return BatchTicket.from_plan(
        planned,
        "881204",
        datetime(2024, 6, 12, 7, 42),
        truck_code="TR-114",
        purchaser="Ashfield Paving",
        project="Route 9, north",
    )


class CaseDelimited:
    def test_a_heading_row_and_a_body(self) -> None:
        text = to_delimited(("a", "b"), [[1, 2], [3, 4]])
        assert text.splitlines() == ["a,b", "1,2", "3,4"]

    def test_a_cell_with_a_comma_is_quoted(self) -> None:
        text = to_delimited(("a",), [["one, two"]])
        assert '"one, two"' in text

    def test_none_becomes_empty(self) -> None:
        assert to_delimited(("a", "b"), [[None, 2]]).splitlines()[1] == ",2"

    def test_another_delimiter(self) -> None:
        assert to_delimited(("a", "b"), [[1, 2]], delimiter=";").splitlines()[0] == "a;b"

    def test_no_columns_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one column"):
            to_delimited((), [])

    def test_a_short_row_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has 1 cells"):
            to_delimited(("a", "b"), [[1]])


class CaseTables:
    def test_tickets(self) -> None:
        text = tickets_to_delimited([ticket()])
        assert text.splitlines()[0].startswith("ticket,plant,mix")
        assert "881204" in text
        assert '"Route 9, north"' in text

    def test_an_empty_ticket_export_still_has_a_heading(self) -> None:
        assert tickets_to_delimited([]).strip() == (
            "ticket,plant,mix,revision,batched_at,volume_yd3,truck,purchaser,project,findings"
        )

    def test_strength_tests(self) -> None:
        text = strength_to_delimited([a_test("S-1", 4500.0)])
        assert "result_psi" in text.splitlines()[0]
        assert "S-1" in text

    def test_materials(self) -> None:
        text = materials_to_delimited(list(catalog()))
        assert "specific_gravity" in text.splitlines()[0]
        assert "CEM-I" in text

    def test_a_material_with_no_assay_exports_blank(self) -> None:
        text = materials_to_delimited(list(catalog()))
        assert ",," in text


class CaseMixJson:
    def test_it_round_trips(self) -> None:
        original = design()
        rebuilt = mix_from_json(mix_to_json(original))
        assert rebuilt.code == original.code
        assert rebuilt.revision == original.revision
        assert rebuilt.specified_strength == original.specified_strength
        assert rebuilt.water_cementitious_ratio == pytest.approx(
            original.water_cementitious_ratio
        )

    def test_the_charges_survive_in_order(self) -> None:
        rebuilt = mix_from_json(mix_to_json(design()))
        codes = [charge.material_code for charge in rebuilt.proportions.charges]
        assert codes == ["CEM-I", "SCM-F", "CA-57", "FA-1", "W-1"]

    def test_the_admixtures_survive(self) -> None:
        rebuilt = mix_from_json(mix_to_json(design()))
        assert [dose.material_code for dose in rebuilt.proportions.admixtures] == [
            "AD-AE",
            "AD-WR",
        ]

    def test_the_bands_survive(self) -> None:
        original = design(slump_band=Band.at_most(5.0))
        rebuilt = mix_from_json(mix_to_json(original))
        band = rebuilt.slump_tolerance()
        assert band.low is None
        assert band.high == pytest.approx(5.0)

    def test_the_exposure_survives(self) -> None:
        rebuilt = mix_from_json(mix_to_json(design()))
        assert str(rebuilt.exposure) == "F2 S1 W0 C0"

    def test_a_metric_design_survives(self) -> None:
        original = design(proportions=design().proportions.scaled_to("kg", "m3"))
        rebuilt = mix_from_json(mix_to_json(original))
        assert rebuilt.proportions.volume_unit == "m3"

    def test_the_document_is_sorted_and_indented(self) -> None:
        text = mix_to_json(design())
        assert text.startswith("{\n")
        assert '"code"' in text

    def test_something_that_is_not_json(self) -> None:
        with pytest.raises(ValidationError, match="not JSON"):
            mix_from_json("not json at all")

    def test_a_json_array(self) -> None:
        with pytest.raises(ValidationError, match="not an object"):
            mix_from_json("[1, 2, 3]")

    def test_another_kind_of_document(self) -> None:
        with pytest.raises(ValidationError, match="not a mix design document"):
            mix_from_json('{"document": "something.else", "version": 1}')

    def test_a_newer_version_is_refused_not_guessed_at(self) -> None:
        text = mix_to_json(design()).replace('"version": 1', '"version": 2')
        with pytest.raises(ValidationError, match="version 2"):
            mix_from_json(text)
