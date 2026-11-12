r"""Study 4: rebalancing rules for a EUR ETF investor, after costs, Italian tax and currency.

Design note: ``docs/design/5.3-study-4-rebalancing.md``.

- **Equity in EUR.** A USD return converted at month-end ECB rates :math:`S` (USD per EUR):
  :math:`r^{EUR}=(1+r^{USD})\,S_{t-1}/S_t-1`.
- **Rolled zero-coupon bond.** With continuously compounded spot rates :math:`z`, a zero with
  maturity :math:`T` bought at the end of month :math:`t-1` and sold at the end of month
  :math:`t` earns :math:`\exp\big(z_{t-1}(T)\,T-z_t(T-\Delta)(T-\Delta)\big)-1`, with
  :math:`\Delta` the years between the two observations (Actual/365.25) and :math:`z_t(T-\Delta)`
  interpolated linearly between the :math:`T-1` and :math:`T` year rates.
- **Policies** run through the backtest engine on monthly returns; the rules see the drifted
  weights at each month end and trade at that close. Tax is the engine's: a rate on realised
  gains, average cost per asset, no offset of losses. The **after-tax wealth** also pays that
  rate on each asset's unrealised gain at the end (liquidation).
- **Simulation.** Stationary-bootstrap paths of the joint monthly returns; every policy runs on
  the same paths and is compared with a reference policy path by path.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from qrlab.backtest.engine import BacktestResult, Policy, TradeOnSignal, run_backtest
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.core.series import NanPolicy, validate_frame, validate_series
from qrlab.metrics.drawdown import max_drawdown
from qrlab.optimization.rebalancing import CalendarPolicy, CostModel, ThresholdPolicy
from qrlab.simulation.plan import TaxModel
from qrlab.stats.bootstrap import MIN_RESAMPLES, stationary_bootstrap_indices

__all__ = [
    "DAYS_PER_YEAR",
    "PERIODS_PER_YEAR",
    "POLICIES",
    "PathMetrics",
    "compare_to_reference",
    "equity_returns_eur",
    "historical_runs",
    "hypotheses",
    "liquidation_value",
    "month_end_observations",
    "path_metrics",
    "run_policy",
    "simulate",
    "summarize_runs",
    "zero_coupon_returns",
]

PERIODS_PER_YEAR = 12
DAYS_PER_YEAR = 365.25

POLICIES: Mapping[str, Policy] = {
    "buy_and_hold": TradeOnSignal(),  # no signals: never trades
    "calendar_monthly": CalendarPolicy(1),
    "calendar_quarterly": CalendarPolicy(3),
    "calendar_annual": CalendarPolicy(12),
    "band_5_target": ThresholdPolicy(0.05, "target"),
    "band_10_target": ThresholdPolicy(0.10, "target"),
    "band_5_edge": ThresholdPolicy(0.05, "band"),
}
"""The policies fixed by the design note."""


@dataclass(frozen=True)
class PathMetrics:
    """Outcome of one policy on one path (money in EUR, rates as decimals)."""

    after_tax_wealth: float
    after_tax_return: float  # annualised
    volatility: float  # annualised, monthly net returns
    max_drawdown: float
    mean_abs_deviation: float  # equity weight vs target, end of each month
    max_abs_deviation: float
    final_equity_weight: float
    annual_turnover: float
    trades: int
    costs: float
    taxes: float
    deferred_tax: float


# ------------------------------------------------------------------------------- data helpers
def month_end_observations(daily: pd.DataFrame) -> pd.DataFrame:
    """Last observation of each calendar month, labelled by month end, with its date.

    Rows with any missing value are skipped first; a month inside the range without any
    complete observation raises (nothing is forward-filled).
    """
    frame = validate_frame(daily, nan_policy=NanPolicy.DROP, name="daily")
    if frame.empty:
        raise ValidationError("no complete daily observations")
    index = pd.DatetimeIndex(frame.index)
    labels = index.normalize() + pd.offsets.MonthEnd(0)
    last = frame.groupby(labels).tail(1)
    out = last.copy()
    out.index = pd.DatetimeIndex(pd.DatetimeIndex(last.index).normalize() + pd.offsets.MonthEnd(0))
    out["observed"] = pd.DatetimeIndex(last.index)
    expected = pd.date_range(out.index[0], out.index[-1], freq="ME")
    missing = expected.difference(out.index)
    if len(missing):
        raise ValidationError(f"no observation in month {missing[0].date()}")
    return out


def equity_returns_eur(usd_returns: pd.Series, usd_per_eur: pd.Series) -> pd.Series:
    """Convert monthly USD returns to EUR with month-end rates (USD per EUR).

    Months need the rate of the month and of the month before.
    """
    r = validate_series(usd_returns, nan_policy=NanPolicy.RAISE, name="usd_returns")
    s = validate_series(usd_per_eur, nan_policy=NanPolicy.RAISE, name="usd_per_eur")
    if not (s > 0).all():
        raise ValidationError("exchange rates must be positive")
    previous = s.shift(1)
    common = r.index.intersection(previous.dropna().index)
    if common.empty:
        raise ValidationError("no month has a return and both exchange rates")
    out = (1.0 + r.loc[common]) * previous.loc[common] / s.loc[common] - 1.0
    return out.rename("equity_eur")


def zero_coupon_returns(
    curve: pd.DataFrame, *, short: str, long: str, maturity: float
) -> pd.Series:
    """Monthly returns of a constant-maturity zero rolled each month.

    ``curve`` comes from :func:`month_end_observations`: continuously compounded spot rates (in
    decimals) at maturities ``maturity - 1`` (column ``short``) and ``maturity`` (column
    ``long``), plus the ``observed`` dates.
    """
    if not (math.isfinite(maturity) and maturity > 1.0):
        raise ValidationError("maturity must be a number of years greater than 1")
    for column in (short, long, "observed"):
        if column not in curve.columns:
            raise ValidationError(f"curve lacks column {column!r}")
    if len(curve) < 2:
        raise ValidationError("need at least two month ends")
    z_long = curve[long].to_numpy(dtype=np.float64)
    z_short = curve[short].to_numpy(dtype=np.float64)
    days = np.diff(pd.DatetimeIndex(curve["observed"]).to_numpy()).astype("timedelta64[D]")
    delta = days.astype(np.float64) / DAYS_PER_YEAR
    if not ((delta > 0) & (delta < 1)).all():
        raise ValidationError("observations must be less than a year apart and increasing")
    remaining = maturity - delta
    z_end = z_long[1:] - delta * (z_long[1:] - z_short[1:])
    log_return = z_long[:-1] * maturity - z_end * remaining
    return pd.Series(np.expm1(log_return), index=curve.index[1:], name="bond")


# --------------------------------------------------------------------------------- policies
def run_policy(
    returns: pd.DataFrame,
    *,
    weights: pd.Series,
    policy: str,
    costs: CostModel,
    tax_rate: float,
    initial_value: float,
) -> BacktestResult:
    """Run one of :data:`POLICIES` on monthly returns, starting at the target weights."""
    if policy not in POLICIES:
        raise ValidationError(f"unknown policy {policy!r}; known: {list(POLICIES)}")
    return run_backtest(
        returns,
        lambda history: None,
        decide_every=1,
        execution_lag=1,
        policy=POLICIES[policy],
        costs=costs,
        taxes=TaxModel(tax_rate, 0.0) if tax_rate > 0 else None,
        initial_weights=weights,
        initial_value=Money.of(repr(float(initial_value)), "EUR"),
        long_only=True,
    )


def liquidation_value(result: BacktestResult, *, tax_rate: float) -> tuple[float, float]:
    """Return (after-tax value if everything were sold at the end, the tax that sale pays)."""
    if not 0.0 <= tax_rate < 1.0:
        raise ValidationError("tax_rate must be in [0, 1)")
    value = float(result.net_values.iloc[-1])
    holdings = result.weights.iloc[-1] * value
    gains = holdings - result.final_basis.reindex(holdings.index)
    tax = tax_rate * float(gains.clip(lower=0.0).sum())
    return value - tax, tax


def path_metrics(
    result: BacktestResult,
    *,
    target: pd.Series,
    equity: str,
    tax_rate: float,
    initial_value: float,
) -> PathMetrics:
    """Summarise one policy run (see :class:`PathMetrics`)."""
    after_tax, deferred = liquidation_value(result, tax_rate=tax_rate)
    months = len(result.net_returns)
    years = months / PERIODS_PER_YEAR
    deviation = (result.weights[equity] - float(target[equity])).abs()
    net = result.net_returns
    return PathMetrics(
        after_tax_wealth=after_tax,
        after_tax_return=(after_tax / initial_value) ** (1.0 / years) - 1.0,
        volatility=float(net.std(ddof=1)) * math.sqrt(PERIODS_PER_YEAR),
        max_drawdown=max_drawdown(net),
        mean_abs_deviation=float(deviation.mean()),
        max_abs_deviation=float(deviation.max()),
        final_equity_weight=float(result.weights[equity].iloc[-1]),
        annual_turnover=sum(e.turnover for e in result.executions) / years,
        trades=sum(e.trades for e in result.executions),
        costs=result.costs_paid,
        taxes=result.taxes_paid,
        deferred_tax=deferred,
    )


# ------------------------------------------------------------------------------- simulation
def simulate(
    returns: pd.DataFrame,
    *,
    weights: pd.Series,
    equity: str,
    policies: Sequence[str],
    cost_scenarios: Mapping[str, CostModel],
    tax_rate: float,
    initial_value: float,
    horizon: int,
    n_paths: int,
    mean_block_length: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Run every policy and cost scenario on the same bootstrap paths; one row per run.

    Each path is the first ``horizon`` months of a stationary-bootstrap resample of the whole
    history (``horizon`` must not exceed the history).
    """
    history = validate_frame(returns, nan_policy=NanPolicy.RAISE, name="returns")
    if type(horizon) is not int or not 12 <= horizon <= len(history):
        raise ValidationError(f"horizon must be an int between 12 and {len(history)} months")
    if type(n_paths) is not int or n_paths < 1:
        raise ValidationError("n_paths must be a positive int")
    # The index generator needs at least MIN_RESAMPLES draws; extra paths are not used.
    indices = stationary_bootstrap_indices(
        len(history),
        mean_block_length=mean_block_length,
        n_resamples=max(n_paths, MIN_RESAMPLES),
        rng=rng,
    )[:n_paths, :horizon]
    labels = pd.date_range("2000-01-31", periods=horizon, freq="ME")
    values = history.to_numpy()
    rows = []
    for path, idx in enumerate(indices):
        frame = pd.DataFrame(values[idx], index=labels, columns=history.columns)
        rows += _run_all(
            frame,
            path=path,
            weights=weights,
            equity=equity,
            policies=policies,
            cost_scenarios=cost_scenarios,
            tax_rate=tax_rate,
            initial_value=initial_value,
        )
    return pd.DataFrame(rows)


def historical_runs(
    returns: pd.DataFrame,
    *,
    weights: pd.Series,
    equity: str,
    policies: Sequence[str],
    cost_scenarios: Mapping[str, CostModel],
    tax_rate: float,
    initial_value: float,
) -> pd.DataFrame:
    """Run every policy and cost scenario on the actual history (one path, ``path`` = 0)."""
    history = validate_frame(returns, nan_policy=NanPolicy.RAISE, name="returns")
    return pd.DataFrame(
        _run_all(
            history,
            path=0,
            weights=weights,
            equity=equity,
            policies=policies,
            cost_scenarios=cost_scenarios,
            tax_rate=tax_rate,
            initial_value=initial_value,
        )
    )


def summarize_runs(runs: pd.DataFrame) -> pd.DataFrame:
    """Median outcome per scenario and policy, with the 5 % and 95 % after-tax wealth."""
    if runs.empty:
        raise ValidationError("no runs to summarise")
    grouped = runs.groupby(["scenario", "policy"], sort=False)
    medians = grouped[
        [
            "after_tax_wealth",
            "after_tax_return",
            "volatility",
            "max_drawdown",
            "mean_abs_deviation",
            "final_equity_weight",
            "annual_turnover",
            "trades",
            "costs",
            "taxes",
            "deferred_tax",
        ]
    ].median()
    medians["after_tax_wealth_p05"] = grouped["after_tax_wealth"].quantile(0.05)
    medians["after_tax_wealth_p95"] = grouped["after_tax_wealth"].quantile(0.95)
    medians["paths"] = grouped.size()
    return medians.reset_index()


def _run_all(
    frame: pd.DataFrame,
    *,
    path: int,
    weights: pd.Series,
    equity: str,
    policies: Sequence[str],
    cost_scenarios: Mapping[str, CostModel],
    tax_rate: float,
    initial_value: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario, costs in cost_scenarios.items():
        for policy in policies:
            result = run_policy(
                frame,
                weights=weights,
                policy=policy,
                costs=costs,
                tax_rate=tax_rate,
                initial_value=initial_value,
            )
            metrics = path_metrics(
                result,
                target=weights,
                equity=equity,
                tax_rate=tax_rate,
                initial_value=initial_value,
            )
            rows.append({"path": path, "scenario": scenario, "policy": policy, **asdict(metrics)})
    return rows


def compare_to_reference(runs: pd.DataFrame, *, reference: str) -> pd.DataFrame:
    """Paired differences (policy minus reference) per scenario: median, 5 % and 95 %."""
    if reference not in set(runs["policy"]):
        raise ValidationError(f"reference policy {reference!r} was not run")
    measures = ["after_tax_wealth", "mean_abs_deviation", "volatility", "max_drawdown"]
    rows = []
    for scenario, group in runs.groupby("scenario", sort=False):
        base = group[group["policy"] == reference].set_index("path")
        for policy, part in group.groupby("policy", sort=False):
            if policy == reference:
                continue
            diff = part.set_index("path")[measures] - base[measures]
            paid = (part.set_index("path")["costs"] + part.set_index("path")["taxes"]) - (
                base["costs"] + base["taxes"]
            )
            row: dict[str, object] = {"scenario": scenario, "policy": policy}
            for column in [*measures, "costs_and_taxes"]:
                series = paid if column == "costs_and_taxes" else diff[column]
                row[f"{column}_median"] = float(series.median())
                row[f"{column}_p05"] = float(series.quantile(0.05))
                row[f"{column}_p95"] = float(series.quantile(0.95))
            row["share_wealth_higher"] = float((diff["after_tax_wealth"] > 0).mean())
            rows.append(row)
    return pd.DataFrame(rows)


def hypotheses(runs: pd.DataFrame, *, support_share: float) -> pd.DataFrame:
    """Shares of paths where each stated direction holds, per scenario, and the verdicts."""
    if not 0.5 < support_share <= 1.0:
        raise ValidationError("support_share must be in (0.5, 1]")
    needed = {"buy_and_hold", "calendar_monthly", "calendar_quarterly", "calendar_annual"}
    needed.add("band_5_target")
    missing = sorted(needed - set(runs["policy"]))
    if missing:
        raise ValidationError(f"hypotheses need the policies {missing}")
    rows = []
    for scenario, group in runs.groupby("scenario", sort=False):
        by = {p: g.set_index("path") for p, g in group.groupby("policy")}
        band, quarterly = by["band_5_target"], by["calendar_quarterly"]
        monthly, annual, hold = by["calendar_monthly"], by["calendar_annual"], by["buy_and_hold"]
        checks = {
            "H1": {
                "deviation not larger": band["mean_abs_deviation"]
                <= quarterly["mean_abs_deviation"] + 1e-12,
                "costs and taxes lower": (band["costs"] + band["taxes"])
                < (quarterly["costs"] + quarterly["taxes"]),
            },
            "H2": {
                "monthly ends with less after-tax wealth": monthly["after_tax_wealth"]
                < annual["after_tax_wealth"],
            },
            "H3": {
                "buy-and-hold ends with more after-tax wealth": hold["after_tax_wealth"]
                > annual["after_tax_wealth"],
                "higher final equity weight": hold["final_equity_weight"]
                > annual["final_equity_weight"],
                "higher volatility": hold["volatility"] > annual["volatility"],
                "deeper maximum drawdown": hold["max_drawdown"] < annual["max_drawdown"],
            },
        }
        for name, parts in checks.items():
            shares = {label: float(mask.mean()) for label, mask in parts.items()}
            for label, share in shares.items():
                rows.append(
                    {
                        "scenario": scenario,
                        "hypothesis": name,
                        "condition": label,
                        "share": share,
                        "supported": all(s >= support_share for s in shares.values()),
                    }
                )
    return pd.DataFrame(rows)
