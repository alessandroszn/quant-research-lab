r"""Monte Carlo engines for simple asset returns (paths x periods x assets).

- **Normal:** log returns :math:`\ell_t\sim N(\mu,\Sigma)` i.i.d.; simple returns
  :math:`e^{\ell_t}-1` stay above -100 %.
- **Student-t:** :math:`\ell_t=\mu+\sqrt{(\nu-2)/\nu}\,Lz_t/\sqrt{w_t}`, :math:`z_t\sim N(0,I)`,
  :math:`w_t\sim\chi^2_\nu/\nu`, :math:`LL^\top=\Sigma`: covariance :math:`\Sigma`, fatter tails,
  :math:`\nu>2`.
- **Block bootstrap:** whole rows of historical simple returns in stationary-bootstrap blocks
  (Politis and Romano 1994) with an explicit mean block length, for a horizon of any length.

Every engine takes an explicit :class:`numpy.random.Generator` and a cell limit
(``max_cells``) checked before anything is allocated. Moments are per period of the stated
frequency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy, validate_frame

__all__ = [
    "MAX_CELLS",
    "LogMoments",
    "SimulatedReturns",
    "bootstrap_returns",
    "log_moments",
    "normal_returns",
    "student_t_returns",
]

MAX_CELLS = 50_000_000
"""Suggested limit on paths x periods x assets (about 400 MB of float64)."""


@dataclass(frozen=True)
class LogMoments:
    """Mean and covariance of one-period log returns, with the sample they come from."""

    mean: pd.Series
    covariance: pd.DataFrame
    n_obs: int

    def __post_init__(self) -> None:
        """Check labels, symmetry and positive semi-definiteness."""
        if list(self.mean.index) != list(self.covariance.index) or list(
            self.covariance.index
        ) != list(self.covariance.columns):
            raise ValidationError("mean and covariance must have the same asset labels")
        values = self.covariance.to_numpy(dtype=np.float64)
        if not np.all(np.isfinite(values)) or not np.all(np.isfinite(self.mean.to_numpy())):
            raise ValidationError("moments must be finite")
        if not np.allclose(values, values.T, atol=0.0):
            raise ValidationError("covariance must be symmetric")
        smallest = float(np.linalg.eigvalsh(values)[0])
        if smallest < -1e-12 * max(1.0, float(np.abs(values).max())):
            raise ValidationError(f"covariance is not positive semi-definite ({smallest})")


@dataclass(frozen=True)
class SimulatedReturns:
    """Simulated simple returns of shape (paths, periods, assets)."""

    returns: np.ndarray
    assets: tuple[str, ...]
    engine: str
    params: dict[str, float] = field(default_factory=dict)

    @property
    def n_paths(self) -> int:
        """Number of paths."""
        return int(self.returns.shape[0])

    @property
    def n_periods(self) -> int:
        """Number of periods."""
        return int(self.returns.shape[1])


def log_moments(returns: pd.DataFrame, *, kind: ReturnKind, missing: NanPolicy) -> LogMoments:
    """Estimate the mean and ``ddof=1`` covariance of log returns from simple returns."""
    if kind is not ReturnKind.SIMPLE:
        raise ValidationError("pass simple returns; they are converted to log returns here")
    if missing not in (NanPolicy.RAISE, NanPolicy.DROP):
        raise ValidationError("missing must be NanPolicy.RAISE or NanPolicy.DROP")
    frame = validate_frame(returns, nan_policy=missing, name="returns")
    if len(frame) < 2 or frame.shape[1] == 0:
        raise ValidationError("need at least two observations of at least one asset")
    if (frame.to_numpy() <= -1.0).any():
        raise ValidationError("simple returns must be above -1")
    logs = pd.DataFrame(np.log1p(frame.to_numpy()), index=frame.index, columns=frame.columns)
    covariance = np.atleast_2d(np.cov(logs.to_numpy(), rowvar=False, ddof=1))
    return LogMoments(
        mean=logs.mean(),
        covariance=pd.DataFrame(covariance, index=frame.columns, columns=frame.columns),
        n_obs=len(frame),
    )


def normal_returns(
    moments: LogMoments,
    *,
    n_paths: int,
    n_periods: int,
    rng: np.random.Generator,
    max_cells: int,
) -> SimulatedReturns:
    """Simulate i.i.d. multivariate normal log returns and return simple returns."""
    n = _check_size(n_paths, n_periods, len(moments.mean), max_cells, rng)
    z = rng.standard_normal((n_paths, n_periods, n))
    logs = moments.mean.to_numpy() + z @ _factor(moments).T
    return SimulatedReturns(np.expm1(logs), _labels(moments), "normal")


def student_t_returns(
    moments: LogMoments,
    *,
    dof: float,
    n_paths: int,
    n_periods: int,
    rng: np.random.Generator,
    max_cells: int,
) -> SimulatedReturns:
    """Simulate i.i.d. multivariate Student-t log returns with covariance ``moments``."""
    if type(dof) not in (int, float) or not dof > 2.0:
        raise ValidationError(f"dof must be a number above 2 (finite variance), got {dof!r}")
    n = _check_size(n_paths, n_periods, len(moments.mean), max_cells, rng)
    z = rng.standard_normal((n_paths, n_periods, n))
    w = rng.chisquare(dof, size=(n_paths, n_periods, 1)) / dof
    scale = math.sqrt((dof - 2.0) / dof)
    logs = moments.mean.to_numpy() + scale * (z @ _factor(moments).T) / np.sqrt(w)
    return SimulatedReturns(np.expm1(logs), _labels(moments), "student_t", {"dof": float(dof)})


def bootstrap_returns(
    history: pd.DataFrame,
    *,
    kind: ReturnKind,
    missing: NanPolicy,
    mean_block_length: float,
    n_paths: int,
    n_periods: int,
    rng: np.random.Generator,
    max_cells: int,
) -> SimulatedReturns:
    """Resample whole rows of historical simple returns in stationary-bootstrap blocks."""
    if kind is not ReturnKind.SIMPLE:
        raise ValidationError("the bootstrap resamples simple returns")
    if missing not in (NanPolicy.RAISE, NanPolicy.DROP):
        raise ValidationError("missing must be NanPolicy.RAISE or NanPolicy.DROP")
    if type(mean_block_length) not in (int, float) or not mean_block_length >= 1.0:
        raise ValidationError(f"mean_block_length must be >= 1, got {mean_block_length!r}")
    frame = validate_frame(history, nan_policy=missing, name="history")
    if len(frame) < 2 or frame.shape[1] == 0:
        raise ValidationError("history needs at least two rows of at least one asset")
    _check_size(n_paths, n_periods, frame.shape[1], max_cells, rng)
    rows = len(frame)
    new_block = rng.random((n_paths, n_periods)) < 1.0 / mean_block_length
    new_block[:, 0] = True
    starts = rng.integers(0, rows, size=(n_paths, n_periods))
    positions = np.arange(n_periods)
    last_start = np.maximum.accumulate(np.where(new_block, positions, 0), axis=1)
    start_rows = np.take_along_axis(starts, last_start, axis=1)
    indices = (start_rows + positions - last_start) % rows
    values = frame.to_numpy()[indices]
    params = {"mean_block_length": float(mean_block_length), "history_rows": float(rows)}
    return SimulatedReturns(values, tuple(map(str, frame.columns)), "block_bootstrap", params)


def _factor(moments: LogMoments) -> np.ndarray:
    """Return L with L L' = covariance (eigen decomposition, valid for singular matrices)."""
    eigenvalues, eigenvectors = np.linalg.eigh(moments.covariance.to_numpy(dtype=np.float64))
    factor: np.ndarray = eigenvectors * np.sqrt(np.clip(eigenvalues, 0.0, None))
    return factor


def _labels(moments: LogMoments) -> tuple[str, ...]:
    return tuple(map(str, moments.mean.index))


def _check_size(
    n_paths: int, n_periods: int, n_assets: int, max_cells: int, rng: np.random.Generator
) -> int:
    for name, value in (("n_paths", n_paths), ("n_periods", n_periods), ("max_cells", max_cells)):
        if type(value) is not int or value < 1:
            raise ValidationError(f"{name} must be a positive int, got {value!r}")
    if not isinstance(rng, np.random.Generator):
        raise ValidationError("rng must be a numpy.random.Generator (seeded by the caller)")
    cells = n_paths * n_periods * n_assets
    if cells > max_cells:
        raise ValidationError(f"{cells} cells exceed max_cells={max_cells}")
    return n_assets
