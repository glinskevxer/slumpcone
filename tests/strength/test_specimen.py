from __future__ import annotations

from datetime import datetime

import pytest

from slumpcone.errors import ValidationError
from slumpcone.strength.specimen import (
    CureCondition,
    Specimen,
    SpecimenPurpose,
    SpecimenSize,
)
from slumpcone.units.quantity import Quantity

CAST = datetime(2024, 6, 12, 9, 20)


def specimen(**overrides: object) -> Specimen:
    fields: dict[str, object] = {
        "code": "C-4471-A",
        "set_code": "S-4471",
        "ticket_number": "881204",
        "cast_at": CAST,
    }
    fields.update(overrides)
    return Specimen(**fields)  # type: ignore[arg-type]


class CaseSize:
    def test_parse(self) -> None:
        assert SpecimenSize.parse("6x12") is SpecimenSize.CYL_6X12
        assert SpecimenSize.parse("4 by 8") is SpecimenSize.CYL_4X8
        assert SpecimenSize.parse("150X300") is SpecimenSize.CYL_150X300

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="specimen size"):
            SpecimenSize.parse("3x6")

    def test_nominal_dimensions(self) -> None:
        assert SpecimenSize.CYL_6X12.nominal_diameter == Quantity(6, "in")
        assert SpecimenSize.CYL_6X12.nominal_length == Quantity(12, "in")
        assert SpecimenSize.CYL_150X300.nominal_length == Quantity(300, "mm")

    def test_small_moulds(self) -> None:
        assert SpecimenSize.CYL_4X8.is_small
        assert SpecimenSize.CYL_100X200.is_small
        assert not SpecimenSize.CYL_6X12.is_small

    def test_a_small_mould_takes_three_to_make_a_test(self) -> None:
        assert SpecimenSize.CYL_4X8.specimens_per_test == 3
        assert SpecimenSize.CYL_100X200.specimens_per_test == 3
        assert SpecimenSize.CYL_6X12.specimens_per_test == 2
        assert SpecimenSize.CYL_150X300.specimens_per_test == 2

    def test_the_largest_aggregate_a_mould_takes(self) -> None:
        assert SpecimenSize.CYL_6X12.largest_aggregate == Quantity(2, "in")
        assert SpecimenSize.CYL_4X8.largest_aggregate.to("in").value == pytest.approx(
            1.333, abs=1e-3
        )

    def test_prints_its_own_value(self) -> None:
        assert str(SpecimenSize.CYL_4X8) == "4x8"


class CaseCure:
    def test_parse(self) -> None:
        assert CureCondition.parse("standard") is CureCondition.STANDARD
        assert CureCondition.parse("LAB") is CureCondition.STANDARD
        assert CureCondition.parse("job") is CureCondition.FIELD

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="cure condition"):
            CureCondition.parse("autoclave")

    def test_only_standard_cure_counts_for_acceptance(self) -> None:
        assert CureCondition.STANDARD.counts_for_acceptance
        assert not CureCondition.FIELD.counts_for_acceptance

    def test_prints_its_own_value(self) -> None:
        assert str(CureCondition.FIELD) == "field"


class CasePurpose:
    def test_parse(self) -> None:
        assert SpecimenPurpose.parse("acceptance") is SpecimenPurpose.ACCEPTANCE
        assert SpecimenPurpose.parse("form removal") is SpecimenPurpose.FORM_REMOVAL

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="specimen purpose"):
            SpecimenPurpose.parse("curiosity")

    def test_prints_its_own_value(self) -> None:
        assert str(SpecimenPurpose.INFORMATION) == "information"


class CaseSpecimen:
    def test_codes_are_normalised(self) -> None:
        built = specimen(code=" c 4471 a ", set_code="s 4471", ticket_number=" 881204 ")
        assert built.code == "C-4471-A"
        assert built.set_code == "S-4471"
        assert built.ticket_number == "881204"

    def test_a_non_positive_age_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="test age has to be positive"):
            specimen(age_days=0)

    def test_due_date(self) -> None:
        assert specimen().due_at == datetime(2024, 7, 10, 9, 20)

    def test_age_at_a_moment(self) -> None:
        assert specimen().age_at(datetime(2024, 6, 19, 9, 20)) == pytest.approx(7.0)

    def test_a_standard_cured_acceptance_specimen_counts(self) -> None:
        assert specimen().counts_for_acceptance

    def test_a_field_cured_specimen_does_not(self) -> None:
        assert not specimen(cure=CureCondition.FIELD).counts_for_acceptance

    def test_a_form_removal_specimen_does_not(self) -> None:
        assert not specimen(purpose=SpecimenPurpose.FORM_REMOVAL).counts_for_acceptance

    def test_a_mould_big_enough_for_the_aggregate(self) -> None:
        assert specimen(size=SpecimenSize.CYL_6X12).suits_aggregate(Quantity(1.5, "in"))

    def test_a_mould_too_small_for_the_aggregate(self) -> None:
        assert not specimen(size=SpecimenSize.CYL_4X8).suits_aggregate(Quantity(1.5, "in"))

    def test_a_one_inch_aggregate_fits_a_four_by_eight(self) -> None:
        assert specimen(size=SpecimenSize.CYL_4X8).suits_aggregate(Quantity(1.0, "in"))

    def test_a_non_length_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="is a length"):
            specimen().suits_aggregate(Quantity(1, "lb"))

    def test_describe(self) -> None:
        line = specimen().describe()
        assert "C-4471-A" in line
        assert "set S-4471" in line
        assert "ticket 881204" in line
        assert "4x8 standard" in line
        assert "due 2024-07-10" in line
