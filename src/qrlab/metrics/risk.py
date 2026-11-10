r"""One-period value at risk and expected shortfall of simple returns.

Results are **positive losses**: ``0.03`` means a 3 % loss over one period of the input series.
No scaling to longer horizons is applied (multi-period risk is phase 3.1).

Historical estimators, with :math:`\alpha` the confidence, :math:`m = n(1 - \alpha)` and
order statistics :math:`r_{(1)} \le \dots \le r_{(n)}`:

- :math:`VaR = -r_{(\lceil m \rceil)}` (inverted-CDF empirical quantile);
- :math:`ES = -\frac{1}{m}\big[\sum_{i=1}^{\lfloor m \rfloor} r_{(i)}
  + (m - \lfloor m \rfloor)\, r_{(\lfloor m \rfloor + 1)}\big]` (Acerbi and Tasche, 2002).

:math:`m` is rounded to 10 decimals first, so that e.g. :math:`20 \times (1 - 0.95)` is exactly
1 rather than :math:`1 + 9 \times 10^{-16}`. :math:`m < 1` is undefined.

Normal (parametric): :math:`VaR = -\bar r + s z_\alpha`,
:math:`ES = -\bar r + s\,\varphi(z_\alpha)/(1 - \alpha)` with sample mean and ``ddof=1``
standard deviation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.metrics._inputs import returns_array
from qrlab.metrics.errors import UndefinedMetricError

__all__ = ["historical_es", "historical_var", "parametric_es", "parametric_var"]


def historical_var(returns: pd.Series, *, confidence: float) -> float:
    """Historical one-period VaR at ``confidence`` (e.g. 0.95), as a positive loss."""
    ordered, m = _tail(returns, confidence)
    return -float(ordered[math.ceil(m) - 1])


def historical_es(returns: pd.Series, *, confidence: float) -> float:
    """Historical one-period expected shortfall (Acerbi-Tasche), as a positive loss."""
    ordered, m = _tail(returns, confidence)
    whole = math.floor(m)
    total = float(np.sum(ordered[:whole]))
    if m > whole:
        total += (m - whole) * float(ordered[whole])
    return -total / m


def parametric_var(returns: pd.Series, *, confidence: float) -> float:
    """Return the normal one-period VaR from the sample mean and ``ddof=1`` deviation."""
    alpha = _confidence(confidence)
    mean, std = _moments(returns)
    return -mean + std * float(stats.norm.ppf(alpha))


def parametric_es(returns: pd.Series, *, confidence: float) -> float:
    """Return the normal one-period expected shortfall from sample mean and deviation."""
    alpha = _confidence(confidence)
    mean, std = _moments(returns)
    z = float(stats.norm.ppf(alpha))
    return -mean + std * float(stats.norm.pdf(z)) / (1.0 - alpha)


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError(f"confidence must be a number in (0, 1), got {value!r}")
    if not 0.0 < value < 1.0:
        raise ValidationError(f"confidence must be strictly between 0 and 1, got {value!r}")
    return float(value)


def _tail(returns: pd.Series, confidence: float) -> tuple[np.ndarray, float]:
    alpha = _confidence(confidence)
    values = returns_array(returns, name="returns", min_n=1)
    m = round(len(values) * (1.0 - alpha), 10)
    if m < 1.0:
        raise UndefinedMetricError(
            f"{len(values)} observations leave a tail of {m} at confidence {alpha}; need >= 1"
        )
    return np.sort(values), m


def _moments(returns: pd.Series) -> tuple[float, float]:
    values = returns_array(returns, name="returns", min_n=2)
    return float(np.mean(values)), float(np.std(values, ddof=1))
