from __future__ import annotations

from datetime import date

import pytest

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.project.project import SpecifiedClass
from slumpcone.project.submittal import (
    Submittal,
    SubmittalBasis,
    SubmittalStatus,
    check_against_class,
)
from slumpcone.spec.exposure import ExposureSet
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from tests.factories import design, proportions

SUBMITTED = date(2024, 4, 2)


def submittal(**overrides: object) -> Submittal:
    fields: dict[str, object] = {
        "reference": "SUB-118-03",
        "project_code": "P-2024-118",
        "class_code": "SLAB",
        "mix_code": "4000P-57",
        "mix_revision": 1,
        "submitted_on": SUBMITTED,
        "required_average": Quantity(5200, "psi"),
    }
    fields.update(overrides)
    return Submittal(**fields)  # type: ignore[arg-type]


def a_class(**overrides: object) -> SpecifiedClass:
    fields: dict[str, object] = {
        "code": "SLAB",
        "specified_strength": Quantity(4000, "psi"),
        "exposure": ExposureSet.parse("F2 S1"),
        "nominal_max_size": Quantity(1.0, "in"),
    }
    fields.update(overrides)
    return SpecifiedClass(**fields)  # type: ignore[arg-type]


class CaseBasis:
    def test_parse(self) -> None:
        assert SubmittalBasis.parse("trial batch") is SubmittalBasis.TRIAL_BATCH
        assert SubmittalBasis.parse("FIELD_RECORD") is SubmittalBasis.FIELD_RECORD

    def test_parse_refuses_the_unknown(self) -> None:
        with pytest.raises(ValidationError, match="submittal basis"):
            SubmittalBasis.parse("a good feeling")

    def test_which_bases_need_a_required_average(self) -> None:
        assert SubmittalBasis.TRIAL_BATCH.needs_a_required_average
        assert SubmittalBasis.FIELD_RECORD.needs_a_required_average
        assert not SubmittalBasis.HISTORICAL_STRENGTH.needs_a_required_average


class CaseStatus:
    def test_only_approved_allows_batching(self) -> None:
        assert SubmittalStatus.APPROVED.allows_batching
        for other in (SubmittalStatus.SUBMITTED, SubmittalStatus.EXPIRED):
            assert not other.allows_batching

    def test_settled_states(self) -> None:
        assert SubmittalStatus.REJECTED.is_settled
        assert SubmittalStatus.WITHDRAWN.is_settled
        assert not SubmittalStatus.SUBMITTED.is_settled
        assert not SubmittalStatus.DRAFT.is_settled

    def test_prints_its_own_value(self) -> None:
        assert str(SubmittalStatus.APPROVED) == "approved"


class CaseConstruction:
    def test_codes_are_normalised(self) -> None:
        built = submittal(reference=" sub 118 03 ", project_code="p 2024 118")
        assert built.reference == "SUB-118-03"
        assert built.project_code == "P-2024-118"

    def test_the_revision_starts_at_one(self) -> None:
        with pytest.raises(ValidationError, match="revision starts at one"):
            submittal(mix_revision=0)

    def test_the_required_average_is_checked(self) -> None:
        with pytest.raises(ValidationError, match="is a pressure"):
            submittal(required_average=Quantity(5200, "lb"))
        with pytest.raises(ValidationError, match="has to be positive"):
            submittal(required_average=Quantity(0, "psi"))

    def test_a_decision_before_submission_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="decided before"):
            submittal(decided_on=date(2024, 4, 1))

    def test_an_expiry_before_the_decision_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="expire before"):
            submittal(decided_on=date(2024, 4, 10), expires_on=date(2024, 4, 5))

    def test_the_mix_identity(self) -> None:
        assert submittal().mix_identity == "4000P-57 r1"


class CaseDecisions:
    def test_approving(self) -> None:
        approved = submittal().approve(date(2024, 4, 10), reviewer="County engineer")
        assert approved.status is SubmittalStatus.APPROVED
        assert approved.decided_on == date(2024, 4, 10)
        assert approved.expires_on == date(2025, 4, 10)
        assert approved.reviewer == "County engineer"

    def test_the_approval_term_is_adjustable(self) -> None:
        approved = submittal().approve(date(2024, 4, 10), days=90)
        assert approved.expires_on == date(2024, 7, 9)

    def test_a_non_positive_term_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="term has to be positive"):
            submittal().approve(date(2024, 4, 10), days=0)

    def test_rejecting(self) -> None:
        rejected = submittal().reject(date(2024, 4, 10), comments="air too low")
        assert rejected.status is SubmittalStatus.REJECTED
        assert rejected.comments == "air too low"
        assert rejected.expires_on is None

    def test_a_settled_submittal_cannot_be_decided_again(self) -> None:
        approved = submittal().approve(date(2024, 4, 10))
        with pytest.raises(RuleViolationError, match="SUBMITTAL_SETTLED"):
            approved.approve(date(2024, 5, 1))
        with pytest.raises(RuleViolationError):
            approved.reject(date(2024, 5, 1))


class CaseValidity:
    approved = submittal().approve(date(2024, 4, 10), days=365)

    def test_valid_inside_the_window(self) -> None:
        assert self.approved.is_valid_on(date(2024, 6, 12))
        assert self.approved.status_on(date(2024, 6, 12)) is SubmittalStatus.APPROVED

    def test_not_valid_before_the_decision(self) -> None:
        assert not self.approved.is_valid_on(date(2024, 4, 5))

    def test_valid_on_the_expiry_day(self) -> None:
        assert self.approved.is_valid_on(date(2025, 4, 10))

    def test_expired_the_day_after(self) -> None:
        assert self.approved.status_on(date(2025, 4, 11)) is SubmittalStatus.EXPIRED
        assert not self.approved.is_valid_on(date(2025, 4, 11))

    def test_an_approval_with_no_expiry_never_lapses(self) -> None:
        forever = submittal(status=SubmittalStatus.APPROVED, decided_on=date(2024, 4, 10))
        assert forever.is_valid_on(date(2030, 1, 1))

    def test_a_submitted_one_is_not_valid(self) -> None:
        assert not submittal().is_valid_on(date(2024, 6, 12))

    def test_describe(self) -> None:
        line = self.approved.describe(date(2025, 4, 11))
        assert "SUB-118-03" in line
        assert "P-2024-118/SLAB" in line
        assert "4000P-57 r1" in line
        assert "expired" in line

    def test_describe_without_a_date(self) -> None:
        assert "approved" in self.approved.describe()


class CaseCheckAgainstClass:
    def test_a_conforming_design(self) -> None:
        assert check_against_class(design(), a_class()) == ()

    def test_too_weak_for_the_class(self) -> None:
        findings = check_against_class(
            design(specified_strength=Quantity(3000, "psi")), a_class()
        )
        assert any("the class needs" in finding for finding in findings)

    def test_the_wrong_test_age(self) -> None:
        findings = check_against_class(design(test_age_days=56), a_class())
        assert any("the class tests at 28" in finding for finding in findings)

    def test_the_ratio_is_too_high(self) -> None:
        findings = check_against_class(
            design(proportions=proportions(water_content=300.0)), a_class()
        )
        assert any("the class allows 0.45" in finding for finding in findings)

    def test_the_cementitious_floor(self) -> None:
        findings = check_against_class(design(), a_class(min_cementitious=Quantity(650, "lb")))
        assert any("cementitious content" in finding for finding in findings)

    def test_the_aggregate_is_too_big(self) -> None:
        findings = check_against_class(design(nominal_max_size=Quantity(1.5, "in")), a_class())
        assert any("aggregate is" in finding for finding in findings)

    def test_the_slump_target_is_outside_the_class_band(self) -> None:
        findings = check_against_class(design(), a_class(slump_band=Band.between(1.0, 3.0)))
        assert any("slump target" in finding for finding in findings)

    def test_the_design_air_is_outside_the_class_band(self) -> None:
        findings = check_against_class(design(), a_class(air_band=Band.between(2.0, 4.0)))
        assert any("design air" in finding for finding in findings)

    def test_several_findings_at_once(self) -> None:
        findings = check_against_class(
            design(specified_strength=Quantity(3000, "psi"), test_age_days=56),
            a_class(min_cementitious=Quantity(650, "lb")),
        )
        assert len(findings) == 3
