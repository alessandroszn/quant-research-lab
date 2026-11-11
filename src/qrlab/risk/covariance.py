r"""Covariance estimators of simple asset returns (one period, never annualised here).

- **Sample:** :math:`\frac{1}{T-1}\sum_t (r_t-\bar r)(r_t-\bar r)^\top`.
- **EWMA:** :math:`\sum_{k=0}^{T-1}\omega_k \tilde r_{T-k}\tilde r_{T-k}^\top` with
  :math:`\omega_k = (1-\lambda)\lambda^k / (1-\lambda^T)` (weights sum to 1). :math:`\tilde r` is
  the raw return (``demean=False``, RiskMetrics) or the return minus the sample mean.
- **Ledoit-Wolf** (2004, *J. Multivariate Analysis*): :math:`\delta\,\mu I + (1-\delta)S` with
  :math:`S` the :math:`1/T` sample covariance of demeaned returns, :math:`\mu=\mathrm{tr}(S)/N` and
  the closed-form optimal intensity :math:`\delta\in[0,1]`.

Every estimate is checked to be symmetric positive semi-definite.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.risk._inputs import asset_returns

__all__ = [
    "CovarianceEstimate",
    "ewma_covariance",
    "ledoit_wolf_covariance",
    "sample_covariance",
]

PSD_TOLERANCE = 1e-12


@dataclass(frozen=True)
class CovarianceEstimate:
    """A covariance matrix with how it was estimated.

    Attributes
    ----------
    matrix
        Covariance of one-period returns, assets on both axes.
    estimator
        ``"sample"``, ``"ewma"`` or ``"ledoit_wolf"``.
    n_obs
        Observations used.
    dropped_rows
        Dates removed because of missing values (``NanPolicy.DROP``).
    params
        Estimator parameters, e.g. ``{"lambda": 0.94}`` or ``{"shrinkage": 0.31}``.
    """

    matrix: pd.DataFrame
    estimator: str
    n_obs: int
    dropped_rows: int
    params: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Check symmetry and positive semi-definiteness."""
        values = self.matrix.to_numpy(dtype=np.float64)
        if values.shape[0] != values.shape[1] or not np.allclose(values, values.T, atol=0.0):
            raise ValidationError("covariance matrix must be square and symmetric")
        eigenvalues = np.linalg.eigvalsh(values)
        if eigenvalues.size and eigenvalues[0] < -PSD_TOLERANCE * max(abs(eigenvalues[-1]), 1.0):
            raise ValidationError(f"covariance is not positive semi-definite ({eigenvalues[0]})")

    def volatilities(self) -> pd.Series:
        """Return the standard deviation of each asset."""
        return pd.Series(np.sqrt(np.diag(self.matrix.to_numpy())), index=self.matrix.index)


def sample_covariance(
    returns: pd.DataFrame, *, kind: ReturnKind, missing: NanPolicy
) -> CovarianceEstimate:
    """Return the ``ddof=1`` sample covariance."""
    frame, dropped = asset_returns(returns, kind=kind, missing=missing, min_obs=2)
    matrix = np.cov(frame.to_numpy(), rowvar=False, ddof=1).reshape(frame.shape[1], -1)
    return CovarianceEstimate(_frame(matrix, frame), "sample", len(frame), dropped)


def ewma_covariance(
    returns: pd.DataFrame, *, kind: ReturnKind, missing: NanPolicy, decay: float, demean: bool
) -> CovarianceEstimate:
    """Return the exponentially weighted covariance with decay ``lambda`` in (0, 1)."""
    if type(decay) is not float or not 0.0 < decay < 1.0:
        raise ValidationError(f"decay must be a float strictly between 0 and 1, got {decay!r}")
    if not isinstance(demean, bool):
        raise ValidationError("demean must be True or False")
    frame, dropped = asset_returns(returns, kind=kind, missing=missing, min_obs=1)
    values = frame.to_numpy()
    if demean:
        values = values - values.mean(axis=0)
    t = len(values)
    ages = np.arange(t - 1, -1, -1)  # oldest row has age T-1, newest has age 0
    weights = (1.0 - decay) * decay**ages / (1.0 - decay**t)
    matrix = (values * weights[:, None]).T @ values
    matrix = (matrix + matrix.T) / 2.0
    params = {"lambda": decay, "demean": float(demean)}
    return CovarianceEstimate(_frame(matrix, frame), "ewma", t, dropped, params)


def ledoit_wolf_covariance(
    returns: pd.DataFrame, *, kind: ReturnKind, missing: NanPolicy
) -> CovarianceEstimate:
    """Return the Ledoit-Wolf (2004) shrinkage towards a scaled identity."""
    frame, dropped = asset_returns(returns, kind=kind, missing=missing, min_obs=2)
    x = frame.to_numpy()
    x = x - x.mean(axis=0)
    t, n = x.shape
    s = x.T @ x / t
    mu = float(np.trace(s)) / n
    target = mu * np.eye(n)
    d2 = float(np.sum((s - target) ** 2)) / n
    if d2 == 0.0:
        shrinkage = 0.0
    else:
        b_bar2 = sum(float(np.sum((np.outer(row, row) - s) ** 2)) for row in x) / (t**2 * n)
        shrinkage = min(b_bar2, d2) / d2
    matrix = shrinkage * target + (1.0 - shrinkage) * s
    return CovarianceEstimate(
        _frame(matrix, frame), "ledoit_wolf", t, dropped, {"shrinkage": shrinkage}
    )


def _frame(matrix: np.ndarray, returns: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(matrix, index=returns.columns, columns=returns.columns)
