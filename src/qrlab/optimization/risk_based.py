r"""Risk-based portfolios and Black-Litterman.

- **Equal (budgeted) risk contribution:** :math:`w_i(\Sigma w)_i = b_i\,\sigma_p^2` with explicit
  budgets :math:`b`, solved as Spinu's (2013) strictly convex problem
  :math:`\min \tfrac12 y^\top\Sigma y - \sum_i b_i\ln y_i` by damped Newton steps, then
  :math:`w = y/\sum y`. Long-only and fully invested by construction.
- **Maximum diversification** (Choueifaty and Coignard 2008): minimum variance on the
  correlation matrix (long-only), rescaled by :math:`1/\sigma_i`.
- **Hierarchical risk parity** (Lopez de Prado 2016): correlation distance
  :math:`\sqrt{(1-\rho)/2}`, single-linkage clustering, quasi-diagonal order, recursive
  bisection with inverse-variance weights inside each cluster.
- **Black-Litterman:** prior :math:`\pi=\delta\Sigma w_{mkt}`; posterior
  :math:`\mu_{BL}=[(\tau\Sigma)^{-1}+P^\top\Omega^{-1}P]^{-1}[(\tau\Sigma)^{-1}\pi+P^\top\Omega^{-1}Q]`
  and :math:`\Sigma_{BL}=\Sigma+[(\tau\Sigma)^{-1}+P^\top\Omega^{-1}P]^{-1}`; :math:`\Omega` is
  given or He-Litterman :math:`\mathrm{diag}(\tau P\Sigma P^\top)`. Weights then come from
  :func:`~qrlab.optimization.mean_variance` on the posterior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform

from qrlab.core.errors import ValidationError
from qrlab.optimization.constraints import Constraints
from qrlab.optimization.mean_variance import OptimizationResult, _result, minimum_variance
from qrlab.risk.covariance import CovarianceEstimate

__all__ = [
    "BlackLitterman",
    "black_litterman",
    "hierarchical_risk_parity",
    "maximum_diversification",
    "risk_budgeting",
]

MAX_NEWTON_STEPS = 200
_LONG_ONLY = Constraints(long_only=True, bounds={}, groups={}, turnover=None, current=None)


@dataclass(frozen=True)
class BlackLitterman:
    """Prior and posterior of a Black-Litterman model."""

    prior: pd.Series
    mean: pd.Series
    covariance: CovarianceEstimate
    tau: float
    risk_aversion: float


def risk_budgeting(covariance: CovarianceEstimate, budgets: pd.Series) -> OptimizationResult:
    """Return long-only weights whose risk contributions match ``budgets`` (summing to 1)."""
    sigma, assets = _matrix(covariance)
    b = _budgets(budgets, assets)
    if np.any(np.diag(sigma) <= 0):
        raise ValidationError("every asset needs positive variance for risk budgeting")
    y = b / np.sqrt(np.diag(sigma))
    iterations = 0
    gradient = sigma @ y - b / y
    while float(np.max(np.abs(gradient))) > 1e-15 and iterations < MAX_NEWTON_STEPS:
        step = np.linalg.solve(sigma + np.diag(b / y**2), gradient)
        # damped step: never move more than half-way to the boundary y = 0
        limit = np.where(step > 0, y / np.where(step > 0, step, 1.0), np.inf)
        y = y - min(1.0, 0.5 * float(limit.min())) * step
        gradient = sigma @ y - b / y
        iterations += 1
    w = y / y.sum()
    contributions = w * (sigma @ w) / float(w @ sigma @ w)
    if float(np.max(np.abs(contributions - b))) > 1e-8:
        raise ValidationError("risk budgeting did not converge")  # pragma: no cover - convex
    method = "equal_risk_contribution" if np.allclose(b, b[0]) else "risk_budgeting"
    return _result(
        covariance,
        w,
        method,
        float(w @ sigma @ w),
        _LONG_ONLY,
        {"budgets": ", ".join(f"{x:.4f}" for x in b)},
        (),
        iterations,
    )


def maximum_diversification(covariance: CovarianceEstimate) -> OptimizationResult:
    """Return the long-only portfolio maximising the diversification ratio."""
    sigma, assets = _matrix(covariance)
    vol = np.sqrt(np.diag(sigma))
    if np.any(vol <= 0):
        raise ValidationError("every asset needs positive volatility for maximum diversification")
    corr = sigma / np.outer(vol, vol)
    on_corr = minimum_variance(
        CovarianceEstimate(
            pd.DataFrame(corr, index=assets, columns=assets),
            "correlation",
            covariance.n_obs,
            covariance.dropped_rows,
        ),
        _LONG_ONLY,
    )
    raw = on_corr.weights.to_numpy() / vol
    w = raw / raw.sum()
    ratio = float(w @ vol / math.sqrt(w @ sigma @ w))
    return _result(
        covariance,
        w,
        "maximum_diversification",
        ratio,
        _LONG_ONLY,
        {"diversification_ratio": ratio},
        on_corr.active,
        on_corr.iterations,
    )


def hierarchical_risk_parity(covariance: CovarianceEstimate) -> OptimizationResult:
    """Return Lopez de Prado's (2016) hierarchical risk parity weights."""
    sigma, assets = _matrix(covariance)
    vol = np.sqrt(np.diag(sigma))
    if np.any(vol <= 0):
        raise ValidationError("every asset needs positive variance for HRP")
    n = len(assets)
    if n == 1:
        order = [0]
    else:
        corr = np.clip(sigma / np.outer(vol, vol), -1.0, 1.0)
        distance = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, None))
        np.fill_diagonal(distance, 0.0)
        links = hierarchy.linkage(squareform(distance, checks=False), method="single")
        order = [int(i) for i in hierarchy.leaves_list(links)]
    w = np.ones(n)
    clusters = [order]
    while clusters:
        nxt = []
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            half = len(cluster) // 2
            left, right = cluster[:half], cluster[half:]
            v_left, v_right = _cluster_variance(sigma, left), _cluster_variance(sigma, right)
            alpha = 1.0 - v_left / (v_left + v_right)
            w[left] *= alpha
            w[right] *= 1.0 - alpha
            nxt += [left, right]
        clusters = nxt
    order_names = ", ".join(assets[i] for i in order)
    return _result(
        covariance,
        w,
        "hierarchical_risk_parity",
        float(w @ sigma @ w),
        _LONG_ONLY,
        {"order": order_names},
        (),
        0,
    )


def black_litterman(
    covariance: CovarianceEstimate,
    *,
    market_weights: pd.Series,
    risk_aversion: float,
    tau: float,
    views: pd.DataFrame,
    view_returns: pd.Series,
    omega: pd.DataFrame | None,
) -> BlackLitterman:
    """Return the Black-Litterman prior and posterior (no views: posterior mean = prior)."""
    sigma, assets = _matrix(covariance)
    for name, value in (("risk_aversion", risk_aversion), ("tau", tau)):
        if type(value) not in (int, float) or not (math.isfinite(value) and value > 0):
            raise ValidationError(f"{name} must be a positive number")
    if set(map(str, market_weights.index)) != set(assets):
        raise ValidationError("market weights must cover exactly the covariance's assets")
    w_mkt = market_weights.rename(index=str).reindex(assets).to_numpy(dtype=np.float64)
    if abs(w_mkt.sum() - 1.0) > 1e-9:
        raise ValidationError("market weights must sum to 1")
    pi = float(risk_aversion) * sigma @ w_mkt
    tau_sigma_inv = np.linalg.inv(float(tau) * sigma)
    if views.shape[0] == 0:
        precision = tau_sigma_inv
        weighted = tau_sigma_inv @ pi
    else:
        if set(map(str, views.columns)) != set(assets):
            raise ValidationError("views must have one column per asset")
        p = views.rename(columns=str).reindex(columns=assets).to_numpy(dtype=np.float64)
        if not views.index.equals(view_returns.index):
            raise ValidationError("view_returns must be indexed like the views")
        q = view_returns.to_numpy(dtype=np.float64)
        if omega is None:
            om = np.diag(np.diag(float(tau) * p @ sigma @ p.T))
        else:
            om = omega.to_numpy(dtype=np.float64)
            if om.shape != (len(q), len(q)):
                raise ValidationError("omega must be square with one row per view")
        om_inv = np.linalg.inv(om)
        precision = tau_sigma_inv + p.T @ om_inv @ p
        weighted = tau_sigma_inv @ pi + p.T @ om_inv @ q
    posterior_cov = np.linalg.inv(precision)
    mean = np.linalg.solve(precision, weighted)
    matrix = sigma + posterior_cov
    return BlackLitterman(
        prior=pd.Series(pi, index=assets),
        mean=pd.Series(mean, index=assets),
        covariance=CovarianceEstimate(
            pd.DataFrame((matrix + matrix.T) / 2.0, index=assets, columns=assets),
            "black_litterman",
            covariance.n_obs,
            covariance.dropped_rows,
            {"tau": float(tau), "risk_aversion": float(risk_aversion)},
        ),
        tau=float(tau),
        risk_aversion=float(risk_aversion),
    )


def _matrix(covariance: CovarianceEstimate) -> tuple[np.ndarray, list[str]]:
    assets = [str(a) for a in covariance.matrix.index]
    if not assets:
        raise ValidationError("covariance has no assets")
    return covariance.matrix.to_numpy(dtype=np.float64), assets


def _budgets(budgets: pd.Series, assets: list[str]) -> np.ndarray:
    if set(map(str, budgets.index)) != set(assets):
        raise ValidationError("risk budgets must cover exactly the covariance's assets")
    b = budgets.rename(index=str).reindex(assets).to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(b)) or np.any(b <= 0) or abs(b.sum() - 1.0) > 1e-9:
        raise ValidationError("risk budgets must be positive and sum to 1")
    return b


def _cluster_variance(sigma: np.ndarray, members: list[int]) -> float:
    sub = sigma[np.ix_(members, members)]
    ivp = 1.0 / np.diag(sub)
    ivp /= ivp.sum()
    return float(ivp @ sub @ ivp)
