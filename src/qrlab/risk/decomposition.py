r"""Risk contributions that add up to the total (Euler allocation), and effective bets.

- **Volatility:** :math:`\sigma_p=\sqrt{w^\top\Sigma w}`, marginal
  :math:`(\Sigma w)_i/\sigma_p`, component :math:`w_i(\Sigma w)_i/\sigma_p`.
- **Historical ES:** the tail of :func:`qrlab.metrics.risk.historical_es` (worst
  :math:`m=T(1-\alpha)` periods, the last with a fractional weight); the component of asset
  :math:`i` is minus its weighted average contribution to the tail returns. Ties in portfolio
  return are broken by date.
- **Normal ES:** :math:`-w_i\bar r_i + \frac{w_i(Sw)_i}{\sigma_p}\frac{\varphi(z_\alpha)}{1-\alpha}`
  with the sample mean and ``ddof=1`` covariance :math:`S`.
- **Effective number of bets** (Meucci 2009): exponential of the entropy of the variance shares
  of the principal portfolios of :math:`\Sigma`; from 1 to :math:`N`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.risk._inputs import asset_returns, portfolio_weights
from qrlab.risk.covariance import CovarianceEstimate

__all__ = [
    "RiskContributions",
    "effective_number_of_bets",
    "historical_es_contributions",
    "normal_es_contributions",
    "volatility_contributions",
]


@dataclass(frozen=True)
class RiskContributions:
    """Contributions of each asset to a portfolio risk measure.

    Attributes
    ----------
    measure
        ``"volatility"``, ``"historical_es"`` or ``"normal_es"``.
    total
        The portfolio risk; ``component`` sums to it.
    component
        Contribution of each asset (same unit as ``total``).
    share
        ``component / total``; sums to 1.
    marginal
        Change in the risk per unit of weight (volatility only), else ``None``.
    weight_sum
        Sum of the weights (not required to be 1).
    """

    measure: str
    total: float
    component: pd.Series
    share: pd.Series
    marginal: pd.Series | None
    weight_sum: float


def volatility_contributions(
    covariance: CovarianceEstimate, weights: pd.Series
) -> RiskContributions:
    """Split portfolio volatility into asset contributions."""
    sigma = covariance.matrix.to_numpy()
    assets = covariance.matrix.index
    w = portfolio_weights(weights, assets)
    sigma_w = sigma @ w
    variance = float(w @ sigma_w)
    if not variance > 0.0:
        raise UndefinedMetricError("portfolio volatility is zero: contributions are undefined")
    vol = math.sqrt(variance)
    marginal = pd.Series(sigma_w / vol, index=assets)
    component = pd.Series(w * sigma_w / vol, index=assets)
    return RiskContributions(
        "volatility", vol, component, component / vol, marginal, float(w.sum())
    )


def historical_es_contributions(
    returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidence: float,
    kind: ReturnKind,
    missing: NanPolicy,
) -> RiskContributions:
    """Split the historical expected shortfall of the portfolio into asset contributions."""
    alpha = _confidence(confidence)
    frame, _ = asset_returns(returns, kind=kind, missing=missing, min_obs=1)
    w = portfolio_weights(weights, frame.columns)
    weighted = frame.to_numpy() * w
    portfolio = weighted.sum(axis=1)
    m = round(len(portfolio) * (1.0 - alpha), 10)
    if m < 1.0:
        raise UndefinedMetricError(
            f"{len(portfolio)} observations leave a tail of {m} at confidence {alpha}; need >= 1"
        )
    order = np.argsort(portfolio, kind="stable")
    whole = math.floor(m)
    tail = weighted[order[:whole]].sum(axis=0)
    if m > whole:
        tail = tail + (m - whole) * weighted[order[whole]]
    component = pd.Series(-tail / m, index=frame.columns)
    total = float(component.sum())
    return RiskContributions(
        "historical_es", total, component, component / total, None, float(w.sum())
    )


def normal_es_contributions(
    returns: pd.DataFrame,
    weights: pd.Series,
    *,
    confidence: float,
    kind: ReturnKind,
    missing: NanPolicy,
) -> RiskContributions:
    """Split the normal (parametric) expected shortfall into asset contributions."""
    alpha = _confidence(confidence)
    frame, _ = asset_returns(returns, kind=kind, missing=missing, min_obs=2)
    w = portfolio_weights(weights, frame.columns)
    values = frame.to_numpy()
    mean = values.mean(axis=0)
    cov = np.cov(values, rowvar=False, ddof=1).reshape(len(w), len(w))
    cov_w = cov @ w
    variance = float(w @ cov_w)
    if not variance > 0.0:
        raise UndefinedMetricError("portfolio volatility is zero: contributions are undefined")
    vol = math.sqrt(variance)
    z = float(stats.norm.ppf(alpha))
    tail_factor = float(stats.norm.pdf(z)) / (1.0 - alpha)
    component = pd.Series(-w * mean + w * cov_w / vol * tail_factor, index=frame.columns)
    total = float(component.sum())
    return RiskContributions("normal_es", total, component, component / total, None, float(w.sum()))


def effective_number_of_bets(covariance: CovarianceEstimate, weights: pd.Series) -> float:
    """Return Meucci's (2009) effective number of bets from principal portfolios."""
    sigma = covariance.matrix.to_numpy()
    w = portfolio_weights(weights, covariance.matrix.index)
    eigenvalues, eigenvectors = np.linalg.eigh(sigma)
    exposures = eigenvectors.T @ w
    variances = np.clip(eigenvalues, 0.0, None) * exposures**2
    total = float(variances.sum())
    if not total > 0.0:
        raise UndefinedMetricError("portfolio variance is zero: effective bets are undefined")
    shares = variances / total
    positive = shares[shares > 0.0]
    return float(math.exp(-float(np.sum(positive * np.log(positive)))))


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 < value < 1.0:
        raise ValidationError(
            f"confidence must be a number strictly between 0 and 1, got {value!r}"
        )
    return float(value)
