r"""Study 2: 1/N against optimised portfolios (DeMiguel, Garlappi and Uppal 2009), extended.

Design note: ``docs/design/5.3-study-2-one-over-n.md``.

- **Targets.** At the end of each month :math:`t` a strategy sees the monthly excess returns of
  months :math:`t-M+1,\dots,t` only (rolling window of :math:`M` months) and returns long-only,
  fully invested weights. Value weights (and the Black-Litterman prior) use the market weights
  of month :math:`t-1`.
- **Execution.** Targets go through the backtest engine on daily total returns, executed one
  trading day after the decision (the last trading day of the month), with proportional costs.
- **Performance.** Monthly net returns are compounded from the daily net returns, minus the
  monthly risk-free rate; the month of the first decision is excluded. Sharpe ratios and the
  certainty equivalent :math:`\text{CEQ}=\hat\mu-\tfrac{\gamma}{2}\hat\sigma^2` (``ddof=1``) are
  annualised with 12 months.

Strategies (names fixed by the design note): ``ew`` (1/N), ``vw`` (lagged market weights),
``maxsharpe_sample``, ``minvar_sample``, ``minvar_lw``, ``maxsharpe_bl``, ``risk_parity``
(equal risk contributions, Ledoit-Wolf) and ``hrp`` (sample covariance). The two maximum-Sharpe
strategies fall back to the minimum variance of the same covariance in months where no expected
excess return is positive; the number of such months is reported.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.backtest.engine import BacktestResult, TradeOnSignal, run_backtest_targets
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy, validate_frame, validate_series
from qrlab.metrics.drawdown import max_drawdown
from qrlab.metrics.sharpe_inference import (
    ProbabilisticSharpe,
    SharpeDifference,
    deflated_sharpe_ratio,
    sharpe_difference_bootstrap,
    sharpe_difference_hac,
    sharpe_difference_jkm,
)
from qrlab.optimization.constraints import Constraints
from qrlab.optimization.mean_variance import maximum_sharpe, minimum_variance
from qrlab.optimization.rebalancing import CostModel
from qrlab.optimization.risk_based import (
    black_litterman,
    hierarchical_risk_parity,
    risk_budgeting,
)
from qrlab.risk.covariance import CovarianceEstimate, ledoit_wolf_covariance, sample_covariance
from qrlab.stats.bootstrap import BootstrapResult, stationary_bootstrap
from qrlab.stats.multiple_testing import Correction, adjust_pvalues
from qrlab.studies.volatility_managed import BootstrapSettings

__all__ = [
    "EXECUTION_LAG_DAYS",
    "PERIODS_PER_YEAR",
    "STRATEGIES",
    "BootstrapSettings",
    "Comparison",
    "Performance",
    "Targets",
    "best_deflated_sharpe",
    "certainty_equivalent",
    "compare",
    "comparison_table",
    "last_trading_days",
    "market_weights",
    "monthly_excess_returns",
    "monthly_net_excess",
    "pair_table",
    "performance",
    "performance_table",
    "rolling_targets",
    "run_targets",
]

STRATEGIES = (
    "ew",
    "vw",
    "maxsharpe_sample",
    "minvar_sample",
    "minvar_lw",
    "maxsharpe_bl",
    "risk_parity",
    "hrp",
)
PERIODS_PER_YEAR = 12
EXECUTION_LAG_DAYS = 1
_INITIAL_VALUE = Money.of("100000", "USD")
_LONG_ONLY = Constraints(long_only=True, bounds={}, groups={}, turnover=None, current=None)
_NEGATIVE_TOLERANCE = 1e-10


@dataclass(frozen=True)
class Targets:
    """Target weights by decision month, and the months a maximum-Sharpe strategy fell back."""

    strategy: str
    weights: pd.DataFrame
    fallbacks: int


@dataclass(frozen=True)
class Performance:
    """Annualised out-of-sample performance of monthly excess returns."""

    mean: float
    volatility: float
    sharpe: float
    ceq: float
    turnover: float  # average monthly turnover (sum of |trades| / value)
    max_drawdown: float
    fallbacks: int
    n: int
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class Comparison:
    """A strategy against a benchmark on the same months."""

    hac: SharpeDifference
    jkm: SharpeDifference
    sharpe_interval: BootstrapResult
    ceq_interval: BootstrapResult


# ------------------------------------------------------------------------------- data helpers
def monthly_excess_returns(monthly: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    """Subtract the monthly risk-free rate; every month of ``monthly`` needs a rate."""
    returns = validate_frame(monthly, nan_policy=NanPolicy.RAISE, name="monthly")
    rate = validate_series(rf, nan_policy=NanPolicy.RAISE, name="rf")
    missing = pd.DatetimeIndex(returns.index).difference(pd.DatetimeIndex(rate.index))
    if len(missing):
        raise ValidationError(f"no risk-free rate for {len(missing)} months, e.g. {missing[0]}")
    return returns.sub(rate.loc[returns.index], axis=0)


def market_weights(firms: pd.DataFrame, size: pd.DataFrame) -> pd.DataFrame:
    """Return number of firms x average size, normalised per month.

    Months with a missing or non-positive capitalisation are left entirely missing.
    """
    if not (firms.index.equals(size.index) and list(firms.columns) == list(size.columns)):
        raise ValidationError("firms and size must have the same dates and assets")
    caps = firms.astype("float64") * size.astype("float64")
    complete = caps.notna().all(axis=1) & (caps > 0).all(axis=1)
    weights = caps.div(caps.sum(axis=1), axis=0)
    weights.loc[~complete] = np.nan
    return weights


def last_trading_days(daily_index: pd.DatetimeIndex, months: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return the last daily date in each month of ``months`` (month-end labels)."""
    days = pd.Series(daily_index, index=daily_index)
    last = days.groupby(daily_index + pd.offsets.MonthEnd(0)).max()
    missing = months.difference(pd.DatetimeIndex(last.index))
    if len(missing):
        raise ValidationError(f"no daily data in month {missing[0].date()}")
    return pd.DatetimeIndex(last.loc[months].to_numpy())


def certainty_equivalent(excess: pd.Series, *, risk_aversion: float) -> float:
    r"""Return the per-period :math:`\hat\mu - \gamma\hat\sigma^2/2` (``ddof=1``)."""
    if type(risk_aversion) is not float or not (math.isfinite(risk_aversion) and risk_aversion > 0):
        raise ValidationError("risk_aversion must be a positive float")
    return float(excess.mean()) - 0.5 * risk_aversion * float(excess.var(ddof=1))


# ------------------------------------------------------------------------------------ targets
def rolling_targets(
    excess: pd.DataFrame,
    *,
    strategy: str,
    window: int,
    market: pd.DataFrame | None,
    bl_risk_aversion: float,
    first: pd.Timestamp | None,
) -> Targets:
    r"""Return the strategy's target weights at every month from ``first`` on.

    Parameters
    ----------
    excess
        Monthly excess returns, month-end index, no missing values.
    strategy
        One of :data:`STRATEGIES`.
    window
        Months in the rolling estimation window (the decision month included).
    market
        Market weights by month (required for ``vw`` and ``maxsharpe_bl``); the decision at
        month :math:`t` uses the row of month :math:`t-1`.
    bl_risk_aversion
        :math:`\delta` of the Black-Litterman prior :math:`\pi=\delta\Sigma w_{mkt}`;
        :math:`\tau = 1/window`.
    first
        First decision month (default: the first month with a full window).
    """
    if strategy not in STRATEGIES:
        raise ValidationError(f"unknown strategy {strategy!r}; known: {list(STRATEGIES)}")
    returns = validate_frame(excess, nan_policy=NanPolicy.RAISE, name="excess")
    if type(window) is not int or not 2 <= window <= len(returns):
        raise ValidationError(f"window must be an int between 2 and {len(returns)}")
    if strategy in ("vw", "maxsharpe_bl") and market is None:
        raise ValidationError(f"{strategy} needs market weights")
    lagged = None if market is None else market.shift(1)
    start = window - 1
    if first is not None:
        position = int(returns.index.get_indexer(pd.DatetimeIndex([first]))[0])
        if position < start:
            raise ValidationError(f"first decision {first.date()} has fewer than {window} months")
        start = position
    rows, fallbacks = [], 0
    for i in range(start, len(returns)):
        sample = returns.iloc[i - window + 1 : i + 1]
        mkt = None if lagged is None else lagged.loc[returns.index[i]]
        weights, fell_back = _decide(strategy, sample, mkt, bl_risk_aversion, window)
        rows.append(weights)
        fallbacks += int(fell_back)
    frame = pd.DataFrame(rows, index=returns.index[start:], columns=returns.columns)
    return Targets(strategy=strategy, weights=frame, fallbacks=fallbacks)


def _decide(
    strategy: str,
    sample: pd.DataFrame,
    market: pd.Series | None,
    delta: float,
    window: int,
) -> tuple[pd.Series, bool]:
    assets = sample.columns
    if strategy == "ew":
        return pd.Series(1.0 / len(assets), index=assets), False
    if strategy in ("vw", "maxsharpe_bl"):
        if market is None or market.isna().any():
            raise ValidationError(f"no market weights for the decision after {sample.index[-1]}")
        if strategy == "vw":
            return _clean(market.reindex(assets)), False
    if strategy in ("maxsharpe_sample", "minvar_sample", "hrp"):
        cov = sample_covariance(sample, kind=ReturnKind.SIMPLE, missing=NanPolicy.RAISE)
    else:
        cov = ledoit_wolf_covariance(sample, kind=ReturnKind.SIMPLE, missing=NanPolicy.RAISE)
    if strategy in ("minvar_sample", "minvar_lw"):
        return _minvar(cov), False
    if strategy == "risk_parity":
        return _clean(
            risk_budgeting(cov, pd.Series(1.0 / len(assets), index=assets)).weights
        ), False
    if strategy == "hrp":
        return _clean(hierarchical_risk_parity(cov).weights), False
    expected = sample.mean()
    moments_cov = cov
    if strategy == "maxsharpe_bl":
        posterior = black_litterman(
            cov,
            market_weights=market.reindex(assets),  # type: ignore[union-attr]
            risk_aversion=delta,
            tau=1.0 / window,
            views=pd.DataFrame(np.eye(len(assets)), index=assets, columns=assets),
            view_returns=pd.Series(expected.to_numpy(), index=assets),
            omega=None,
        )
        expected, moments_cov = posterior.mean, posterior.covariance
    if not (expected > 0).any():
        return _minvar(cov), True
    return _clean(maximum_sharpe(expected, moments_cov).weights), False


def _minvar(cov: CovarianceEstimate) -> pd.Series:
    return _clean(minimum_variance(cov, _LONG_ONLY).weights)


def _clean(weights: pd.Series) -> pd.Series:
    """Remove solver noise below zero and renormalise (larger negatives raise)."""
    if (weights < -_NEGATIVE_TOLERANCE).any():
        raise ValidationError(f"negative long-only weights {weights[weights < 0].to_dict()}")
    clipped = weights.clip(lower=0.0).astype("float64")
    return clipped / float(clipped.sum())


# --------------------------------------------------------------------------- engine and returns
def run_targets(daily: pd.DataFrame, targets: pd.DataFrame, *, cost: float) -> BacktestResult:
    """Execute monthly targets on daily total returns, one trading day after each decision.

    The backtest starts on the first decision day holding the first target; ``cost`` is the
    proportional cost per unit traded.
    """
    if type(cost) is not float or not (math.isfinite(cost) and cost >= 0):
        raise ValidationError(f"cost must be a finite float >= 0, got {cost!r}")
    days = last_trading_days(pd.DatetimeIndex(daily.index), pd.DatetimeIndex(targets.index))
    decided = targets.set_axis(days, axis=0)
    returns = daily.loc[days[0] :]
    return run_backtest_targets(
        returns,
        decided,
        execution_lag=EXECUTION_LAG_DAYS,
        policy=TradeOnSignal(),
        costs=CostModel(cost, 0.0),
        taxes=None,
        initial_weights=decided.iloc[0],
        initial_value=_INITIAL_VALUE,
        long_only=True,
    )


def monthly_net_excess(result: BacktestResult, rf: pd.Series) -> pd.Series:
    """Compound daily net returns by month, subtract the monthly risk-free rate.

    The first month (the month of the first decision, only partly invested) is excluded.
    """
    daily = result.net_returns
    month = pd.DatetimeIndex(daily.index).normalize() + pd.offsets.MonthEnd(0)
    monthly = (1.0 + daily).groupby(month).prod() - 1.0
    first_decision = pd.Timestamp(result.net_values.index[0]) + pd.offsets.MonthEnd(0)
    monthly = monthly.loc[monthly.index > first_decision]
    missing = pd.DatetimeIndex(monthly.index).difference(pd.DatetimeIndex(rf.index))
    if len(missing):
        raise ValidationError(f"no risk-free rate for {missing[0].date()}")
    return (monthly - rf.loc[monthly.index]).rename("excess")


# ----------------------------------------------------------------------------- evaluation
def performance(
    excess: pd.Series, *, turnover: float, ceq_risk_aversion: float, fallbacks: int
) -> Performance:
    """Annualised mean, volatility, Sharpe ratio and CEQ, with turnover and drawdown."""
    values = validate_series(excess, nan_policy=NanPolicy.RAISE, name="excess")
    sd = float(values.std(ddof=1))
    if not sd > 0:
        raise ValidationError("excess returns have zero variance")
    return Performance(
        mean=PERIODS_PER_YEAR * float(values.mean()),
        volatility=sd * math.sqrt(PERIODS_PER_YEAR),
        sharpe=float(values.mean()) / sd * math.sqrt(PERIODS_PER_YEAR),
        ceq=PERIODS_PER_YEAR * certainty_equivalent(values, risk_aversion=ceq_risk_aversion),
        turnover=turnover,
        max_drawdown=max_drawdown(values),
        fallbacks=fallbacks,
        n=len(values),
        start=values.index[0],
        end=values.index[-1],
    )


def performance_table(
    results: Mapping[tuple[str, int, float, str], Performance],
) -> pd.DataFrame:
    """One row per dataset, window, cost and strategy."""
    if not results:
        raise ValidationError("at least one performance result is required")
    return pd.DataFrame(
        [
            {
                "dataset": dataset,
                "window": window,
                "cost_per_unit": cost,
                "strategy": strategy,
                "mean": r.mean,
                "volatility": r.volatility,
                "sharpe": r.sharpe,
                "ceq": r.ceq,
                "turnover": r.turnover,
                "max_drawdown": r.max_drawdown,
                "fallbacks": r.fallbacks,
                "n": r.n,
                "start": r.start.date().isoformat(),
                "end": r.end.date().isoformat(),
            }
            for (dataset, window, cost, strategy), r in results.items()
        ]
    )


def compare(
    candidate: pd.Series,
    benchmark: pd.Series,
    *,
    hac_lags: int,
    bootstrap: BootstrapSettings,
    rng: np.random.Generator,
    ceq_risk_aversion: float,
) -> Comparison:
    """Test the per-month Sharpe-ratio difference and interval the CEQ difference."""
    hac = sharpe_difference_hac(candidate, benchmark, hac_lags=hac_lags)
    jkm = sharpe_difference_jkm(candidate, benchmark)
    sharpe_interval = sharpe_difference_bootstrap(
        candidate,
        benchmark,
        mean_block_length=bootstrap.mean_block_length,
        n_resamples=bootstrap.n_resamples,
        confidence=bootstrap.confidence,
        rng=rng,
    )
    gamma = ceq_risk_aversion
    certainty_equivalent(candidate, risk_aversion=gamma)  # validates gamma

    def ceq_difference(values: np.ndarray) -> float:
        a, b = values[:, 0], values[:, 1]
        return float(
            a.mean() - 0.5 * gamma * a.var(ddof=1) - b.mean() + 0.5 * gamma * b.var(ddof=1)
        )

    ceq_interval = stationary_bootstrap(
        pd.concat([candidate.rename("candidate"), benchmark.rename("benchmark")], axis=1),
        ceq_difference,
        mean_block_length=bootstrap.mean_block_length,
        n_resamples=bootstrap.n_resamples,
        confidence=bootstrap.confidence,
        rng=rng,
    )
    return Comparison(hac, jkm, sharpe_interval, ceq_interval)


def comparison_table(
    comparisons: Mapping[tuple[str, int, float, str], Comparison], *, significance: float
) -> pd.DataFrame:
    """Strategies against 1/N; Holm and BH across strategies in each dataset, window and cost."""
    if not comparisons:
        raise ValidationError("at least one comparison is required")
    frame = pd.DataFrame(
        [
            {
                "dataset": dataset,
                "window": window,
                "cost_per_unit": cost,
                "strategy": strategy,
                **_comparison_row(c),
            }
            for (dataset, window, cost, strategy), c in comparisons.items()
        ]
    )
    return _corrected(frame, ["dataset", "window", "cost_per_unit"], significance)


def pair_table(
    comparisons: Mapping[tuple[str, int, float, str, str], Comparison], *, significance: float
) -> pd.DataFrame:
    """Robust against sample-estimate pairs; Holm and BH across pairs in each group."""
    if not comparisons:
        raise ValidationError("at least one pair comparison is required")
    frame = pd.DataFrame(
        [
            {
                "dataset": dataset,
                "window": window,
                "cost_per_unit": cost,
                "robust": robust,
                "sample": sample,
                **_comparison_row(c),
            }
            for (dataset, window, cost, robust, sample), c in comparisons.items()
        ]
    )
    return _corrected(frame, ["dataset", "window", "cost_per_unit"], significance)


def best_deflated_sharpe(
    series: Mapping[str, pd.Series], *, configurations: int
) -> tuple[str, ProbabilisticSharpe, int] | None:
    """DSR of the variant with the highest per-month Sharpe ratio.

    Trials are the variants in ``series`` times the configurations in the trial ledger; the
    variance of the trial Sharpe ratios is estimated from ``series``. ``None`` with fewer than two
    variants.
    """
    if type(configurations) is not int or configurations < 1:
        raise ValidationError("configurations must be an int >= 1")
    if len(series) < 2:
        return None
    sharpes = pd.Series({k: float(v.mean() / v.std(ddof=1)) for k, v in series.items()})
    best = str(sharpes.idxmax())
    n_trials = len(series) * configurations
    dsr = deflated_sharpe_ratio(
        series[best], n_trials=n_trials, trial_sharpes=sharpes, variance=None
    )
    return best, dsr, n_trials


def _comparison_row(c: Comparison) -> dict[str, float]:
    return {
        "difference_per_month": c.hac.difference,
        "z_hac": c.hac.z,
        "pvalue_hac": c.hac.pvalue,
        "z_jkm": c.jkm.z,
        "pvalue_jkm": c.jkm.pvalue,
        "sharpe_low": c.sharpe_interval.low,
        "sharpe_high": c.sharpe_interval.high,
        "ceq_difference_annual": PERIODS_PER_YEAR * c.ceq_interval.estimate,
        "ceq_low_annual": PERIODS_PER_YEAR * c.ceq_interval.low,
        "ceq_high_annual": PERIODS_PER_YEAR * c.ceq_interval.high,
    }


def _corrected(frame: pd.DataFrame, keys: list[str], significance: float) -> pd.DataFrame:
    frame["holm"] = np.nan
    frame["bh"] = np.nan
    for _, group in frame.groupby(keys, sort=False):
        pvalues = pd.Series(group["pvalue_hac"].to_numpy(), index=group.index)
        for column, method in (("holm", Correction.HOLM), ("bh", Correction.BENJAMINI_HOCHBERG)):
            frame.loc[group.index, column] = adjust_pvalues(
                pvalues, method=method, alpha=significance
            ).adjusted
    return frame
