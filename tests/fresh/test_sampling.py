from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.fresh.sampling import (
    EXCLUDED_END,
    Sample,
    check_sample,
    is_acceptance_sample,
)
from slumpcone.units.quantity import Quantity


def sample(**overrides: object) -> Sample:
    fields: dict[str, object] = {
        "ticket_number": "881204",
        "load_volume": Quantity(9, "yd3"),
        "discharged_before": Quantity(3, "yd3"),
        "portions": 2,
        "portion_span_minutes": 6.0,
        "start_delay_minutes": 3.0,
    }
    fields.update(overrides)
    return Sample(**fields)  # type: ignore[arg-type]


class CaseConstruction:
    def test_the_ticket_number_is_normalised(self) -> None:
        assert sample(ticket_number=" 881204 ").ticket_number == "881204"

    def test_the_volumes_have_to_be_volumes(self) -> None:
        with pytest.raises(ValidationError, match="load_volume is a volume"):
            sample(load_volume=Quantity(9, "lb"))
        with pytest.raises(ValidationError, match="discharged_before is a volume"):
            sample(discharged_before=Quantity(3, "lb"))

    def test_negative_volumes_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot be negative"):
            sample(discharged_before=Quantity(-1, "yd3"))

    def test_a_load_with_no_volume_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="has to have a volume"):
            sample(load_volume=Quantity(0, "yd3"))

    def test_discharging_more_than_the_load_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="than the load held"):
            sample(discharged_before=Quantity(10, "yd3"))

    def test_zero_portions_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least one portion"):
            sample(portions=0)

    def test_negative_times_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="portion span"):
            sample(portion_span_minutes=-1.0)
        with pytest.raises(ValidationError, match="start delay"):
            sample(start_delay_minutes=-1.0)


class CasePosition:
    def test_discharged_fraction(self) -> None:
        assert sample().discharged_fraction.value == pytest.approx(33.33, abs=0.01)

    def test_remaining(self) -> None:
        assert sample().remaining == Quantity(6, "yd3")

    def test_the_middle_of_the_load_is_neither_head_nor_tail(self) -> None:
        assert not sample().is_from_the_head
        assert not sample().is_from_the_tail

    def test_the_head(self) -> None:
        assert sample(discharged_before=Quantity(0.1, "yd3")).is_from_the_head

    def test_the_tail(self) -> None:
        assert sample(discharged_before=Quantity(8.9, "yd3")).is_from_the_tail

    def test_the_excluded_end(self) -> None:
        assert EXCLUDED_END.value == pytest.approx(0.25)
        assert not sample(discharged_before=Quantity(0.25, "yd3")).is_from_the_head


class CaseChecks:
    def test_a_good_sample_has_no_faults(self) -> None:
        assert check_sample(sample()) == ()
        assert is_acceptance_sample(sample())

    def test_a_sample_off_the_head(self) -> None:
        faults = check_sample(sample(discharged_before=Quantity(0.1, "yd3")))
        assert "does not count" in faults[0]
        assert not is_acceptance_sample(sample(discharged_before=Quantity(0.1, "yd3")))

    def test_a_sample_off_the_tail(self) -> None:
        faults = check_sample(sample(discharged_before=Quantity(8.9, "yd3")))
        assert any("left" in fault for fault in faults)

    def test_a_single_portion(self) -> None:
        faults = check_sample(sample(portions=1))
        assert any("at least 2 are needed" in fault for fault in faults)

    def test_portions_too_far_apart(self) -> None:
        faults = check_sample(sample(portion_span_minutes=18.0))
        assert any("minutes apart" in fault for fault in faults)

    def test_exactly_fifteen_minutes_apart_is_allowed(self) -> None:
        assert check_sample(sample(portion_span_minutes=15.0)) == ()

    def test_testing_started_too_late(self) -> None:
        faults = check_sample(sample(start_delay_minutes=7.0))
        assert any("testing began" in fault for fault in faults)

    def test_moulding_gets_longer(self) -> None:
        assert check_sample(sample(start_delay_minutes=7.0), for_specimens=True) == ()

    def test_moulding_has_its_own_limit(self) -> None:
        faults = check_sample(sample(start_delay_minutes=20.0), for_specimens=True)
        assert any("moulding began" in fault for fault in faults)

    def test_several_faults_come_back_together(self) -> None:
        faults = check_sample(
            sample(
                discharged_before=Quantity(0.1, "yd3"),
                portions=1,
                portion_span_minutes=20.0,
                start_delay_minutes=9.0,
            )
        )
        assert len(faults) == 4

    def test_a_tiny_load_can_be_head_and_tail_at_once(self) -> None:
        faults = check_sample(
            sample(load_volume=Quantity(0.4, "yd3"), discharged_before=Quantity(0.2, "yd3"))
        )
        assert len(faults) == 2
