r"""Benchmark-relative metrics.

Portfolio and benchmark series must have **identical indexes** (no silent alignment). They must
also be in the same currency and of the same return type (both total-return or both
price-return); the series cannot carry that information, so it is the caller's responsibility.

Active return :math:`a_t = r^p_t - r^b_t`. Annualisation uses an explicit
``periods_per_year``; :math:`\sqrt{P}` scaling assumes no serial correlation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import require_same_index
from qrlab.metrics._inputs import check_periods_per_year, returns_array
from qrlab.metrics.errors import UndefinedMetricError

__all__ = [
    "CapmEstimate",
    "active_share",
    "capm_regression",
    "down_capture",
    "information_ratio",
    "tracking_error",
    "up_capture",
]


@dataclass(frozen=True)
class CapmEstimate:
    """OLS regression of portfolio excess returns on benchmark excess returns.

    Attributes
    ----------
    alpha_annualised
        Intercept times periods per year (arithmetic).
    beta
        Slope.
    se_alpha_annualised, se_beta
        Classical OLS standard errors (homoskedastic, uncorrelated errors). HAC errors are
        planned for ``stats`` (phase 2.2).
    r_squared
        Coefficient of determination.
    n
        Number of observations.
    """

    alpha_annualised: float
    beta: float
    se_alpha_annualised: float
    se_beta: float
    r_squared: float
    n: int


def tracking_error(portfolio: pd.Series, benchmark: pd.Series, *, periods_per_year: float) -> float:
    r"""Annualised tracking error, :math:`s_a \sqrt{P}` (``ddof=1``)."""
    p = check_periods_per_year(periods_per_year)
    active = _active(portfolio, benchmark, min_n=2)
    return float(np.std(active, ddof=1)) * math.sqrt(p)


def information_ratio(
    portfolio: pd.Series, benchmark: pd.Series, *, periods_per_year: float
) -> float:
    r"""Annualised information ratio, :math:`\bar a P / (s_a \sqrt{P})`."""
    p = check_periods_per_year(periods_per_year)
    active = _active(portfolio, benchmark, min_n=2)
    std = float(np.std(active, ddof=1))
    if std == 0.0:
        raise UndefinedMetricError("information_ratio: tracking error is zero")
    return float(np.mean(active)) * p / (std * math.sqrt(p))


def capm_regression(
    excess_portfolio: pd.Series, excess_benchmark: pd.Series, *, periods_per_year: float
) -> CapmEstimate:
    r"""Regress :math:`e^p_t = \alpha + \beta e^b_t + \varepsilon_t` by OLS.

    Both inputs are **excess** returns over the same risk-free rate (see
    :func:`qrlab.core.returns.excess_returns`). Needs at least 3 observations, a benchmark with
    non-zero variance and a portfolio with non-zero variance (for :math:`R^2`).
    """
    p = check_periods_per_year(periods_per_year)
    y = returns_array(excess_portfolio, name="excess_portfolio", min_n=3)
    x = returns_array(excess_benchmark, name="excess_benchmark", min_n=3)
    require_same_index(excess_portfolio, excess_benchmark)
    n = len(y)
    x_mean, y_mean = float(np.mean(x)), float(np.mean(y))
    sxx = float(np.sum((x - x_mean) ** 2))
    syy = float(np.sum((y - y_mean) ** 2))
    if sxx == 0.0:
        raise UndefinedMetricError("capm_regression: benchmark has zero variance")
    if syy == 0.0:
        raise UndefinedMetricError("capm_regression: R-squared undefined (portfolio is constant)")
    beta = float(np.sum((x - x_mean) * (y - y_mean))) / sxx
    alpha = y_mean - beta * x_mean
    residuals = y - alpha - beta * x
    ssr = float(np.sum(residuals**2))
    sigma2 = ssr / (n - 2)
    se_beta = math.sqrt(sigma2 / sxx)
    se_alpha = math.sqrt(sigma2 * (1.0 / n + x_mean**2 / sxx))
    return CapmEstimate(
        alpha_annualised=alpha * p,
        beta=beta,
        se_alpha_annualised=se_alpha * p,
        se_beta=se_beta,
        r_squared=1.0 - ssr / syy,
        n=n,
    )


def up_capture(portfolio: pd.Series, benchmark: pd.Series, *, periods_per_year: float) -> float:
    """Ratio of annualised geometric returns over periods when the benchmark rose.

    Morningstar definition; periods with a zero benchmark return are excluded. Because returns
    compound, a portfolio with half the benchmark's exposure does not score exactly 0.5.
    """
    return _capture(portfolio, benchmark, periods_per_year, up=True)


def down_capture(portfolio: pd.Series, benchmark: pd.Series, *, periods_per_year: float) -> float:
    """Ratio of annualised geometric returns over periods when the benchmark fell."""
    return _capture(portfolio, benchmark, periods_per_year, up=False)


def active_share(
    portfolio_weights: pd.Series, benchmark_weights: pd.Series, *, weight_tolerance: float
) -> float:
    r"""Active share :math:`\tfrac12 \sum_i |w^p_i - w^b_i|` over the union of holdings.

    Weights are indexed by holding identifier, must be finite, non-negative (long-only
    definition), unique, and sum to 1 within ``weight_tolerance``. They are never rescaled.
    """
    if not (math.isfinite(weight_tolerance) and weight_tolerance >= 0):
        raise ValidationError(f"weight_tolerance must be finite and >= 0, got {weight_tolerance}")
    wp = _weights(portfolio_weights, "portfolio_weights", weight_tolerance)
    wb = _weights(benchmark_weights, "benchmark_weights", weight_tolerance)
    union = wp.index.union(wb.index)
    diff = wp.reindex(union, fill_value=0.0) - wb.reindex(union, fill_value=0.0)
    return 0.5 * float(np.abs(diff.to_numpy()).sum())


# --------------------------------------------------------------------------- helpers
def _active(portfolio: pd.Series, benchmark: pd.Series, *, min_n: int) -> np.ndarray:
    rp = returns_array(portfolio, name="portfolio", min_n=min_n)
    rb = returns_array(benchmark, name="benchmark", min_n=min_n)
    require_same_index(portfolio, benchmark)
    active: np.ndarray = np.subtract(rp, rb)
    return active


def _capture(
    portfolio: pd.Series, benchmark: pd.Series, periods_per_year: float, *, up: bool
) -> float:
    p = check_periods_per_year(periods_per_year)
    rp = returns_array(portfolio, name="portfolio", min_n=1)
    rb = returns_array(benchmark, name="benchmark", min_n=1)
    require_same_index(portfolio, benchmark)
    mask = rb > 0 if up else rb < 0
    label = "up" if up else "down"
    if not mask.any():
        raise UndefinedMetricError(f"{label}_capture: the benchmark has no {label} periods")
    return _annualised(rp[mask], p, label) / _annualised(rb[mask], p, label)


def _annualised(values: np.ndarray, p: float, label: str) -> float:
    wealth = float(np.prod(1.0 + values))
    if wealth <= 0:
        raise UndefinedMetricError(f"{label}_capture: final wealth <= 0 over the selected periods")
    return float(wealth ** (p / len(values))) - 1.0


def _weights(weights: object, name: str, tolerance: float) -> pd.Series:
    if not isinstance(weights, pd.Series) or weights.empty:
        raise ValidationError(f"{name} must be a non-empty Series")
    if weights.index.has_duplicates:
        raise ValidationError(f"{name} has duplicated identifiers")
    values = weights.astype("float64")
    if not np.isfinite(values.to_numpy()).all():
        raise ValidationError(f"{name} must be finite")
    if (values < 0).any():
        raise ValidationError(f"{name} has negative weights (active share is long-only)")
    total = float(values.sum())
    if abs(total - 1.0) > tolerance:
        raise ValidationError(f"{name} sum to {total}, not 1 within {tolerance}; not rescaled")
    return values
