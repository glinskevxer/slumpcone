from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import NotFoundError, ValidationError
from slumpcone.project.project import Project, SpecifiedClass
from slumpcone.spec.exposure import ExposureSet
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


def a_class(code: str = "SLAB", **overrides: object) -> SpecifiedClass:
    fields: dict[str, object] = {
        "code": code,
        "specified_strength": Quantity(4000, "psi"),
        "exposure": ExposureSet.parse("F2 S1"),
        "slump_band": Band.symmetric(4.0, 1.0),
        "nominal_max_size": Quantity(1.0, "in"),
    }
    fields.update(overrides)
    return SpecifiedClass(**fields)  # type: ignore[arg-type]


def project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "code": "P-2024-118",
        "name": "Route 9 shoulder widening",
        "classes": (a_class(), a_class("FOOTING", exposure=ExposureSet.parse("S2"))),
        "owner": "County highways",
        "started_on": date(2024, 5, 1),
        "finished_on": date(2024, 11, 30),
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


class CaseSpecifiedClass:
    def test_the_code_is_normalised(self) -> None:
        assert a_class(code=" slab ").code == "SLAB"

    def test_the_strength_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            a_class(specified_strength=Quantity(4000, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            a_class(specified_strength=Quantity(0, "psi"))

    def test_the_test_age_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="test age has to be positive"):
            a_class(test_age_days=0)

    def test_the_optional_limits_are_checked(self) -> None:
        with pytest.raises(ValidationError, match="ratio limit has to be positive"):
            a_class(max_water_cementitious=0.0)
        with pytest.raises(ValidationError, match="cementitious floor is a mass"):
            a_class(min_cementitious=Quantity(500, "yd3"))
        with pytest.raises(ValidationError, match="nominal maximum size is a length"):
            a_class(nominal_max_size=Quantity(1, "lb"))

    def test_the_exposure_ratio_binds_when_the_drawings_are_silent(self) -> None:
        assert a_class().effective_ratio_limit == pytest.approx(0.45)

    def test_a_tighter_drawing_limit_wins(self) -> None:
        assert a_class(max_water_cementitious=0.40).effective_ratio_limit == pytest.approx(0.40)

    def test_a_looser_drawing_limit_does_not(self) -> None:
        assert a_class(max_water_cementitious=0.50).effective_ratio_limit == pytest.approx(0.45)

    def test_no_limit_at_all(self) -> None:
        assert a_class(exposure=ExposureSet()).effective_ratio_limit is None

    def test_the_exposure_can_raise_the_strength_floor(self) -> None:
        raised = a_class(specified_strength=Quantity(3000, "psi"))
        assert raised.effective_strength_floor == Quantity(4500, "psi")

    def test_a_high_specified_strength_wins(self) -> None:
        assert a_class(specified_strength=Quantity(6000, "psi")).effective_strength_floor == (
            Quantity(6000, "psi")
        )

    def test_describe(self) -> None:
        line = a_class().describe()
        assert "SLAB" in line
        assert "4000 psi at 28 d" in line
        assert "w/cm max 0.45" in line

    def test_describe_without_a_ratio_limit(self) -> None:
        assert "w/cm" not in a_class(exposure=ExposureSet()).describe()


class CaseProject:
    def test_names_are_normalised(self) -> None:
        built = project(code=" p 2024 118 ", name="  Route 9   shoulder ", owner=" County  ")
        assert built.code == "P-2024-118"
        assert built.name == "Route 9 shoulder"
        assert built.owner == "County"

    def test_a_repeated_class_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="appears twice"):
            project(classes=(a_class(), a_class()))

    def test_finishing_before_starting_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot finish before it starts"):
            project(finished_on=date(2024, 4, 1))

    def test_class_codes_are_sorted(self) -> None:
        assert project().class_codes == ("FOOTING", "SLAB")

    def test_a_class_by_code(self) -> None:
        assert project().specified_class("slab").specified_strength == Quantity(4000, "psi")

    def test_an_unknown_class_is_named(self) -> None:
        with pytest.raises(NotFoundError, match="WALL"):
            project().specified_class("WALL")

    def test_open_inside_the_window(self) -> None:
        assert project().is_open(date(2024, 6, 12))

    def test_closed_before_it_starts(self) -> None:
        assert not project().is_open(date(2024, 4, 30))

    def test_closed_after_it_finishes(self) -> None:
        assert not project().is_open(date(2024, 12, 1))

    def test_open_on_the_boundary_days(self) -> None:
        assert project().is_open(date(2024, 5, 1))
        assert project().is_open(date(2024, 11, 30))

    def test_a_project_with_no_dates_is_always_open(self) -> None:
        assert project(started_on=None, finished_on=None).is_open(date(2020, 1, 1))

    def test_the_unit_system_defaults_to_customary(self) -> None:
        assert project().unit_system is UnitSystem.CUSTOMARY

    def test_describe(self) -> None:
        line = project().describe()
        assert "P-2024-118" in line
        assert "County highways" in line
        assert "2 classes" in line
