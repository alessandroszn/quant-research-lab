"""Stationary bootstrap for dependent data (Politis and Romano, 1994).

Resamples are built from blocks of consecutive observations whose lengths are geometric with
mean ``mean_block_length``; blocks start at uniformly random positions and wrap around the end
of the sample (circular), so every resample is a stationary series. Block resampling preserves
short-range dependence that the iid bootstrap destroys; ``mean_block_length = 1`` gives the
iid bootstrap.

The random generator is a required argument: results are reproducible and no hidden global
seed is used. The block length is always explicit (automatic selection, e.g. Politis and White
2004, is not implemented).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, validate_frame, validate_series

__all__ = ["BootstrapResult", "stationary_bootstrap", "stationary_bootstrap_indices"]

MIN_RESAMPLES = 100


@dataclass(frozen=True)
class BootstrapResult:
    """Bootstrap estimate and percentile confidence interval.

    Attributes
    ----------
    estimate
        Statistic on the original sample.
    low, high
        Percentile interval at ``confidence`` (NumPy's default linear quantile interpolation).
    confidence, mean_block_length, n_resamples
        Settings used.
    method
        Always ``"percentile"``.
    distribution
        The statistic on every resample, for diagnostics.
    """

    estimate: float
    low: float
    high: float
    confidence: float
    mean_block_length: float
    n_resamples: int
    method: str = "percentile"
    distribution: np.ndarray = field(default_factory=lambda: np.empty(0), compare=False, repr=False)


def stationary_bootstrap_indices(
    n: int, *, mean_block_length: float, n_resamples: int, rng: np.random.Generator
) -> np.ndarray:
    """Row indices of ``n_resamples`` stationary-bootstrap resamples of a length-``n`` sample.

    Returns an integer array of shape ``(n_resamples, n)``.
    """
    _check_settings(mean_block_length, n_resamples, rng)
    if type(n) is not int or n < 2:
        raise ValidationError(f"need at least 2 observations, got {n!r}")
    probability = 1.0 / mean_block_length
    new_block = rng.random((n_resamples, n)) < probability
    new_block[:, 0] = True
    starts = rng.integers(0, n, size=(n_resamples, n))
    positions = np.arange(n)
    # Position of the most recent block start for every cell, then offset from it (circular).
    last_start = np.maximum.accumulate(np.where(new_block, positions, 0), axis=1)
    start_values = np.take_along_axis(starts, last_start, axis=1)
    indices: np.ndarray = (start_values + positions - last_start) % n
    return indices


def stationary_bootstrap(
    data: pd.Series | pd.DataFrame,
    statistic: Callable[[np.ndarray], float],
    *,
    mean_block_length: float,
    n_resamples: int,
    confidence: float,
    rng: np.random.Generator,
) -> BootstrapResult:
    """Percentile confidence interval of ``statistic`` by stationary bootstrap.

    Parameters
    ----------
    data
        Time-ordered observations without NaN; for a frame, whole rows are resampled together.
    statistic
        Function of the values array (1-D for a series, 2-D rows x columns for a frame)
        returning a finite number.
    mean_block_length
        Expected block length (>= 1); larger values preserve longer dependence.
    n_resamples
        Number of resamples (>= 100).
    confidence
        Interval level in (0, 1).
    rng
        Seeded generator, e.g. ``np.random.default_rng(seed)``.
    """
    _check_settings(mean_block_length, n_resamples, rng)
    if not 0.0 < confidence < 1.0:
        raise ValidationError(f"confidence must be in (0, 1), got {confidence}")
    values: np.ndarray
    if isinstance(data, pd.DataFrame):
        values = validate_frame(data, nan_policy=NanPolicy.RAISE, name="data").to_numpy()
    else:
        values = validate_series(data, nan_policy=NanPolicy.RAISE, name="data").to_numpy()
    if len(values) < 2:
        raise ValidationError(f"need at least 2 observations, got {len(values)}")
    estimate = _evaluate(statistic, values)
    indices = stationary_bootstrap_indices(
        len(values), mean_block_length=mean_block_length, n_resamples=n_resamples, rng=rng
    )
    distribution = np.array([_evaluate(statistic, values[row]) for row in indices])
    low, high = np.quantile(distribution, [(1.0 - confidence) / 2.0, (1.0 + confidence) / 2.0])
    return BootstrapResult(
        estimate=estimate,
        low=float(low),
        high=float(high),
        confidence=confidence,
        mean_block_length=mean_block_length,
        n_resamples=n_resamples,
        distribution=distribution,
    )


def _evaluate(statistic: Callable[[np.ndarray], float], values: np.ndarray) -> float:
    result = float(statistic(values))
    if not math.isfinite(result):
        raise ValidationError(f"statistic must return a finite number, got {result}")
    return result


def _check_settings(mean_block_length: object, n_resamples: object, rng: object) -> None:
    if (
        isinstance(mean_block_length, bool)
        or not isinstance(mean_block_length, int | float)
        or not math.isfinite(mean_block_length)
        or mean_block_length < 1
    ):
        raise ValidationError(f"mean_block_length must be a number >= 1, got {mean_block_length!r}")
    if type(n_resamples) is not int or n_resamples < MIN_RESAMPLES:
        raise ValidationError(f"n_resamples must be an int >= {MIN_RESAMPLES}, got {n_resamples!r}")
    if not isinstance(rng, np.random.Generator):
        raise ValidationError(
            "rng must be a numpy.random.Generator (e.g. np.random.default_rng(seed))"
        )
