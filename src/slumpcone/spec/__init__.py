"""What the specification demands of a mixture before anything is batched."""

from slumpcone.spec.exposure import (
    ExposureCategory,
    ExposureClass,
    ExposureSet,
    air_requirement,
)
from slumpcone.spec.frequency import (
    check_frequency,
    may_waive_strength_tests,
    required_samples,
)

__all__ = [
    "ExposureCategory",
    "ExposureClass",
    "ExposureSet",
    "air_requirement",
    "check_frequency",
    "may_waive_strength_tests",
    "required_samples",
]
