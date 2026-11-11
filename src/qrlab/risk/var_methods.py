r"""Cornish-Fisher and filtered-historical VaR and ES of one return series (positive losses).

**Cornish-Fisher.** With :math:`z=\Phi^{-1}(1-\alpha)`, sample skewness :math:`S` and excess
kurtosis :math:`K` (bias-corrected, :mod:`qrlab.metrics.moments`),

.. math:: q(z) = z + \frac{(z^2-1)S}{6} + \frac{(z^3-3z)K}{24} - \frac{(2z^3-5z)S^2}{36},

VaR :math:`= -(\bar r + s\,q(z))` and ES :math:`= -(\bar r + s\,E[q(Z)\mid Z\le z])`, computed
exactly from the truncated moments of the standard normal. The expansion is a quantile only
where :math:`q` increases; if it does not increase on the whole tail :math:`(-\infty, z]`, the
functions raise instead of returning a wrong number (Maillard 2012).

**Filtered historical simulation** (Hull and White 1998; Barone-Adesi et al. 1999) with an EWMA
volatility filter: :math:`\hat\sigma^2` starts at the ``ddof=1`` variance of the first ``warmup``
returns, then :math:`\hat\sigma^2_{t+1} = \lambda\hat\sigma^2_t + (1-\lambda) r_t^2`. Each later
return is standardised by the volatility known before it, :math:`z_t = r_t/\hat\sigma_t`, and the
next-period VaR and ES are :math:`\hat\sigma_{T+1}` times the historical VaR and ES of :math:`z`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.metrics._inputs import returns_array
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.moments import excess_kurtosis, skewness
from qrlab.metrics.risk import historical_es, historical_var

__all__ = [
    "CornishFisher",
    "FilteredHistorical",
    "cornish_fisher",
    "filtered_historical",
]


@dataclass(frozen=True)
class CornishFisher:
    """Cornish-Fisher VaR and ES with the moments used."""

    var: float
    es: float
    z: float
    z_cf: float
    mean: float
    std: float
    skewness: float
    excess_kurtosis: float


@dataclass(frozen=True)
class FilteredHistorical:
    """Filtered-historical VaR and ES for the next period."""

    var: float
    es: float
    next_volatility: float
    n_filtered: int


def cornish_fisher(returns: pd.Series, *, confidence: float) -> CornishFisher:
    """Return the Cornish-Fisher VaR and ES at ``confidence``."""
    alpha = _confidence(confidence)
    values = returns_array(returns, name="returns", min_n=4)
    s, k = skewness(returns), excess_kurtosis(returns)
    z = float(stats.norm.ppf(1.0 - alpha))
    _require_increasing(z, s, k)
    mean, std = float(np.mean(values)), float(np.std(values, ddof=1))
    z_cf = _quantile(z, s, k)
    phi, cdf = float(stats.norm.pdf(z)), 1.0 - alpha
    # truncated moments E[Z^n; Z <= z] of the standard normal
    m0, m1, m2, m3 = cdf, -phi, cdf - z * phi, -(z * z + 2.0) * phi
    expected = (
        m1 + (m2 - m0) * s / 6.0 + (m3 - 3.0 * m1) * k / 24.0 - (2.0 * m3 - 5.0 * m1) * s * s / 36.0
    ) / m0
    return CornishFisher(
        var=-(mean + std * z_cf),
        es=-(mean + std * expected),
        z=z,
        z_cf=z_cf,
        mean=mean,
        std=std,
        skewness=s,
        excess_kurtosis=k,
    )


def filtered_historical(
    returns: pd.Series, *, confidence: float, decay: float, warmup: int
) -> FilteredHistorical:
    """Return the filtered-historical VaR and ES for the period after the last return."""
    _confidence(confidence)
    if type(decay) is not float or not 0.0 < decay < 1.0:
        raise ValidationError(f"decay must be a float strictly between 0 and 1, got {decay!r}")
    if type(warmup) is not int or warmup < 2:
        raise ValidationError(f"warmup must be an int >= 2, got {warmup!r}")
    values = returns_array(returns, name="returns", min_n=warmup + 1)
    variance = float(np.var(values[:warmup], ddof=1))
    if not variance > 0.0:
        raise UndefinedMetricError("warm-up returns have zero variance: cannot filter")
    standardised = []
    for r in values[warmup:]:
        standardised.append(r / math.sqrt(variance))
        variance = decay * variance + (1.0 - decay) * r * r
    z = pd.Series(standardised, index=returns.index[warmup:])
    next_vol = math.sqrt(variance)
    return FilteredHistorical(
        var=next_vol * historical_var(z, confidence=confidence),
        es=next_vol * historical_es(z, confidence=confidence),
        next_volatility=next_vol,
        n_filtered=len(z),
    )


def _quantile(z: float, s: float, k: float) -> float:
    return (
        z
        + (z * z - 1.0) * s / 6.0
        + (z**3 - 3.0 * z) * k / 24.0
        - (2.0 * z**3 - 5.0 * z) * s * s / 36.0
    )


def _require_increasing(z: float, s: float, k: float) -> None:
    """Raise unless dq/dz = a z^2 + b z + c > 0 on (-inf, z]."""
    a = k / 8.0 - s * s / 6.0
    b = s / 3.0
    c = 1.0 - k / 8.0 + 5.0 * s * s / 36.0
    if a < 0.0 or (a == 0.0 and b > 0.0):
        lowest = -math.inf
    elif a == 0.0:
        lowest = a * z * z + b * z + c
    else:
        point = min(-b / (2.0 * a), z)
        lowest = a * point * point + b * point + c
    if not lowest > 0.0:
        raise UndefinedMetricError(
            f"Cornish-Fisher expansion is not a quantile on the tail (skewness {s:.3f}, "
            f"excess kurtosis {k:.3f})"
        )


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0.0 < value < 1.0:
        raise ValidationError(
            f"confidence must be a number strictly between 0 and 1, got {value!r}"
        )
    return float(value)
