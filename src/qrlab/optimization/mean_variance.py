r"""Equal weights, minimum variance, mean-variance and the efficient frontier.

- **1/N:** :math:`w_i = 1/N`; it must satisfy the constraints (otherwise it raises).
- **Minimum variance:** :math:`\min w^\top\Sigma w` subject to the constraints.
- **Mean-variance:** :math:`\max w^\top\mu - \frac{\lambda}{2}w^\top\Sigma w` with an explicit
  risk aversion :math:`\lambda > 0`.
- **Efficient frontier:** minimum variance at each target return :math:`w^\top\mu = m`.
- **Maximum Sharpe (long-only):** :math:`\max w^\top\mu/\sqrt{w^\top\Sigma w}` with
  :math:`w\ge 0`, solved as :math:`\min y^\top\Sigma y` subject to :math:`\mu^\top y = 1`,
  :math:`y\ge 0`, then :math:`w=y/\mathbf 1^\top y` (Cornuejols and Tutuncu 2007); :math:`\mu`
  are expected **excess** returns.

Inputs are one-period figures; :math:`\mu` and :math:`\Sigma` must have the same asset labels.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import optimize

from qrlab.core.errors import ValidationError
from qrlab.optimization.constraints import SNAP, TOLERANCE, Constraints, solve
from qrlab.risk.covariance import CovarianceEstimate
from qrlab.risk.decomposition import RiskContributions, volatility_contributions

ZERO_VARIANCE = 1e-24
"""Portfolio variance below this (volatility below 1e-12) is treated as zero."""

__all__ = [
    "OptimizationResult",
    "efficient_frontier",
    "equal_weights",
    "maximum_sharpe",
    "mean_variance",
    "minimum_variance",
]

_LONG_ONLY = Constraints(long_only=True, bounds={}, groups={}, turnover=None, current=None)


@dataclass(frozen=True)
class OptimizationResult:
    """Weights with the inputs and diagnostics that produced them."""

    weights: pd.Series
    method: str
    objective: float
    inputs: Mapping[str, str | float]
    contributions: RiskContributions | None
    active: tuple[str, ...]
    iterations: int


def equal_weights(covariance: CovarianceEstimate, constraints: Constraints) -> OptimizationResult:
    """Return 1/N weights after checking that they satisfy ``constraints``."""
    assets = _assets(covariance)
    w = np.full(len(assets), 1.0 / len(assets))
    lower = np.array([constraints.bounds.get(a, (-math.inf, math.inf))[0] for a in assets])
    upper = np.array([constraints.bounds.get(a, (-math.inf, math.inf))[1] for a in assets])
    broken = (w < lower - TOLERANCE).any() or (w > upper + TOLERANCE).any()
    for _, (members, low, high) in constraints.groups.items():
        total = sum(1.0 / len(assets) for a in assets if a in members)
        broken |= total < low - TOLERANCE or total > high + TOLERANCE
    if constraints.current is not None:
        current = constraints.current.reindex(assets).to_numpy(dtype=np.float64)
        broken |= float(np.abs(w - current).sum()) > float(constraints.turnover or 0) + TOLERANCE
    if broken:
        raise ValidationError("1/N weights break the constraints")
    return _result(covariance, w, "equal_weights", 0.0, constraints, {}, (), 0)


def minimum_variance(
    covariance: CovarianceEstimate, constraints: Constraints
) -> OptimizationResult:
    """Return the minimum-variance weights under ``constraints``."""
    assets = _assets(covariance)
    sigma = covariance.matrix.to_numpy(dtype=np.float64)
    _require_unique(sigma, constraints)
    outcome = solve(assets, lambda w: float(w @ sigma @ w), lambda w: 2.0 * sigma @ w, constraints)
    return _result(
        covariance,
        outcome.weights,
        "minimum_variance",
        outcome.objective,
        constraints,
        {},
        outcome.active,
        outcome.iterations,
    )


def mean_variance(
    expected: pd.Series,
    covariance: CovarianceEstimate,
    constraints: Constraints,
    *,
    risk_aversion: float,
) -> OptimizationResult:
    r"""Return the weights maximising :math:`w^\top\mu - \frac{\lambda}{2} w^\top\Sigma w`."""
    if type(risk_aversion) not in (int, float) or not (
        math.isfinite(risk_aversion) and risk_aversion > 0
    ):
        raise ValidationError("risk_aversion must be a positive number")
    assets = _assets(covariance)
    mu = _expected(expected, assets)
    sigma = covariance.matrix.to_numpy(dtype=np.float64)
    lam = float(risk_aversion)
    outcome = solve(
        assets,
        lambda w: float(-(w @ mu) + 0.5 * lam * (w @ sigma @ w)),
        lambda w: -mu + lam * sigma @ w,
        constraints,
    )
    inputs = {"risk_aversion": lam, "expected_return": float(outcome.weights @ mu)}
    return _result(
        covariance,
        outcome.weights,
        "mean_variance",
        -outcome.objective,
        constraints,
        inputs,
        outcome.active,
        outcome.iterations,
    )


def maximum_sharpe(expected: pd.Series, covariance: CovarianceEstimate) -> OptimizationResult:
    """Return the long-only, fully invested weights with the highest Sharpe ratio.

    ``expected`` are one-period expected excess returns. The objective reported is the
    one-period Sharpe ratio of the weights. Other constraints (bounds, groups, turnover) are not
    supported: the change of variables does not preserve them.

    Raises
    ------
    ValidationError
        If no asset has a positive expected excess return (the maximum Sharpe ratio is then not
        positive and the change of variables fails), if an asset has zero variance, or if the
        solver fails.
    """
    assets = _assets(covariance)
    mu = _expected(expected, assets)
    sigma = covariance.matrix.to_numpy(dtype=np.float64)
    variances = np.diag(sigma)
    if np.any(variances <= 0):
        raise ValidationError("every asset needs positive variance for the maximum Sharpe ratio")
    if not np.any(mu > 0):
        raise ValidationError("maximum Sharpe needs at least one positive expected excess return")
    ratios = np.where(mu > 0, mu / np.sqrt(variances), -np.inf)
    start = np.zeros(len(assets))
    best = int(np.argmax(ratios))
    start[best] = 1.0 / mu[best]

    def variance(y: np.ndarray) -> float:
        return float(y @ sigma @ y)

    def gradient(y: np.ndarray) -> np.ndarray:
        return np.asarray(2.0 * sigma @ y, dtype=np.float64)

    budget: list[Any] = [{"type": "eq", "fun": lambda y: mu @ y - 1.0, "jac": lambda y: mu}]
    box: list[Any] = [(0.0, None)] * len(assets)
    result = optimize.minimize(
        variance,
        start,
        jac=gradient,
        method="SLSQP",
        bounds=box,
        constraints=budget,
        options={"ftol": 1e-15, "maxiter": 2000},
    )
    y = np.clip(np.asarray(result.x, dtype=np.float64), 0.0, None)
    if not result.success or abs(float(mu @ y) - 1.0) > 1e-6:
        raise ValidationError(f"maximum Sharpe optimisation failed: {result.message}")
    w = y / y.sum()
    w = np.where(w <= SNAP, 0.0, w)
    w = w / w.sum()
    sharpe = float(w @ mu / np.sqrt(w @ sigma @ w))
    active = tuple(a for a, wi in zip(assets, w, strict=True) if wi == 0.0)
    return _result(covariance, w, "maximum_sharpe", sharpe, _LONG_ONLY, {}, active, int(result.nit))


def efficient_frontier(
    expected: pd.Series,
    covariance: CovarianceEstimate,
    constraints: Constraints,
    *,
    targets: Sequence[float],
) -> tuple[OptimizationResult, ...]:
    """Return the minimum-variance portfolio at each target expected return."""
    if not targets:
        raise ValidationError("give at least one target return")
    assets = _assets(covariance)
    mu = _expected(expected, assets)
    sigma = covariance.matrix.to_numpy(dtype=np.float64)
    results = []
    for target in targets:
        outcome = solve(
            assets,
            lambda w: float(w @ sigma @ w),
            lambda w: 2.0 * sigma @ w,
            constraints,
            equalities=((mu, float(target)),),
        )
        results.append(
            _result(
                covariance,
                outcome.weights,
                "frontier",
                outcome.objective,
                constraints,
                {"target_return": float(target)},
                outcome.active,
                outcome.iterations,
            )
        )
    return tuple(results)


def _assets(covariance: CovarianceEstimate) -> list[str]:
    assets = [str(a) for a in covariance.matrix.index]
    if len(assets) < 1:
        raise ValidationError("covariance has no assets")
    return assets


def _expected(expected: pd.Series, assets: list[str]) -> np.ndarray:
    if set(map(str, expected.index)) != set(assets):
        raise ValidationError("expected returns must be a Series with the covariance's assets")
    values = expected.rename(index=str).reindex(assets).to_numpy(dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValidationError("expected returns must be finite")
    return values


def _require_unique(sigma: np.ndarray, constraints: Constraints) -> None:
    """Raise for a singular covariance without bounds: the minimum is not unique."""
    unbounded = not constraints.long_only and not constraints.bounds
    if unbounded and np.linalg.matrix_rank(sigma) < sigma.shape[0]:
        raise ValidationError("singular covariance without bounds: the minimum is not unique")


def _result(
    covariance: CovarianceEstimate,
    w: np.ndarray,
    method: str,
    objective: float,
    constraints: Constraints,
    extra: Mapping[str, str | float],
    active: tuple[str, ...],
    iterations: int,
) -> OptimizationResult:
    weights = pd.Series(w, index=covariance.matrix.index, name="weight")
    sigma = covariance.matrix.to_numpy(dtype=np.float64)
    contributions: RiskContributions | None = None
    if float(w @ sigma @ w) > ZERO_VARIANCE:
        contributions = volatility_contributions(covariance, weights)
    inputs: dict[str, str | float] = {
        "covariance": covariance.estimator,
        "n_obs": float(covariance.n_obs),
        "constraints": constraints.describe(),
        **extra,
    }
    return OptimizationResult(weights, method, objective, inputs, contributions, active, iterations)
