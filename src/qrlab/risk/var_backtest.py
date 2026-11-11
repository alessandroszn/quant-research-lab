r"""Out-of-sample VaR forecasts and their backtests (Kupiec 1995; Christoffersen 1998).

**Forecasts.** :func:`var_forecasts` computes, for each date :math:`t` after the first
``window`` returns, the VaR of the ``window`` returns strictly **before** :math:`t`. A change in
:math:`r_t` can never move the forecast for :math:`t`.

**Hits.** :math:`I_t = 1` when the loss :math:`-r_t` is strictly greater than the forecast.

**Kupiec (proportion of failures).** With :math:`n` forecasts, :math:`x` hits, :math:`p=1-\alpha`
and :math:`\hat p = x/n`:
:math:`LR_{pof} = -2\ln\frac{(1-p)^{n-x}p^x}{(1-\hat p)^{n-x}\hat p^x} \sim \chi^2(1)`.

**Christoffersen (independence).** From the transition counts :math:`n_{ij}` (hit :math:`i`
followed by hit :math:`j`), :math:`\pi_0 = n_{01}/(n_{00}+n_{01})`,
:math:`\pi_1 = n_{11}/(n_{10}+n_{11})` and the pooled :math:`\pi`:
:math:`LR_{ind} = -2[\ell(\pi) - \ell(\pi_0, \pi_1)] \sim \chi^2(1)`, and conditional coverage
:math:`LR_{cc} = LR_{pof} + LR_{ind} \sim \chi^2(2)`. :math:`0\ln 0 = 0` throughout.

Not rejecting is not proof that the model is right; a test can only reject.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_series

__all__ = ["VarBacktest", "var_backtest", "var_forecasts"]


@dataclass(frozen=True)
class VarBacktest:
    """Exceedances and test statistics of a VaR backtest."""

    n: int
    exceedances: int
    expected: float
    hit_rate: float
    kupiec_lr: float
    kupiec_pvalue: float
    independence_lr: float
    independence_pvalue: float
    conditional_coverage_lr: float
    conditional_coverage_pvalue: float
    transitions: tuple[int, int, int, int]  # n00, n01, n10, n11
    notes: tuple[str, ...]


def var_forecasts(
    returns: pd.Series, *, window: int, model: Callable[[pd.Series], float]
) -> pd.Series:
    """Return one-step VaR forecasts, each from the ``window`` returns before its date.

    ``model`` maps a window of returns to a VaR, e.g.
    ``lambda r: historical_var(r, confidence=0.99)``.
    """
    if type(window) is not int or window < 2:
        raise ValidationError(f"window must be an int >= 2, got {window!r}")
    series = validate_series(returns, nan_policy=NanPolicy.RAISE, name="returns")
    if len(series) <= window:
        raise ValidationError(f"{len(series)} returns leave no forecast after a window of {window}")
    values = [float(model(series.iloc[t - window : t])) for t in range(window, len(series))]
    return pd.Series(values, index=series.index[window:], name="var")


def var_backtest(returns: pd.Series, forecasts: pd.Series, *, confidence: float) -> VarBacktest:
    """Backtest VaR ``forecasts`` against realised ``returns`` on the same dates."""
    if type(confidence) is not float or not 0.0 < confidence < 1.0:
        raise ValidationError(f"confidence must be a float in (0, 1), got {confidence!r}")
    realised = validate_series(returns, nan_policy=NanPolicy.RAISE, name="returns")
    var = validate_series(forecasts, nan_policy=NanPolicy.RAISE, name="forecasts")
    require_same_index(realised, var)
    if len(realised) < 2:
        raise ValidationError("a backtest needs at least two forecasts")
    hits = (-realised.to_numpy() > var.to_numpy()).astype(int)
    n, x = len(hits), int(hits.sum())
    p = 1.0 - confidence
    kupiec = -2.0 * (_loglik(p, n - x, x) - _loglik(x / n, n - x, x))
    pairs = list(itertools.pairwise(int(h) for h in hits))
    n00 = sum(1 for a, b in pairs if (a, b) == (0, 0))
    n01 = sum(1 for a, b in pairs if (a, b) == (0, 1))
    n10 = sum(1 for a, b in pairs if (a, b) == (1, 0))
    n11 = sum(1 for a, b in pairs if (a, b) == (1, 1))
    notes: list[str] = []
    if n10 + n11 == 0 or n00 + n01 == 0:
        independence = 0.0
        notes.append("no transitions out of one of the states: independence is not testable")
    else:
        pi0, pi1 = n01 / (n00 + n01), n11 / (n10 + n11)
        pi = (n01 + n11) / len(pairs)
        independence = -2.0 * (
            _loglik(pi, n00 + n10, n01 + n11) - _loglik(pi0, n00, n01) - _loglik(pi1, n10, n11)
        )
    independence = max(independence, 0.0)
    kupiec = max(kupiec, 0.0)
    coverage = kupiec + independence
    return VarBacktest(
        n=n,
        exceedances=x,
        expected=n * p,
        hit_rate=x / n,
        kupiec_lr=kupiec,
        kupiec_pvalue=float(stats.chi2.sf(kupiec, 1)),
        independence_lr=independence,
        independence_pvalue=float(stats.chi2.sf(independence, 1)),
        conditional_coverage_lr=coverage,
        conditional_coverage_pvalue=float(stats.chi2.sf(coverage, 2)),
        transitions=(n00, n01, n10, n11),
        notes=tuple(notes),
    )


def _loglik(q: float, zeros: int, ones: int) -> float:
    """Return zeros * ln(1 - q) + ones * ln(q), with 0 ln 0 = 0.

    Every caller passes a ``q`` that is 0 only when ``ones`` is 0 and 1 only when ``zeros`` is 0.
    """
    total = 0.0
    if zeros:
        total += zeros * math.log1p(-q)
    if ones:
        total += ones * math.log(q)
    return total
