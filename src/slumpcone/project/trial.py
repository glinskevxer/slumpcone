"""Trial batches, and reading a water-cementitious ratio off them.

A plant with no test record proves a mixture by making it. Three batches at
three different ratios, each broken at the design age, and the results plotted
against ratio. The ratio that gives the required average strength is read off
that line, and the mixture submitted is the one at that ratio or lower.

The rule that gets skipped is that the trials have to *bracket* the required
strength. Three batches that all come out above it give a line that has to be
extrapolated, and extrapolating a strength curve upward is how a mixture ends
up submitted at a ratio it has never been made at.

Slump and air matter too. A trial batch run at two inches of slump does not
tell you anything about a mixture that will be delivered at five.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from slumpcone.errors import ValidationError
from slumpcone.identity import normalize_code
from slumpcone.percent import Percent
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity

# How many batches at different ratios a trial series needs.
MIN_TRIAL_POINTS = 3

# The least difference in ratio between two trial points for them to count as
# different mixtures rather than the same one made twice.
MIN_RATIO_SEPARATION = 0.02


@dataclass(frozen=True, slots=True)
class TrialBatch:
    """One batch in a trial series."""

    water_cementitious: float
    strengths: tuple[Quantity, ...]
    slump: Quantity
    air: Percent
    age_days: int = 28

    def __post_init__(self) -> None:
        if not 0.15 <= self.water_cementitious <= 1.0:
            raise ValidationError(
                f"a water-cementitious ratio of {self.water_cementitious} is not a mixture",
                field="water_cementitious",
            )
        if len(self.strengths) < 2:
            raise ValidationError(
                "a trial point needs at least two cylinders", field="strengths"
            )
        for strength in self.strengths:
            if strength.dimension.value != "pressure":
                raise ValidationError("a strength is a pressure", field="strengths")
            if strength.value <= 0.0:
                raise ValidationError("a strength has to be positive", field="strengths")
        if self.slump.dimension.value != "length":
            raise ValidationError("a slump is a length", field="slump")
        if self.age_days <= 0:
            raise ValidationError("a test age has to be positive", field="age_days")

    @property
    def average(self) -> Quantity:
        """The batch's strength, averaged over its cylinders."""
        total = Quantity.zero("psi")
        for strength in self.strengths:
            total = total + strength.to("psi")
        return total * (1.0 / len(self.strengths))

    def describe(self) -> str:
        """One line for a trial report."""
        return (
            f"w/cm {self.water_cementitious:.3f}  {self.average.format(0)}  "
            f"slump {self.slump.format(1)}  air {self.air.format(1)}"
        )


@dataclass(frozen=True, slots=True)
class TrialSeries:
    """The batches making up one mixture's trial, with what they have to satisfy."""

    mix_code: str
    batches: tuple[TrialBatch, ...]
    required_average: Quantity
    slump_band: Band | None = None
    air_band: Band | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mix_code", normalize_code(self.mix_code, field="mix_code"))
        if not self.batches:
            raise ValidationError("a trial series needs at least one batch", field="batches")
        if self.required_average.dimension.value != "pressure":
            raise ValidationError(
                "a required average strength is a pressure", field="required_average"
            )
        if self.required_average.value <= 0.0:
            raise ValidationError(
                "a required average strength has to be positive", field="required_average"
            )

    @property
    def points(self) -> tuple[TrialBatch, ...]:
        """The batches, lowest ratio first."""
        return tuple(sorted(self.batches, key=lambda batch: batch.water_cementitious))

    @property
    def distinct_ratios(self) -> int:
        """How many genuinely different ratios were made."""
        ratios: list[float] = []
        for batch in self.points:
            if not ratios or batch.water_cementitious - ratios[-1] >= MIN_RATIO_SEPARATION:
                ratios.append(batch.water_cementitious)
        return len(ratios)

    @property
    def brackets_the_requirement(self) -> bool:
        """True when the trials sit either side of the required strength."""
        strengths = [batch.average for batch in self.points]
        if not strengths:
            return False
        return min(strengths) <= self.required_average <= max(strengths)

    def ratio_for(self, target: Quantity | None = None) -> float:
        """The ratio that gives ``target``, read off the trial line.

        Interpolated between the two bracketing points. Refuses to extrapolate,
        which is the whole point of asking for the trials to bracket.
        """
        wanted = self.required_average if target is None else target
        ordered = self.points
        if len(ordered) < 2:
            raise ValidationError(
                "two trial points are needed to read a ratio", field="batches"
            )
        for lower, upper in zip(ordered, ordered[1:], strict=False):
            high, low = lower.average, upper.average
            if min(low, high) <= wanted <= max(low, high):
                span = high.base_value - low.base_value
                if abs(span) < 1e-9:
                    return lower.water_cementitious
                share = (high.base_value - wanted.base_value) / span
                return lower.water_cementitious + share * (
                    upper.water_cementitious - lower.water_cementitious
                )
        raise ValidationError(
            f"{wanted.format(0)} is outside the trial range, which would mean "
            "extrapolating the strength curve",
            field="required_average",
        )

    def findings(self) -> tuple[str, ...]:
        """Everything that stops this series supporting a submittal."""
        found: list[str] = []
        if self.distinct_ratios < MIN_TRIAL_POINTS:
            found.append(
                f"{self.distinct_ratios} distinct ratios, {MIN_TRIAL_POINTS} are needed"
            )
        if not self.brackets_the_requirement:
            found.append(f"the trials do not bracket {self.required_average.format(0)}")
        ages = {batch.age_days for batch in self.batches}
        if len(ages) > 1:
            found.append(f"batches broken at {len(ages)} different ages")
        if self.slump_band is not None:
            for batch in self.points:
                if not self.slump_band.contains(batch.slump.to("in").value):
                    found.append(
                        f"the w/cm {batch.water_cementitious:.3f} batch was run at "
                        f"{batch.slump.format(1)}, outside {self.slump_band.format(1)}"
                    )
        if self.air_band is not None:
            for batch in self.points:
                if not self.air_band.contains(batch.air.value):
                    found.append(
                        f"the w/cm {batch.water_cementitious:.3f} batch was run at "
                        f"{batch.air.format(1)} air, outside {self.air_band.format(1)}"
                    )
        return tuple(found)

    @property
    def supports_a_submittal(self) -> bool:
        """True when the series is complete enough to submit a mixture on."""
        return not self.findings()

    def describe(self) -> str:
        """A short trial report."""
        lines = [
            f"{self.mix_code} trial against {self.required_average.format(0)}: "
            f"{len(self.batches)} batches"
        ]
        lines.extend(f"  {batch.describe()}" for batch in self.points)
        return "\n".join(lines)


def series_from_pairs(
    mix_code: str,
    pairs: Sequence[tuple[float, float]],
    required_average: Quantity,
    *,
    slump: Quantity | None = None,
    air: Percent | None = None,
) -> TrialSeries:
    """Build a series from ``(ratio, strength)`` pairs, for a quick check."""
    batches = tuple(
        TrialBatch(
            ratio,
            (Quantity(strength, "psi"), Quantity(strength, "psi")),
            slump or Quantity(4.0, "in"),
            air or Percent(6.0),
        )
        for ratio, strength in pairs
    )
    return TrialSeries(mix_code, batches, required_average)
