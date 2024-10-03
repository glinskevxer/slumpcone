from __future__ import annotations

from datetime import date

import pytest

from slumpcone.delivery.truck import Truck
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.certification import Certificate, CertificateKind
from slumpcone.materials.kinds import CementType, MaterialClass
from slumpcone.materials.spec import Material
from slumpcone.plant.plant import Plant
from slumpcone.plant.scale import Scale
from slumpcone.project.submittal import Submittal, SubmittalBasis
from slumpcone.report.compliance import (
    DueItem,
    DueKind,
    blocking,
    calendar,
    from_catalog,
    from_plant,
    from_submittals,
    from_trucks,
    overdue,
    render_calendar,
    render_compliance_report,
)
from slumpcone.units.quantity import Quantity

DAY = date(2024, 6, 12)


def catalog() -> MaterialCatalog:
    stock = MaterialCatalog()
    stock.add(
        Material(
            "CEM-I",
            "Portland",
            MaterialClass.CEMENT,
            cement_type=CementType.TYPE_II,
            specific_gravity=3.15,
        )
    )
    stock.certify(
        Certificate(
            "CEM-I",
            CertificateKind.MILL_CERTIFICATE,
            "MC-1",
            date(2024, 5, 20),
            date(2024, 7, 4),
        )
    )
    return stock


def plant() -> Plant:
    return Plant(
        "PL-1",
        "Northmoor",
        scales=(
            Scale(
                "SC-CEM",
                "Cement scale",
                Quantity(6000, "lb"),
                Quantity(1, "lb"),
                (MaterialClass.CEMENT,),
                date(2024, 3, 1),
            ),
        ),
        certification_expires=date(2024, 6, 30),
    )


def truck() -> Truck:
    return Truck("TR-114", Quantity(11, "yd3"), last_uniformity_test=date(2024, 5, 1))


def submittal() -> Submittal:
    return Submittal(
        "SUB-1",
        "P-2024-118",
        "SLAB",
        "4000P-57",
        1,
        date(2024, 4, 2),
        basis=SubmittalBasis.TRIAL_BATCH,
    ).approve(date(2024, 4, 10), days=100)


class CaseDueKind:
    def test_which_kinds_stop_the_plant(self) -> None:
        assert DueKind.SCALE_CALIBRATION.blocks_batching
        assert DueKind.MATERIAL_CERTIFICATE.blocks_batching
        assert not DueKind.MIX_SUBMITTAL.blocks_batching

    def test_prints_its_own_value(self) -> None:
        assert str(DueKind.MIXER_UNIFORMITY) == "mixer uniformity"


class CaseSources:
    def test_from_a_catalog(self) -> None:
        items = from_catalog(catalog(), DAY)
        assert items[0].kind is DueKind.MATERIAL_CERTIFICATE
        assert items[0].due_on == date(2024, 7, 4)
        assert "MC-1" in items[0].subject

    def test_a_certificate_not_yet_issued_is_left_out(self) -> None:
        assert from_catalog(catalog(), date(2024, 5, 1)) == ()

    def test_from_a_plant(self) -> None:
        kinds = [item.kind for item in from_plant(plant())]
        assert DueKind.PLANT_CERTIFICATION in kinds
        assert DueKind.SCALE_CALIBRATION in kinds

    def test_a_plant_with_no_certification_date(self) -> None:
        bare = Plant("PL-2", "Yard plant")
        assert from_plant(bare) == ()

    def test_from_trucks(self) -> None:
        items = from_trucks([truck()])
        assert items[0].kind is DueKind.MIXER_UNIFORMITY
        assert items[0].due_on == date(2025, 5, 1)

    def test_a_truck_never_tested_is_left_out(self) -> None:
        assert from_trucks([Truck("TR-9", Quantity(11, "yd3"))]) == ()

    def test_from_submittals(self) -> None:
        items = from_submittals([submittal()])
        assert items[0].kind is DueKind.MIX_SUBMITTAL
        assert "4000P-57 r1" in items[0].subject

    def test_an_unapproved_submittal_is_left_out(self) -> None:
        pending = Submittal("SUB-2", "P-1", "SLAB", "4000P-57", 1, date(2024, 4, 2))
        assert from_submittals([pending]) == ()


class CaseCalendar:
    def items(self) -> tuple[DueItem, ...]:
        return (
            *from_catalog(catalog(), DAY),
            *from_plant(plant()),
            *from_trucks([truck()]),
            *from_submittals([submittal()]),
        )

    def test_the_horizon_cuts_the_far_ones_off(self) -> None:
        upcoming = calendar(self.items(), DAY, horizon_days=45)
        assert all(item.due_on <= date(2024, 7, 27) for item in upcoming)
        assert not any(item.kind is DueKind.MIXER_UNIFORMITY for item in upcoming)

    def test_soonest_first(self) -> None:
        upcoming = calendar(self.items(), DAY)
        assert upcoming[0].due_on <= upcoming[-1].due_on

    def test_a_wider_horizon_takes_more(self) -> None:
        assert len(calendar(self.items(), DAY, horizon_days=400)) > len(
            calendar(self.items(), DAY)
        )

    def test_overdue(self) -> None:
        lapsed = overdue(self.items(), date(2024, 9, 1))
        assert any(item.kind is DueKind.SCALE_CALIBRATION for item in lapsed)

    def test_nothing_overdue_today(self) -> None:
        assert overdue(self.items(), DAY) == ()

    def test_blocking_leaves_out_the_submittal(self) -> None:
        lapsed = blocking(self.items(), date(2024, 9, 1))
        assert all(item.kind is not DueKind.MIX_SUBMITTAL for item in lapsed)


class CaseRendering:
    def test_the_table(self) -> None:
        text = render_calendar(from_plant(plant()), DAY)
        assert "due" in text.splitlines()[0]
        assert "PL-1" in text

    def test_days_remaining_goes_negative(self) -> None:
        item = DueItem(DueKind.SCALE_CALIBRATION, "PL-1 SC-CEM", date(2024, 6, 1))
        assert item.days_remaining(DAY) == -11
        assert item.is_overdue(DAY)
        assert "overdue" in item.describe(DAY)

    def test_describe_when_it_is_still_current(self) -> None:
        item = DueItem(DueKind.SCALE_CALIBRATION, "PL-1 SC-CEM", date(2024, 6, 30))
        assert "18 d" in item.describe(DAY)

    def test_the_whole_report(self) -> None:
        items = (*from_catalog(catalog(), DAY), *from_plant(plant()))
        text = render_compliance_report(items, DAY)
        assert "Compliance calendar to 45 days" in text
        assert "as at" in text
        assert "Overdue" in text

    @pytest.mark.parametrize("horizon", [10, 90])
    def test_the_horizon_appears_in_the_heading(self, horizon: int) -> None:
        text = render_compliance_report(from_plant(plant()), DAY, horizon_days=horizon)
        assert f"to {horizon} days" in text
