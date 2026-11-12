r"""Inference on Sharpe ratios: probabilistic and deflated Sharpe ratios, tests of differences.

All Sharpe ratios here are **per period** (as in the papers), from simple or excess returns
as the caller passes them. Skewness :math:`\gamma_3` and kurtosis :math:`\gamma_4` (not excess)
are the bias-corrected estimators of :mod:`qrlab.metrics.moments`.

- **PSR** (Bailey and Lopez de Prado 2012):
  :math:`\Phi\big((\widehat{SR}-SR^*)\sqrt{T-1}\,/\sqrt{1-\gamma_3\widehat{SR}+\tfrac{\gamma_4-1}{4}\widehat{SR}^2}\big)`.
- **DSR** (Bailey and Lopez de Prado 2014): PSR at
  :math:`SR^*_0=\sqrt V\,[(1-\gamma)\Phi^{-1}(1-1/N)+\gamma\Phi^{-1}(1-1/(Ne))]`, the expected
  maximum Sharpe ratio of :math:`N` independent trials with variance :math:`V`.
- **Jobson-Korkie with Memmel's (2003) correction** (i.i.d. normal returns):
  :math:`\theta=\frac1T[2-2\rho+\frac12(SR_1^2+SR_2^2-2SR_1SR_2\rho^2)]`.
- **Ledoit-Wolf (2008) HAC test:** delta method on the first and second moments of both series,
  with a Bartlett-kernel HAC covariance and explicit lags; Sharpe ratios use the ``ddof=0``
  variance there, as in the paper.
- **Stationary-bootstrap percentile interval** of the difference (``ddof=1`` Sharpe ratios).

Not rejecting a difference is not evidence that the two Sharpe ratios are equal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_series
from qrlab.metrics._inputs import returns_array
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.moments import excess_kurtosis, skewness
from qrlab.stats.bootstrap import BootstrapResult, stationary_bootstrap

__all__ = [
    "EULER_GAMMA",
    "ProbabilisticSharpe",
    "SharpeDifference",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "jkm_statistic",
    "probabilistic_sharpe",
    "probabilistic_sharpe_ratio",
    "sharpe_difference_bootstrap",
    "sharpe_difference_hac",
    "sharpe_difference_jkm",
]

EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True)
class ProbabilisticSharpe:
    """Probability that the true per-period Sharpe ratio exceeds ``benchmark``."""

    sharpe: float
    benchmark: float
    z: float
    probability: float
    skewness: float
    kurtosis: float
    n: int


@dataclass(frozen=True)
class SharpeDifference:
    """Test of :math:`SR_1 - SR_2 = 0` (two-sided)."""

    sharpe_1: float
    sharpe_2: float
    difference: float
    standard_error: float
    z: float
    pvalue: float
    method: str
    n: int


def probabilistic_sharpe(
    sharpe: float, *, n: int, skew: float, kurtosis: float, benchmark: float
) -> ProbabilisticSharpe:
    """Return the PSR from a per-period Sharpe ratio and its sample moments."""
    if type(n) is not int or n < 3:
        raise UndefinedMetricError("PSR needs at least 3 observations")
    denominator = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if not denominator > 0:
        raise UndefinedMetricError(
            f"PSR is undefined for these moments (skewness {skew:.3f}, kurtosis {kurtosis:.3f})"
        )
    z = (sharpe - benchmark) * math.sqrt(n - 1) / math.sqrt(denominator)
    return ProbabilisticSharpe(sharpe, benchmark, z, float(stats.norm.cdf(z)), skew, kurtosis, n)


def probabilistic_sharpe_ratio(returns: pd.Series, *, benchmark: float) -> ProbabilisticSharpe:
    """Return the PSR of ``returns`` against a per-period benchmark Sharpe ratio."""
    sharpe, n = _sharpe(returns)
    return probabilistic_sharpe(
        sharpe,
        n=n,
        skew=skewness(returns),
        kurtosis=excess_kurtosis(returns) + 3.0,
        benchmark=benchmark,
    )


def expected_max_sharpe(*, n_trials: int, variance: float) -> float:
    """Return the expected maximum per-period Sharpe ratio of ``n_trials`` independent trials."""
    if type(n_trials) is not int or n_trials < 2:
        raise ValidationError("n_trials must be an int >= 2")
    if not (math.isfinite(variance) and variance >= 0):
        raise ValidationError("variance must be finite and >= 0")
    q1 = float(stats.norm.ppf(1.0 - 1.0 / n_trials))
    q2 = float(stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e)))
    return math.sqrt(variance) * ((1.0 - EULER_GAMMA) * q1 + EULER_GAMMA * q2)


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    n_trials: int,
    trial_sharpes: pd.Series | None,
    variance: float | None,
) -> ProbabilisticSharpe:
    """Return the DSR: PSR at the expected maximum Sharpe ratio of the trials.

    Give exactly one of ``trial_sharpes`` (per-period Sharpe ratios of every trial; the
    variance is estimated with ``ddof=1``) or ``variance``.
    """
    if (trial_sharpes is None) == (variance is None):
        raise ValidationError("give exactly one of trial_sharpes or variance")
    if trial_sharpes is not None:
        values = trial_sharpes.to_numpy(dtype=np.float64)
        if len(values) < 2 or not np.all(np.isfinite(values)):
            raise ValidationError("trial_sharpes needs at least two finite values")
        v = float(np.var(values, ddof=1))
    else:
        v = float(variance)  # type: ignore[arg-type]
    threshold = expected_max_sharpe(n_trials=n_trials, variance=v)
    return probabilistic_sharpe_ratio(returns, benchmark=threshold)


def jkm_statistic(sharpe_1: float, sharpe_2: float, *, rho: float, n: int) -> tuple[float, float]:
    """Return Memmel's variance of the difference and its z statistic."""
    theta = (
        2.0 - 2.0 * rho + 0.5 * (sharpe_1**2 + sharpe_2**2 - 2.0 * sharpe_1 * sharpe_2 * rho**2)
    ) / n
    if not theta > 0:
        raise UndefinedMetricError("the difference of the Sharpe ratios has zero variance")
    return theta, (sharpe_1 - sharpe_2) / math.sqrt(theta)


def sharpe_difference_jkm(first: pd.Series, second: pd.Series) -> SharpeDifference:
    """Jobson-Korkie test with Memmel's correction (assumes i.i.d. normal returns)."""
    a, b = _pair(first, second)
    s1, s2 = _sr(a, 1), _sr(b, 1)
    rho = float(np.corrcoef(a, b)[0, 1])
    theta, z = jkm_statistic(s1, s2, rho=rho, n=len(a))
    return SharpeDifference(
        s1, s2, s1 - s2, math.sqrt(theta), z, _two_sided(z), "jobson_korkie_memmel", len(a)
    )


def sharpe_difference_hac(
    first: pd.Series, second: pd.Series, *, hac_lags: int
) -> SharpeDifference:
    """Ledoit-Wolf (2008) test with a Bartlett-kernel HAC covariance (explicit lags)."""
    if type(hac_lags) is not int or hac_lags < 0:
        raise ValidationError("hac_lags must be an int >= 0")
    a, b = _pair(first, second)
    n = len(a)
    if hac_lags >= n:
        raise ValidationError("hac_lags must be smaller than the number of observations")
    mu1, mu2 = a.mean(), b.mean()
    g1, g2 = (a**2).mean(), (b**2).mean()
    v1, v2 = g1 - mu1**2, g2 - mu2**2
    if not (v1 > 0 and v2 > 0):
        raise UndefinedMetricError("a series has zero variance")
    s1, s2 = mu1 / math.sqrt(v1), mu2 / math.sqrt(v2)
    gradient = np.array([g1 / v1**1.5, -g2 / v2**1.5, -0.5 * mu1 / v1**1.5, 0.5 * mu2 / v2**1.5])
    y = np.column_stack([a - mu1, b - mu2, a**2 - g1, b**2 - g2])
    psi = y.T @ y / n
    for lag in range(1, hac_lags + 1):
        weight = 1.0 - lag / (hac_lags + 1.0)
        gamma = y[lag:].T @ y[:-lag] / n
        psi += weight * (gamma + gamma.T)
    variance = float(gradient @ psi @ gradient) / n
    if not variance > 1e-300:
        raise UndefinedMetricError("the difference of the Sharpe ratios has zero variance")
    se = math.sqrt(variance)
    z = (s1 - s2) / se
    return SharpeDifference(
        s1, s2, s1 - s2, se, z, _two_sided(z), f"ledoit_wolf_hac({hac_lags})", n
    )


def sharpe_difference_bootstrap(
    first: pd.Series,
    second: pd.Series,
    *,
    mean_block_length: float,
    n_resamples: int,
    confidence: float,
    rng: np.random.Generator,
) -> BootstrapResult:
    """Stationary-bootstrap percentile interval of the difference of per-period Sharpe ratios."""
    _pair(first, second)
    frame = pd.concat([first.rename("first"), second.rename("second")], axis=1)

    def difference(values: np.ndarray) -> float:
        return _sr(values[:, 0], 1) - _sr(values[:, 1], 1)

    return stationary_bootstrap(
        frame,
        difference,
        mean_block_length=mean_block_length,
        n_resamples=n_resamples,
        confidence=confidence,
        rng=rng,
    )


def _sharpe(returns: pd.Series) -> tuple[float, int]:
    values = returns_array(returns, name="returns", min_n=3)
    return _sr(values, 1), len(values)


def _sr(values: np.ndarray, ddof: int) -> float:
    std = float(np.std(values, ddof=ddof))
    if not std > 0:
        raise UndefinedMetricError("a series has zero variance")
    return float(np.mean(values)) / std


def _pair(first: pd.Series, second: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    a = validate_series(first, nan_policy=NanPolicy.RAISE, name="first")
    b = validate_series(second, nan_policy=NanPolicy.RAISE, name="second")
    require_same_index(a, b)
    if len(a) < 3:
        raise UndefinedMetricError("a Sharpe-ratio test needs at least 3 observations")
    return a.to_numpy(), b.to_numpy()


def _two_sided(z: float) -> float:
    return float(2.0 * stats.norm.sf(abs(z)))
