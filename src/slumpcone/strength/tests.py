"""A strength test, which is never one cylinder.

ACI is specific about this and specifications repeat it: a strength test is the
average of the companion specimens from one sample, broken at the same age. One
cylinder is a break, not a test, and a single low break has no standing on its
own.

What the average hides is how far apart the companions were. C39's precision
statement puts a limit on the spread between cylinders from one sample, and a
set that exceeds it is telling you something about the lab rather than about
the concrete. The average is still the test; the spread is a separate finding.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.strength.breaks import BreakResult
from slumpcone.strength.specimen import CureCondition, SpecimenPurpose, SpecimenSize
from slumpcone.units.quantity import Quantity

# The spread C39's single-operator precision allows between companions from one
# sample, as a share of their average.
RANGE_LIMIT_TWO = Percent(8.0)
RANGE_LIMIT_THREE = Percent(9.5)

# How far apart the companions' ages may be and still be one test.
MAX_AGE_SPREAD_DAYS = 0.5


@dataclass(frozen=True, slots=True)
class StrengthTest:
    """The companions from one sample, averaged."""

    set_code: str
    mix_code: str
    breaks: tuple[BreakResult, ...]
    size: SpecimenSize = SpecimenSize.CYL_4X8
    cure: CureCondition = CureCondition.STANDARD
    purpose: SpecimenPurpose = SpecimenPurpose.ACCEPTANCE
    ticket_number: str | None = None
    project: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_code", normalize_code(self.set_code, field="set_code"))
        object.__setattr__(self, "mix_code", normalize_code(self.mix_code, field="mix_code"))
        if not self.breaks:
            raise ValidationError("a strength test needs at least one break", field="breaks")
        codes = [b.specimen_code for b in self.breaks]
        if len(set(codes)) != len(codes):
            raise ValidationError("the same specimen appears twice in a test", field="breaks")

    @property
    def age_days(self) -> float:
        """The age the set was broken at, averaged over the companions."""
        return sum(b.age_days for b in self.breaks) / len(self.breaks)

    @property
    def tested_on(self) -> date:
        """The day the last companion was broken."""
        return max(b.tested_at for b in self.breaks).date()

    @property
    def age_spread(self) -> float:
        """How far apart the companions' ages were, in days."""
        ages = [b.age_days for b in self.breaks]
        return max(ages) - min(ages)

    @property
    def strengths(self) -> tuple[Quantity, ...]:
        """Each companion's corrected strength, in break order."""
        return tuple(b.strength for b in self.breaks)

    @property
    def average(self) -> Quantity:
        """The strength test result."""
        total = Quantity.zero("psi")
        for strength in self.strengths:
            total = total + strength.to("psi")
        return total * (1.0 / len(self.breaks))

    @property
    def lowest(self) -> Quantity:
        """The weakest companion."""
        return min(self.strengths, key=lambda q: q.base_value)

    @property
    def highest(self) -> Quantity:
        """The strongest companion."""
        return max(self.strengths, key=lambda q: q.base_value)

    @property
    def within_test_range(self) -> Quantity:
        """The spread between the weakest and strongest companion."""
        return self.highest - self.lowest.to(self.highest.unit)

    @property
    def within_test_range_percent(self) -> Percent:
        """The spread as a share of the average."""
        if self.average.is_zero():
            return Percent(0.0)
        return Percent.from_fraction(
            self.within_test_range.base_value / self.average.base_value
        )

    @property
    def range_limit(self) -> Percent:
        """The spread C39 allows for this many companions."""
        return RANGE_LIMIT_TWO if len(self.breaks) <= 2 else RANGE_LIMIT_THREE

    @property
    def is_complete(self) -> bool:
        """True when enough companions were broken to make a test."""
        return len(self.breaks) >= self.size.specimens_per_test

    @property
    def counts_for_acceptance(self) -> bool:
        """True when this test belongs in the acceptance record."""
        return (
            self.is_complete
            and self.cure.counts_for_acceptance
            and self.purpose is SpecimenPurpose.ACCEPTANCE
        )

    def concerns(self) -> tuple[str, ...]:
        """Everything about this set worth a second look."""
        found: list[str] = []
        if not self.is_complete:
            found.append(
                f"{len(self.breaks)} of {self.size.specimens_per_test} companions broken"
            )
        if self.age_spread > MAX_AGE_SPREAD_DAYS + 1e-9:
            found.append(
                f"companions broken {self.age_spread:.1f} days apart, the limit is "
                f"{MAX_AGE_SPREAD_DAYS:g}"
            )
        if self.within_test_range_percent > self.range_limit:
            found.append(
                f"companions spread {self.within_test_range_percent.format(1)}, "
                f"the precision limit is {self.range_limit.format(1)}"
            )
        for entry in self.breaks:
            if entry.is_out_of_round:
                found.append(f"{entry.specimen_code} was out of round")
            if entry.fracture.suggests_a_testing_fault:
                found.append(
                    f"{entry.specimen_code} broke {entry.fracture}, which points at the setup"
                )
        return tuple(found)

    def describe(self) -> str:
        """One line for a strength report."""
        return (
            f"{self.set_code}  {self.mix_code}  {self.age_days:g} d  "
            f"{self.average.format(0)}  spread {self.within_test_range_percent.format(1)}  "
            f"n={len(self.breaks)}"
        )


def group_into_tests(
    breaks: Iterable[BreakResult],
    set_of: dict[str, str],
    mix_of: dict[str, str],
    **defaults: object,
) -> tuple[StrengthTest, ...]:
    """Gather loose breaks into tests by the set each specimen belongs to.

    A break whose specimen is not in ``set_of`` is dropped rather than guessed
    at. A lab that hands over a break for a cylinder nobody logged has a filing
    problem, and inventing a set for it hides that.
    """
    grouped: dict[str, list[BreakResult]] = {}
    for entry in breaks:
        set_code = set_of.get(entry.specimen_code)
        if set_code is None:
            continue
        grouped.setdefault(set_code, []).append(entry)
    tests: list[StrengthTest] = []
    for set_code, members in sorted(grouped.items()):
        mix_code = mix_of.get(set_code)
        if mix_code is None:
            continue
        ordered = tuple(sorted(members, key=lambda b: b.specimen_code))
        tests.append(StrengthTest(set_code, mix_code, ordered, **defaults))  # type: ignore[arg-type]
    return tuple(tests)
