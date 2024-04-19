from __future__ import annotations

from datetime import date

import pytest

from slumpcone.batching.engine import blocking_reasons, plan_batch
from slumpcone.batching.moisture import AggregateMoisture
from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.materials.catalog import MaterialCatalog
from slumpcone.materials.certification import Certificate, CertificateKind
from slumpcone.materials.kinds import MaterialClass
from slumpcone.percent import Percent
from slumpcone.plant.plant import Plant
from slumpcone.plant.scale import Scale
from slumpcone.units.quantity import Quantity
from tests.factories import catalog as bare_catalog
from tests.factories import design

DAY = date(2024, 6, 12)


def papered_catalog() -> MaterialCatalog:
    stock = bare_catalog()
    for material in stock:
        for kind in (
            CertificateKind.MILL_CERTIFICATE,
            CertificateKind.SOURCE_APPROVAL,
            CertificateKind.GRADATION,
            CertificateKind.CONFORMANCE_LETTER,
        ):
            stock.certify(
                Certificate(
                    material.code,
                    kind,
                    f"{material.code}-{kind.value[:4]}",
                    date(2024, 1, 1),
                    date(2024, 12, 31),
                )
            )
    return stock


def plant(**overrides: object) -> Plant:
    fields: dict[str, object] = {
        "code": "PL-1",
        "name": "Northmoor batch plant",
        "scales": (
            Scale(
                "SC-AGG",
                "Aggregate scale",
                Quantity(12000, "lb"),
                Quantity(2, "lb"),
                (MaterialClass.COARSE_AGGREGATE, MaterialClass.FINE_AGGREGATE),
                date(2024, 3, 1),
            ),
            Scale(
                "SC-CEM",
                "Cement scale",
                Quantity(6000, "lb"),
                Quantity(1, "lb"),
                (MaterialClass.CEMENT, MaterialClass.SCM),
                date(2024, 3, 1),
            ),
        ),
        "max_load": Quantity(11, "yd3"),
    }
    fields.update(overrides)
    return Plant(**fields)  # type: ignore[arg-type]


MOISTURES = {
    "CA-57": AggregateMoisture("CA-57", Percent(1.5), Percent(0.7)),
    "FA-1": AggregateMoisture("FA-1", Percent(5.0), Percent(1.4)),
}


class CaseBlockingReasons:
    def test_a_ready_plant_reports_nothing(self) -> None:
        assert (
            blocking_reasons(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
            == ()
        )

    def test_an_overdue_scale(self) -> None:
        reasons = blocking_reasons(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), date(2024, 10, 1)
        )
        assert any("calibration lapsed" in r for r in reasons)

    def test_a_load_over_the_plant_maximum(self) -> None:
        reasons = blocking_reasons(
            plant(), design(), papered_catalog(), Quantity(12, "yd3"), DAY
        )
        assert any("over the" in r for r in reasons)

    def test_a_material_with_no_paper(self) -> None:
        reasons = blocking_reasons(plant(), design(), bare_catalog(), Quantity(9, "yd3"), DAY)
        assert any("CEM-I has no current" in r for r in reasons)

    def test_an_admixture_with_no_paper(self) -> None:
        stock = papered_catalog()
        reasons = blocking_reasons(plant(), design(), stock, Quantity(9, "yd3"), DAY)
        assert reasons == ()

    def test_several_reasons_come_back_together(self) -> None:
        reasons = blocking_reasons(
            plant(), design(), bare_catalog(), Quantity(12, "yd3"), date(2024, 10, 1)
        )
        assert len(reasons) > 3


class CasePlanBatch:
    def plan(self, **overrides: object) -> object:
        return plan_batch(
            plant(),
            design(),
            papered_catalog(),
            Quantity(9, "yd3"),
            DAY,
            MOISTURES,
        )

    def test_a_refused_batch_names_every_reason(self) -> None:
        with pytest.raises(RuleViolationError) as caught:
            plan_batch(plant(), design(), bare_catalog(), Quantity(9, "yd3"), DAY)
        assert caught.value.code == "BATCH_REFUSED"
        assert "CEM-I" in caught.value.detail

    def test_every_charge_gets_a_line(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert len(planned.lines) == 5

    def test_the_cement_line_is_nine_times_the_design(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert planned.line("CEM-I").required == Quantity(4230, "lb")

    def test_the_aggregate_lines_carry_a_moisture_adjustment(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert planned.line("CA-57").moisture_adjustment.value > 0.0
        assert planned.line("CEM-I").moisture_adjustment.value == pytest.approx(0.0)

    def test_the_water_line_is_cut(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert planned.water_line.required < planned.water_line.design_weight

    def test_scales_are_assigned_by_class(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert planned.line("CEM-I").scale_code == "SC-CEM"
        assert planned.line("CA-57").scale_code == "SC-AGG"
        assert planned.line("W-1").scale_code is None

    def test_the_allowance_reflects_the_scale(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert planned.line("CEM-I").allowance.value == pytest.approx(42.3, abs=0.1)

    def test_admixture_lines_follow_the_binder(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        codes = [entry.material_code for entry in planned.admixture_lines]
        assert codes == ["AD-AE", "AD-WR"]
        assert planned.admixture_lines[0].charge.value == pytest.approx(60.912, abs=0.01)

    def test_the_total_is_everything_on_the_scales(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        assert planned.total_weight.value == pytest.approx(
            sum(entry.required.value for entry in planned.lines)
        )

    def test_no_moisture_readings_still_plans(self) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        assert planned.line("CA-57").moisture_adjustment.value == pytest.approx(0.0)

    def test_an_unknown_line_is_named(self) -> None:
        planned = plan_batch(plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY)
        with pytest.raises(ValidationError, match="not in this batch"):
            planned.line("CEM-III")

    def test_describe_prints_a_batch_sheet(self) -> None:
        planned = plan_batch(
            plant(), design(), papered_catalog(), Quantity(9, "yd3"), DAY, MOISTURES
        )
        text = planned.describe()
        assert "4000P-57 r1 at PL-1" in text
        assert "9.00 yd3 on 2024-06-12" in text
        assert "SC-CEM" in text
        assert "metered" in text

    def test_a_plant_with_no_scales_still_plans(self) -> None:
        planned = plan_batch(
            Plant("PL-9", "Portable plant"),
            design(),
            papered_catalog(),
            Quantity(9, "yd3"),
            DAY,
        )
        assert planned.line("CEM-I").scale_code is None
        assert planned.line("CEM-I").allowance.value == pytest.approx(42.3, abs=0.1)
