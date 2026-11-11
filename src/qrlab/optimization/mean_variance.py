r"""Equal weights, minimum variance, mean-variance and the efficient frontier.

- **1/N:** :math:`w_i = 1/N`; it must satisfy the constraints (otherwise it raises).
- **Minimum variance:** :math:`\min w^\top\Sigma w` subject to the constraints.
- **Mean-variance:** :math:`\max w^\top\mu - \frac{\lambda}{2}w^\top\Sigma w` with an explicit
  risk aversion :math:`\lambda > 0`.
- **Efficient frontier:** minimum variance at each target return :math:`w^\top\mu = m`.

Inputs are one-period figures; :math:`\mu` and :math:`\Sigma` must have the same asset labels.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.optimization.constraints import TOLERANCE, Constraints, solve
from qrlab.risk.covariance import CovarianceEstimate
from qrlab.risk.decomposition import RiskContributions, volatility_contributions

__all__ = [
    "OptimizationResult",
    "efficient_frontier",
    "equal_weights",
    "mean_variance",
    "minimum_variance",
]


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
    try:
        contributions: RiskContributions | None = volatility_contributions(covariance, weights)
    except UndefinedMetricError:
        contributions = None
    inputs: dict[str, str | float] = {
        "covariance": covariance.estimator,
        "n_obs": float(covariance.n_obs),
        "constraints": constraints.describe(),
        **extra,
    }
    return OptimizationResult(weights, method, objective, inputs, contributions, active, iterations)
