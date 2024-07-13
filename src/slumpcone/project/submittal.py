"""Submitting a mixture to a job, and what makes it acceptable there.

A mix design is not usable on a project until it has been submitted against one
of that project's classes and approved. The approval is against a class, not a
project, so the same mixture can be approved for the slab and rejected for the
footing on the same job.

Approvals expire. Most specifications tie them to the job, but the ones that
matter here tie them to a date, and a plant batching against an approval that
lapsed in March is producing unapproved concrete whether anyone notices or not.

What the check does *not* do is decide the mixture is good. It decides the
mixture satisfies the class as written. Whether the proportions will actually
reach the strength is what the required average strength and the test record
are for.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import Enum

from slumpcone.errors import RuleViolationError, ValidationError
from slumpcone.identity import normalize_code, normalize_name
from slumpcone.mixdesign.design import MixDesign
from slumpcone.project.project import SpecifiedClass
from slumpcone.units.quantity import Quantity

DEFAULT_APPROVAL_DAYS = 365


class SubmittalBasis(Enum):
    """What the submittal offers as evidence the mixture will perform."""

    FIELD_RECORD = "field_record"
    TRIAL_BATCH = "trial_batch"
    HISTORICAL_STRENGTH = "historical_strength"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, text: str) -> SubmittalBasis:
        """Read a basis off a submittal form."""
        key = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"unknown submittal basis {text!r}", field="basis")

    @property
    def needs_a_required_average(self) -> bool:
        """True when the basis has to state a required average strength.

        Historical strength documentation stands on the record itself, so it
        does not compute one. The other two do, by different routes, and a
        submittal on either of them with no number on it is incomplete.
        """
        return self is not SubmittalBasis.HISTORICAL_STRENGTH


class SubmittalStatus(Enum):
    """Where a submittal stands."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"

    def __str__(self) -> str:
        return self.value

    @property
    def allows_batching(self) -> bool:
        """True when a plant may batch against a submittal in this state."""
        return self is SubmittalStatus.APPROVED

    @property
    def is_settled(self) -> bool:
        """True when the reviewer has finished with it."""
        return self in {
            SubmittalStatus.APPROVED,
            SubmittalStatus.REJECTED,
            SubmittalStatus.WITHDRAWN,
            SubmittalStatus.EXPIRED,
        }


@dataclass(frozen=True, slots=True)
class Submittal:
    """One mixture offered against one class on one job."""

    reference: str
    project_code: str
    class_code: str
    mix_code: str
    mix_revision: int
    submitted_on: date
    basis: SubmittalBasis = SubmittalBasis.TRIAL_BATCH
    status: SubmittalStatus = SubmittalStatus.SUBMITTED
    required_average: Quantity | None = None
    decided_on: date | None = None
    expires_on: date | None = None
    reviewer: str | None = None
    comments: str = ""

    def __post_init__(self) -> None:
        for label, field_name in (
            ("reference", "submittal_reference"),
            ("project_code", "project_code"),
            ("class_code", "class_code"),
            ("mix_code", "mix_code"),
        ):
            object.__setattr__(
                self, label, normalize_code(getattr(self, label), field=field_name)
            )
        if self.reviewer is not None:
            object.__setattr__(
                self, "reviewer", normalize_name(self.reviewer, field="reviewer")
            )
        if self.mix_revision <= 0:
            raise ValidationError("a mix revision starts at one", field="mix_revision")
        if self.required_average is not None:
            if self.required_average.dimension.value != "pressure":
                raise ValidationError(
                    "a required average strength is a pressure", field="required_average"
                )
            if self.required_average.value <= 0.0:
                raise ValidationError(
                    "a required average strength has to be positive", field="required_average"
                )
        if self.decided_on is not None and self.decided_on < self.submitted_on:
            raise ValidationError(
                "a submittal cannot be decided before it was submitted", field="decided_on"
            )
        if (
            self.expires_on is not None
            and self.decided_on is not None
            and self.expires_on < self.decided_on
        ):
            raise ValidationError(
                "an approval cannot expire before it was given", field="expires_on"
            )

    @property
    def mix_identity(self) -> str:
        """The revision this submittal is for, as a ticket writes it."""
        return f"{self.mix_code} r{self.mix_revision}"

    def status_on(self, on: date) -> SubmittalStatus:
        """The status as of ``on``, taking expiry into account."""
        if self.status is not SubmittalStatus.APPROVED:
            return self.status
        if self.expires_on is not None and on > self.expires_on:
            return SubmittalStatus.EXPIRED
        return SubmittalStatus.APPROVED

    def is_valid_on(self, on: date) -> bool:
        """True when a plant may batch this mixture for this class on ``on``."""
        if self.decided_on is not None and on < self.decided_on:
            return False
        return self.status_on(on).allows_batching

    def approve(
        self,
        on: date,
        *,
        reviewer: str | None = None,
        days: int = DEFAULT_APPROVAL_DAYS,
        comments: str = "",
    ) -> Submittal:
        """Approve a submittal that has not been decided yet."""
        if self.status.is_settled:
            raise RuleViolationError(
                "SUBMITTAL_SETTLED",
                f"{self.reference} is already {self.status} and cannot be approved",
            )
        if days <= 0:
            raise ValidationError("an approval term has to be positive", field="days")
        return replace(
            self,
            status=SubmittalStatus.APPROVED,
            decided_on=on,
            expires_on=on + timedelta(days=days),
            reviewer=reviewer or self.reviewer,
            comments=comments or self.comments,
        )

    def reject(self, on: date, *, reviewer: str | None = None, comments: str = "") -> Submittal:
        """Reject a submittal that has not been decided yet."""
        if self.status.is_settled:
            raise RuleViolationError(
                "SUBMITTAL_SETTLED",
                f"{self.reference} is already {self.status} and cannot be rejected",
            )
        return replace(
            self,
            status=SubmittalStatus.REJECTED,
            decided_on=on,
            reviewer=reviewer or self.reviewer,
            comments=comments or self.comments,
        )

    def describe(self, on: date | None = None) -> str:
        """One line for a submittal register."""
        state = self.status if on is None else self.status_on(on)
        expiry = f" to {self.expires_on.isoformat()}" if self.expires_on else ""
        return (
            f"{self.reference}  {self.project_code}/{self.class_code}  "
            f"{self.mix_identity}  {self.basis}  {state}{expiry}"
        )


def check_against_class(design: MixDesign, specified: SpecifiedClass) -> tuple[str, ...]:
    """Every way ``design`` fails to satisfy ``specified``."""
    findings: list[str] = []
    floor = specified.effective_strength_floor
    if design.specified_strength < floor:
        findings.append(
            f"designed for {design.specified_strength.format(0)} and the class needs "
            f"{floor.format(0)}"
        )
    if design.test_age_days != specified.test_age_days:
        findings.append(
            f"designed at {design.test_age_days} days and the class tests at "
            f"{specified.test_age_days}"
        )
    limit = specified.effective_ratio_limit
    if limit is not None and design.water_cementitious_ratio > limit + 1e-9:
        findings.append(
            f"ratio is {design.water_cementitious_ratio:.3f} and the class allows {limit:.2f}"
        )
    if (
        specified.min_cementitious is not None
        and design.cementitious < specified.min_cementitious
    ):
        findings.append(
            f"cementitious content is {design.cementitious.format(0)} and the class needs "
            f"{specified.min_cementitious.format(0)}"
        )
    if (
        specified.nominal_max_size is not None
        and design.nominal_max_size > specified.nominal_max_size
    ):
        findings.append(
            f"aggregate is {design.nominal_max_size.format(2)} and the class allows "
            f"{specified.nominal_max_size.format(2)}"
        )
    if specified.slump_band is not None and not specified.slump_band.contains(
        design.slump_target.to("in").value
    ):
        findings.append(
            f"slump target {design.slump_target.format(1)} is outside the class band "
            f"{specified.slump_band.format(1)}"
        )
    if specified.air_band is not None and not specified.air_band.contains(
        design.design_air.value
    ):
        findings.append(
            f"design air {design.design_air.format(1)} is outside the class band "
            f"{specified.air_band.format(1)}"
        )
    return tuple(findings)
