"""Higher moments of a return series (bias-corrected sample estimators)."""

from __future__ import annotations

import pandas as pd
from scipy import stats

from qrlab.metrics._inputs import returns_array, sample_std

__all__ = ["excess_kurtosis", "skewness"]


def skewness(returns: pd.Series) -> float:
    """Return the adjusted Fisher-Pearson sample skewness (``scipy.stats.skew(bias=False)``).

    Needs at least 3 observations and non-zero variance.
    """
    values = returns_array(returns, name="skewness", min_n=3)
    sample_std(values, "skewness")
    return float(stats.skew(values, bias=False))


def excess_kurtosis(returns: pd.Series) -> float:
    """Return the bias-corrected sample excess kurtosis (normal = 0; ``scipy.stats.kurtosis``).

    Needs at least 4 observations and non-zero variance.
    """
    values = returns_array(returns, name="excess_kurtosis", min_n=4)
    sample_std(values, "excess_kurtosis")
    return float(stats.kurtosis(values, fisher=True, bias=False))
