r"""Study 1: volatility-managed factors (Moreira and Muir 2017; Cederburg et al. 2020).

Design note: ``docs/design/5.3-study-1-volatility-managed.md``.

- **Realised variance** of month :math:`t`: :math:`RV_t=\sum_{d\in t}f_d^2` (or with the
  within-month mean removed, ``demean=True``), from daily factor returns.
- **Signal**: :math:`1/RV_{t-\ell}` labelled at month :math:`t`, shifted by calendar months
  (``lag`` :math:`\ell\ge 1`), so the weight of a month uses only variances already observed.
- **In sample** (the paper's spanning test): :math:`f^\sigma_t=c\,f_t/RV_{t-1}` with :math:`c`
  chosen on the **full sample** so that :math:`f^\sigma` and :math:`f` have the same volatility
  (this uses future information by construction); then
  :math:`f^\sigma_t=\alpha+\beta f_t+\varepsilon_t` with Newey-West standard errors.
- **Out of sample** (real-time investor): :math:`c_t` from months before :math:`t` only
  (expanding window after ``burn_in`` months), weight :math:`w_t=\min(c_t/RV_{t-1},\text{cap})`,
  net return :math:`w_tf_t-\kappa|w_t-w_{t-1}|` (the initial position is not charged, as for the
  unmanaged factor), compared with :math:`f_t` on the same months by the Ledoit-Wolf HAC test and
  a stationary-bootstrap interval of the Sharpe-ratio difference.

Inputs are monthly series indexed by month-end dates; the overlap of factor and signal must be
consecutive months (a gap raises instead of silently shifting the alignment). Variances and
Sharpe ratios use ``ddof=1``. The factors are excess (or zero-cost) returns, so no risk-free rate
is subtracted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, validate_series
from qrlab.metrics.sharpe_inference import (
    ProbabilisticSharpe,
    SharpeDifference,
    deflated_sharpe_ratio,
    sharpe_difference_bootstrap,
    sharpe_difference_hac,
)
from qrlab.stats.bootstrap import MIN_RESAMPLES, BootstrapResult
from qrlab.stats.multiple_testing import Correction, adjust_pvalues
from qrlab.stats.regression import CovType, ols

__all__ = [
    "BootstrapSettings",
    "InSampleResult",
    "OutOfSampleResult",
    "best_deflated_sharpe",
    "full_sample_scale",
    "in_sample_spanning",
    "in_sample_table",
    "inverse_variance_signal",
    "out_of_sample_comparison",
    "out_of_sample_table",
    "real_time_weights",
    "realized_variance",
    "turnover_costs",
]


@dataclass(frozen=True)
class BootstrapSettings:
    """Stationary-bootstrap settings for the Sharpe-ratio difference."""

    mean_block_length: float
    n_resamples: int
    confidence: float

    def __post_init__(self) -> None:
        """Validate every setting."""
        if not (math.isfinite(self.mean_block_length) and self.mean_block_length >= 1.0):
            raise ValidationError("mean_block_length must be a finite number >= 1")
        if type(self.n_resamples) is not int or self.n_resamples < MIN_RESAMPLES:
            raise ValidationError(f"n_resamples must be an int >= {MIN_RESAMPLES}")
        if not 0.0 < self.confidence < 1.0:
            raise ValidationError("confidence must be in (0, 1)")


@dataclass(frozen=True)
class InSampleResult:
    r"""Spanning regression of the managed factor on the unmanaged factor (full-sample ``c``).

    ``alpha`` is per month and ``alpha_annual`` is ``periods_per_year * alpha``; the appraisal
    ratio is :math:`\alpha/\sigma_\varepsilon` annualised with :math:`\sqrt{12}`, where
    :math:`\sigma_\varepsilon` is the standard error of the regression (``n - 2`` degrees of
    freedom). Sharpe ratios are annualised.
    """

    scale: float
    alpha: float
    alpha_annual: float
    alpha_t: float
    alpha_pvalue: float
    beta: float
    appraisal_ratio: float
    r_squared: float
    sharpe_factor: float
    sharpe_managed: float
    n: int
    start: pd.Timestamp
    end: pd.Timestamp
    hac_lags: int


@dataclass(frozen=True)
class OutOfSampleResult:
    """Real-time managed factor, net of costs, against the unmanaged factor on the same months."""

    cap: float
    cost_per_unit: float
    weights: pd.Series
    managed_net: pd.Series
    factor: pd.Series
    sharpe_factor: float
    sharpe_managed: float
    test: SharpeDifference
    interval: BootstrapResult
    mean_weight: float
    max_weight: float
    annual_turnover: float
    n: int
    start: pd.Timestamp
    end: pd.Timestamp


# ------------------------------------------------------------------------------- building blocks
def realized_variance(daily: pd.Series, *, demean: bool) -> pd.Series:
    """Return the monthly realised variance of daily returns, indexed by month-end dates.

    Parameters
    ----------
    daily
        Daily factor returns in decimals, without NaN.
    demean
        Remove each month's mean daily return before squaring (Moreira and Muir's definition);
        ``False`` sums raw squares.

    Raises
    ------
    ValidationError
        For NaN, a month with fewer than 2 daily returns, or a month with zero variance.
    """
    if not isinstance(demean, bool):
        raise ValidationError("demean must be True or False")
    values = validate_series(daily, nan_policy=NanPolicy.RAISE, name="daily")
    month = pd.DatetimeIndex(values.index).normalize() + pd.offsets.MonthEnd(0)
    grouped = values.groupby(month)
    counts = grouped.count()
    if (counts < 2).any():
        short = [d.date().isoformat() for d in counts.index[counts < 2]]
        raise ValidationError(f"every month needs at least 2 daily returns; short months: {short}")
    if demean:
        deviations = values - grouped.transform("mean")
        rv = (deviations**2).groupby(month).sum()
    else:
        rv = (values**2).groupby(month).sum()
    if not (rv > 0).all():
        zero = [d.date().isoformat() for d in rv.index[~(rv > 0)]]
        raise ValidationError(f"zero realised variance in months {zero}")
    rv.index = pd.DatetimeIndex(rv.index, name="month")
    return rv.rename("realized_variance")


def inverse_variance_signal(variance: pd.Series, *, lag: int) -> pd.Series:
    """Return :math:`1/RV_{t-lag}` labelled at month :math:`t` (calendar-month shift)."""
    if type(lag) is not int or lag < 1:
        raise ValidationError(f"lag must be an int >= 1, got {lag!r}")
    rv = validate_series(variance, nan_policy=NanPolicy.RAISE, name="variance")
    _check_month_ends(rv.index, "variance")
    if not (rv > 0).all():
        raise ValidationError("variance must be positive")
    shifted = 1.0 / rv
    shifted.index = pd.DatetimeIndex(rv.index + pd.offsets.MonthEnd(lag), name="month")
    return shifted.rename("signal")


def full_sample_scale(factor: pd.Series, signal: pd.Series) -> float:
    r"""Return :math:`c` such that :math:`c\,s_tf_t` has the volatility of :math:`f_t`.

    Uses the whole overlap of ``factor`` and ``signal``: in sample by construction.
    """
    f, s = _align(factor, signal, min_n=3)
    return _scale(f.to_numpy(), (s * f).to_numpy())


def real_time_weights(
    factor: pd.Series, signal: pd.Series, *, burn_in: int, cap: float
) -> pd.Series:
    r"""Return the real-time weights :math:`\min(c_t s_t, cap)` after ``burn_in`` months.

    :math:`c_t` uses factor returns and signals of the months before :math:`t` only (expanding
    window). ``cap`` is the maximum leverage; ``math.inf`` means no cap.
    """
    if type(cap) is not float or math.isnan(cap) or cap <= 0:
        raise ValidationError(f"cap must be a positive float (math.inf for no cap), got {cap!r}")
    f, s = _align(factor, signal, min_n=3)
    if type(burn_in) is not int or burn_in < 2 or burn_in >= len(f):
        raise ValidationError(
            f"burn_in must be an int between 2 and {len(f) - 1} (months of overlap - 1)"
        )
    fv, mv = f.to_numpy(), (s * f).to_numpy()
    weights = np.empty(len(f) - burn_in)
    for i in range(burn_in, len(f)):
        weights[i - burn_in] = min(_scale(fv[:i], mv[:i]) * float(s.iloc[i]), cap)
    return pd.Series(weights, index=f.index[burn_in:], name="weight")


def turnover_costs(weights: pd.Series, *, cost_per_unit: float) -> pd.Series:
    r"""Return :math:`\kappa|w_t-w_{t-1}|`, zero for the first (initial) position."""
    if type(cost_per_unit) is not float or not (
        math.isfinite(cost_per_unit) and cost_per_unit >= 0
    ):
        raise ValidationError(f"cost_per_unit must be a finite float >= 0, got {cost_per_unit!r}")
    w = validate_series(weights, nan_policy=NanPolicy.RAISE, name="weights")
    return (w.diff().abs().fillna(0.0) * cost_per_unit).rename("cost")


# ------------------------------------------------------------------------------------ analyses
def in_sample_spanning(
    factor: pd.Series, signal: pd.Series, *, hac_lags: int, periods_per_year: int
) -> InSampleResult:
    """Run the paper's spanning regression with the full-sample scale (in sample)."""
    _check_periods(periods_per_year)
    if type(hac_lags) is not int or hac_lags < 0:
        raise ValidationError(f"hac_lags must be an int >= 0, got {hac_lags!r}")
    f, s = _align(factor, signal, min_n=3)
    c = _scale(f.to_numpy(), (s * f).to_numpy())
    managed = (c * s * f).rename("managed")
    fit = ols(
        managed,
        f.rename("factor").to_frame(),
        add_intercept=True,
        cov_type=CovType.HAC,
        hac_lags=hac_lags,
    )
    alpha = float(fit.params["const"])
    sigma = math.sqrt(float((fit.residuals**2).sum()) / fit.df_resid)
    root = math.sqrt(periods_per_year)
    return InSampleResult(
        scale=c,
        alpha=alpha,
        alpha_annual=periods_per_year * alpha,
        alpha_t=float(fit.tvalues["const"]),
        alpha_pvalue=float(fit.pvalues["const"]),
        beta=float(fit.params["factor"]),
        appraisal_ratio=alpha / sigma * root,
        r_squared=fit.r_squared,
        sharpe_factor=_sharpe(f) * root,
        sharpe_managed=_sharpe(managed) * root,
        n=len(f),
        start=f.index[0],
        end=f.index[-1],
        hac_lags=hac_lags,
    )


def out_of_sample_comparison(
    factor: pd.Series,
    signal: pd.Series,
    *,
    burn_in: int,
    cap: float,
    cost_per_unit: float,
    hac_lags: int,
    periods_per_year: int,
    bootstrap: BootstrapSettings,
    rng: np.random.Generator,
) -> OutOfSampleResult:
    """Compare the real-time managed factor, net of costs, with the factor on the same months."""
    _check_periods(periods_per_year)
    weights = real_time_weights(factor, signal, burn_in=burn_in, cap=cap)
    costs = turnover_costs(weights, cost_per_unit=cost_per_unit)
    f, _ = _align(factor, signal, min_n=3)
    unmanaged = f.reindex(weights.index).rename("factor")
    managed = (weights * unmanaged - costs).rename("managed_net")
    test = sharpe_difference_hac(managed, unmanaged, hac_lags=hac_lags)
    interval = sharpe_difference_bootstrap(
        managed,
        unmanaged,
        mean_block_length=bootstrap.mean_block_length,
        n_resamples=bootstrap.n_resamples,
        confidence=bootstrap.confidence,
        rng=rng,
    )
    root = math.sqrt(periods_per_year)
    return OutOfSampleResult(
        cap=cap,
        cost_per_unit=cost_per_unit,
        weights=weights,
        managed_net=managed,
        factor=unmanaged,
        sharpe_factor=_sharpe(unmanaged) * root,
        sharpe_managed=_sharpe(managed) * root,
        test=test,
        interval=interval,
        mean_weight=float(weights.mean()),
        max_weight=float(weights.max()),
        annual_turnover=float(weights.diff().abs().mean()) * periods_per_year,
        n=len(weights),
        start=weights.index[0],
        end=weights.index[-1],
    )


# ---------------------------------------------------------------------------------- tables
def in_sample_table(results: Mapping[str, InSampleResult], *, significance: float) -> pd.DataFrame:
    """One row per factor, with Holm and Benjamini-Hochberg adjusted alpha p-values."""
    if not results:
        raise ValidationError("at least one in-sample result is required")
    frame = pd.DataFrame(
        {
            name: {
                "start": r.start.date().isoformat(),
                "end": r.end.date().isoformat(),
                "n": r.n,
                "scale": r.scale,
                "alpha_annual": r.alpha_annual,
                "alpha_t": r.alpha_t,
                "alpha_pvalue": r.alpha_pvalue,
                "beta": r.beta,
                "appraisal_ratio": r.appraisal_ratio,
                "r_squared": r.r_squared,
                "sharpe_factor": r.sharpe_factor,
                "sharpe_managed": r.sharpe_managed,
            }
            for name, r in results.items()
        }
    ).T
    frame.index.name = "factor"
    pvalues = frame["alpha_pvalue"].astype("float64")
    frame["alpha_holm"] = _adjusted(pvalues, Correction.HOLM, significance)
    frame["alpha_bh"] = _adjusted(pvalues, Correction.BENJAMINI_HOCHBERG, significance)
    return frame


def out_of_sample_table(
    results: Sequence[tuple[str, OutOfSampleResult]], *, significance: float
) -> pd.DataFrame:
    """One row per factor, cap and cost; corrections across factors within each cap and cost."""
    if not results:
        raise ValidationError("at least one out-of-sample result is required")
    rows = [
        {
            "factor": name,
            "cap": r.cap,
            "cost_per_unit": r.cost_per_unit,
            "start": r.start.date().isoformat(),
            "end": r.end.date().isoformat(),
            "n": r.n,
            "sharpe_factor": r.sharpe_factor,
            "sharpe_managed_net": r.sharpe_managed,
            "difference_per_period": r.test.difference,
            "z_hac": r.test.z,
            "pvalue_hac": r.test.pvalue,
            "bootstrap_low": r.interval.low,
            "bootstrap_high": r.interval.high,
            "mean_weight": r.mean_weight,
            "max_weight": r.max_weight,
            "annual_turnover": r.annual_turnover,
        }
        for name, r in results
    ]
    frame = pd.DataFrame(rows)
    frame["holm"] = np.nan
    frame["bh"] = np.nan
    for _, group in frame.groupby(["cap", "cost_per_unit"], sort=False):
        pvalues = pd.Series(group["pvalue_hac"].to_numpy(), index=group.index)
        frame.loc[group.index, "holm"] = _adjusted(pvalues, Correction.HOLM, significance)
        frame.loc[group.index, "bh"] = _adjusted(
            pvalues, Correction.BENJAMINI_HOCHBERG, significance
        )
    return frame


def best_deflated_sharpe(
    results: Sequence[tuple[str, OutOfSampleResult]], *, configurations: int
) -> tuple[str, ProbabilisticSharpe, int] | None:
    """Return the DSR of the variant with the highest per-period net Sharpe ratio.

    The number of trials is the number of variants in ``results`` times ``configurations``
    (the configurations tried, from the runner's ledger); the variance of the trial Sharpe ratios
    is estimated from ``results``. ``None`` when fewer than two variants make that impossible.
    """
    if type(configurations) is not int or configurations < 1:
        raise ValidationError("configurations must be an int >= 1")
    if len(results) < 2:
        return None
    labelled = {
        f"{name} | cap {r.cap:g} | cost {r.cost_per_unit * 1e4:g} bp": r.managed_net
        for name, r in results
    }
    sharpes = pd.Series({label: _sharpe(series) for label, series in labelled.items()})
    best = str(sharpes.idxmax())
    n_trials = len(results) * configurations
    dsr = deflated_sharpe_ratio(
        labelled[best], n_trials=n_trials, trial_sharpes=sharpes, variance=None
    )
    return best, dsr, n_trials


# ------------------------------------------------------------------------------------- helpers
def _align(factor: pd.Series, signal: pd.Series, *, min_n: int) -> tuple[pd.Series, pd.Series]:
    f = validate_series(factor, nan_policy=NanPolicy.RAISE, name="factor")
    s = validate_series(signal, nan_policy=NanPolicy.RAISE, name="signal")
    _check_month_ends(f.index, "factor")
    _check_month_ends(s.index, "signal")
    common = f.index.intersection(s.index)
    if len(common) < min_n:
        raise ValidationError(
            f"factor and signal overlap in {len(common)} months; need at least {min_n}"
        )
    expected = pd.date_range(common[0], common[-1], freq="ME")
    if len(expected) != len(common):
        raise ValidationError(
            "factor and signal must overlap in consecutive months "
            f"({len(expected) - len(common)} months missing between {common[0].date()} "
            f"and {common[-1].date()})"
        )
    return f.loc[common], s.loc[common]


def _check_month_ends(index: pd.Index, name: str) -> None:
    dates = pd.DatetimeIndex(index)
    if not (dates == dates.normalize() + pd.offsets.MonthEnd(0)).all():
        raise ValidationError(f"{name} must be indexed by month-end dates")


def _scale(factor: np.ndarray, managed_unscaled: np.ndarray) -> float:
    sd_f = float(np.std(factor, ddof=1))
    sd_m = float(np.std(managed_unscaled, ddof=1))
    if not (sd_f > 0 and sd_m > 0):
        raise ValidationError("cannot scale: a series has zero variance")
    return sd_f / sd_m


def _sharpe(series: pd.Series) -> float:
    # Callers have already rejected zero variance (scale, HAC test).
    return float(series.mean()) / float(series.std(ddof=1))


def _check_periods(periods_per_year: int) -> None:
    if type(periods_per_year) is not int or periods_per_year < 1:
        raise ValidationError(f"periods_per_year must be an int >= 1, got {periods_per_year!r}")


def _adjusted(pvalues: pd.Series, method: Correction, significance: float) -> pd.Series:
    return adjust_pvalues(pvalues, method=method, alpha=significance).adjusted
