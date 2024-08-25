"""Reports: what the register has to be able to show somebody."""

from slumpcone.report.nonconformance import (
    NonConformance,
    Severity,
    register_from,
)

__all__ = ["NonConformance", "Severity", "register_from"]
