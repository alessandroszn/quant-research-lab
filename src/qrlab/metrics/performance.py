r"""Performance metrics of a series of simple returns.

Conventions: inputs are simple returns in decimals with no NaN; ``periods_per_year`` is always
explicit; the sample standard deviation uses ``ddof=1``; annualising a standard deviation by
:math:`\sqrt{P}` assumes returns are not serially correlated.

Sharpe and Sortino ratios take **excess** returns, computed by the caller with
:func:`qrlab.core.returns.excess_returns`, so the risk-free rate is always explicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.metrics._inputs import check_finite, check_periods_per_year, returns_array, sample_std
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.moments import excess_kurtosis, skewness

__all__ = [
    "SharpeEstimate",
    "SharpeSE",
    "annualised_arithmetic_return",
    "annualised_geometric_return",
    "annualised_volatility",
    "downside_deviation",
    "gain_loss_ratio",
    "hit_rate",
    "sharpe_ratio",
    "sortino_ratio",
]


class SharpeSE(Enum):
    """Standard-error formula for the Sharpe ratio (both assume iid returns)."""

    IID_NORMAL = "iid_normal"  # Lo (2002)
    IID_NON_NORMAL = "iid_non_normal"  # Mertens (2002): adjusts for skewness and kurtosis


@dataclass(frozen=True)
class SharpeEstimate:
    """Annualised Sharpe ratio with its standard error.

    Attributes
    ----------
    value
        Per-period Sharpe ratio times the square root of periods per year.
    standard_error
        Standard error of ``value`` under ``method``.
    n
        Number of observations.
    method
        Standard-error formula used.
    """

    value: float
    standard_error: float
    n: int
    method: SharpeSE


def annualised_arithmetic_return(returns: pd.Series, *, periods_per_year: float) -> float:
    r"""Mean return times periods per year, :math:`\bar r P` (not a compound growth rate)."""
    p = check_periods_per_year(periods_per_year, returns)
    return float(np.mean(returns_array(returns, name="returns", min_n=1))) * p


def annualised_geometric_return(returns: pd.Series, *, periods_per_year: float) -> float:
    r"""Compound annual growth rate, :math:`W_n^{P/n} - 1` with :math:`W_n = \prod (1 + r_t)`.

    Raises
    ------
    UndefinedMetricError
        If final wealth is zero or negative (a total loss has no growth rate).
    """
    p = check_periods_per_year(periods_per_year, returns)
    values = returns_array(returns, name="returns", min_n=1)
    wealth = float(np.prod(1.0 + values))
    if wealth <= 0:
        raise UndefinedMetricError(f"final wealth {wealth} <= 0: no compound growth rate")
    return float(wealth ** (p / len(values))) - 1.0


def annualised_volatility(returns: pd.Series, *, periods_per_year: float) -> float:
    r"""Sample standard deviation (``ddof=1``) times :math:`\sqrt{P}`. Needs 2 observations."""
    p = check_periods_per_year(periods_per_year, returns)
    values = returns_array(returns, name="returns", min_n=2)
    return float(np.std(values, ddof=1)) * math.sqrt(p)


def sharpe_ratio(
    excess_returns: pd.Series, *, periods_per_year: float, se_method: SharpeSE
) -> SharpeEstimate:
    r"""Annualised Sharpe ratio of excess returns with a standard error.

    :math:`\widehat{SR} = \bar e / s_e` per period, annualised by :math:`\sqrt{P}`.

    Standard errors (per period, then times :math:`\sqrt{P}`):

    - ``IID_NORMAL`` (Lo, 2002): :math:`\sqrt{(1 + \widehat{SR}^2/2)/n}`;
    - ``IID_NON_NORMAL`` (Mertens, 2002):
      :math:`\sqrt{(1 + \widehat{SR}^2/2 - \gamma_3 \widehat{SR} + \kappa \widehat{SR}^2/4)/n}`
      with bias-corrected skewness :math:`\gamma_3` and excess kurtosis :math:`\kappa`.

    Both assume iid returns; autocorrelation-robust inference is planned for phase 5.1.
    """
    if not isinstance(se_method, SharpeSE):
        raise ValidationError(f"se_method must be a SharpeSE, got {se_method!r}")
    p = check_periods_per_year(periods_per_year, excess_returns)
    min_n = 4 if se_method is SharpeSE.IID_NON_NORMAL else 2
    values = returns_array(excess_returns, name="excess_returns", min_n=min_n)
    n = len(values)
    sr = float(np.mean(values)) / sample_std(values, "sharpe_ratio")
    if se_method is SharpeSE.IID_NORMAL:
        variance = (1.0 + sr**2 / 2.0) / n
    else:
        g3, kappa = skewness(excess_returns), excess_kurtosis(excess_returns)
        variance = (1.0 + sr**2 / 2.0 - g3 * sr + kappa * sr**2 / 4.0) / n
        if variance <= 0:
            raise UndefinedMetricError("Mertens variance is not positive for these moments")
    scale = math.sqrt(p)
    return SharpeEstimate(sr * scale, math.sqrt(variance) * scale, n, se_method)


def downside_deviation(returns: pd.Series, *, target: float, periods_per_year: float) -> float:
    r"""Annualised downside deviation below ``target`` (a per-period return).

    :math:`\sqrt{\tfrac{1}{n}\sum_t \min(r_t - \tau, 0)^2}\,\sqrt{P}`, averaging over *all*
    periods (denominator :math:`n`).
    """
    p = check_periods_per_year(periods_per_year, returns)
    tau = check_finite(target, "target")
    values = returns_array(returns, name="returns", min_n=1)
    return _downside(values, tau) * math.sqrt(p)


def sortino_ratio(excess_returns: pd.Series, *, target: float, periods_per_year: float) -> float:
    r"""Annualised Sortino ratio, :math:`(\bar e - \tau) / DD \cdot \sqrt{P}`.

    ``target`` :math:`\tau` is the per-period minimum acceptable return; :math:`DD` is the
    per-period downside deviation below it (see :func:`downside_deviation`).
    """
    p = check_periods_per_year(periods_per_year, excess_returns)
    tau = check_finite(target, "target")
    values = returns_array(excess_returns, name="excess_returns", min_n=1)
    dd = _downside(values, tau)
    if dd == 0.0:
        raise UndefinedMetricError("sortino_ratio: no return below the target")
    return (float(np.mean(values)) - tau) / dd * math.sqrt(p)


def hit_rate(returns: pd.Series) -> float:
    """Share of periods with a strictly positive return (a zero return is not a hit)."""
    values = returns_array(returns, name="returns", min_n=1)
    return float(np.mean(values > 0))


def gain_loss_ratio(returns: pd.Series) -> float:
    """Mean of positive returns divided by the absolute mean of negative returns."""
    values = returns_array(returns, name="returns", min_n=1)
    gains, losses = values[values > 0], values[values < 0]
    if len(gains) == 0 or len(losses) == 0:
        raise UndefinedMetricError("gain_loss_ratio needs at least one gain and one loss")
    return float(np.mean(gains)) / abs(float(np.mean(losses)))


def _downside(values: np.ndarray, target: float) -> float:
    shortfall = np.minimum(values - target, 0.0)
    return math.sqrt(float(np.mean(shortfall**2)))
