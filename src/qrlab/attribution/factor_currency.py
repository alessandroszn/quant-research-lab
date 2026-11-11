r"""Factor-based and currency attribution.

**Factor-based (ex post).** The active return is regressed by OLS with an intercept,
:math:`a_t=\alpha+\beta^\top f_t+e_t` (:func:`qrlab.stats.ols`, covariance estimator explicit).
Residuals of OLS with an intercept sum to zero, so
:math:`\sum_t a_t = T\alpha + \sum_k\beta_k\sum_t f_{k,t}` exactly. Alpha carries its standard
error and :math:`t`-statistic; :math:`|t|<2` is labelled not significant, and even
:math:`|t|\ge 2` is one test among many, not proof of skill.

**Currency (one period).** A segment's base return is :math:`(1+\ell_s)(1+x_s)-1`; the base
return of a portfolio splits into local markets :math:`\sum w_s\ell_s`, currency
:math:`\sum w_s x_s` and the cross term :math:`\sum w_s\ell_s x_s`. Active attribution is the
difference between portfolio and benchmark; the three parts add up to the active base return.
Forward premia and hedging costs (Karnosky-Singer) are not modelled.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.stats.regression import CovType, ols

__all__ = [
    "CurrencyAttribution",
    "CurrencySplit",
    "FactorAttribution",
    "currency_attribution",
    "factor_attribution",
]

SIGNIFICANCE_T = 2.0


@dataclass(frozen=True)
class FactorAttribution:
    """Exposures, contributions and alpha of an active return series."""

    betas: pd.Series
    contributions: pd.Series
    alpha: float
    alpha_se: float
    alpha_t: float
    alpha_significant: bool
    alpha_total: float
    residual_total: float
    active_total: float
    r_squared: float
    n_obs: int
    cov_type: str


@dataclass(frozen=True)
class CurrencySplit:
    """Local, currency and cross parts of one base-currency return."""

    local: float
    currency: float
    cross: float

    @property
    def total(self) -> float:
        """Return the base-currency return the parts add up to."""
        return self.local + self.currency + self.cross


@dataclass(frozen=True)
class CurrencyAttribution:
    """Currency split of the portfolio, the benchmark and their difference."""

    portfolio: CurrencySplit
    benchmark: CurrencySplit
    active: CurrencySplit


def factor_attribution(
    active: pd.Series,
    factors: pd.DataFrame,
    *,
    cov_type: CovType,
    hac_lags: int | None,
) -> FactorAttribution:
    """Attribute an active return series to factors, alpha and residual."""
    fit = ols(active, factors, add_intercept=True, cov_type=cov_type, hac_lags=hac_lags)
    betas = fit.params.drop("const")
    sums = factors.sum(axis=0)
    contributions = betas * sums.reindex(betas.index)
    alpha = float(fit.params["const"])
    alpha_t = float(fit.tvalues["const"])
    n = fit.nobs
    active_total = float(active.sum())
    explained = n * alpha + float(contributions.sum())
    return FactorAttribution(
        betas=betas,
        contributions=contributions,
        alpha=alpha,
        alpha_se=float(fit.std_errors["const"]),
        alpha_t=alpha_t,
        alpha_significant=abs(alpha_t) >= SIGNIFICANCE_T,
        alpha_total=n * alpha,
        residual_total=active_total - explained,
        active_total=active_total,
        r_squared=fit.r_squared,
        n_obs=n,
        cov_type=fit.cov_type.value,
    )


def currency_attribution(
    portfolio_weights: pd.Series,
    benchmark_weights: pd.Series,
    portfolio_local: pd.Series,
    benchmark_local: pd.Series,
    currency_returns: pd.Series,
) -> CurrencyAttribution:
    """Split one period's base returns into local, currency and cross parts (by segment)."""
    segments = list(portfolio_weights.index)
    for series, name in (
        (benchmark_weights, "benchmark_weights"),
        (portfolio_local, "portfolio_local"),
        (benchmark_local, "benchmark_local"),
        (currency_returns, "currency_returns"),
    ):
        if set(series.index) != set(segments):
            raise ValidationError(f"{name} must cover exactly the segments {segments}")
    x = currency_returns.reindex(segments).to_numpy(dtype=np.float64)
    parts = []
    for weights, local, name in (
        (portfolio_weights, portfolio_local, "portfolio"),
        (benchmark_weights, benchmark_local, "benchmark"),
    ):
        w = weights.reindex(segments).to_numpy(dtype=np.float64)
        ell = local.reindex(segments).to_numpy(dtype=np.float64)
        if not (np.all(np.isfinite(w)) and np.all(np.isfinite(ell)) and np.all(np.isfinite(x))):
            raise ValidationError(f"{name} inputs must be finite")
        if abs(float(w.sum()) - 1.0) > 1e-9:
            raise ValidationError(f"{name} weights must sum to 1")
        parts.append(CurrencySplit(float(w @ ell), float(w @ x), float(w @ (ell * x))))
    p, b = parts
    active = CurrencySplit(p.local - b.local, p.currency - b.currency, p.cross - b.cross)
    return CurrencyAttribution(p, b, active)
