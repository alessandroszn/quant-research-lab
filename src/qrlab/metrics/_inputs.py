"""Shared input checks for metric functions."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, validate_series
from qrlab.metrics.errors import UndefinedMetricError


def returns_array(returns: pd.Series, *, name: str, min_n: int) -> np.ndarray:
    """Validate a return series (NaN refused) and return its values as ``float64``."""
    values = validate_series(returns, nan_policy=NanPolicy.RAISE, name=name).to_numpy()
    if len(values) < min_n:
        raise UndefinedMetricError(
            f"{name}: needs at least {min_n} observation(s), got {len(values)}"
        )
    return values


def check_periods_per_year(value: object) -> float:
    """Return ``periods_per_year`` as a float after checking it is positive and finite."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError(f"periods_per_year must be a positive number, got {value!r}")
    if not (math.isfinite(value) and value > 0):
        raise ValidationError(f"periods_per_year must be positive and finite, got {value!r}")
    return float(value)


def check_finite(value: object, name: str) -> float:
    """Return ``value`` after checking it is a finite real number."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValidationError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def sample_std(values: np.ndarray, name: str) -> float:
    """Sample standard deviation (ddof = 1); zero variance is undefined for ratios."""
    std = float(np.std(values, ddof=1))
    if std == 0.0:
        raise UndefinedMetricError(f"{name}: zero variance")
    return std
