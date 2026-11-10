"""Errors raised by metrics."""

from __future__ import annotations

from qrlab.core.errors import ValidationError

__all__ = ["UndefinedMetricError"]


class UndefinedMetricError(ValidationError):
    """The metric is not defined for this input (too few observations, zero variance, ...).

    Raised instead of returning a silent NaN or infinity; reports can catch it and show "n/a".
    """
