r"""The backtest engine: signals -> targets -> trades (policy, lag) -> drifting weights -> returns.

**Timing.** :math:`r_t` runs from the close of :math:`t-1` to the close of :math:`t`. A
decision at the close of :math:`t` sees only returns up to :math:`t`. With ``execution_lag``
:math:`L \ge 1` (required; 0 is refused) the trade executes at the close of :math:`t+L`, so new
weights earn :math:`r_{t+L+1}` onward. A decision whose execution falls after the last period
is recorded as not executed.

**Strategy API (default).** ``strategy(history)`` receives a fresh copy of the returns
truncated at :math:`t`, so it cannot index the future; it returns target weights or ``None``
(keep the previous target). A closure that captured the full frame before the run can still
leak: that cannot be enforced, only documented. Precomputed targets indexed by decision date
use :func:`run_backtest_targets`, with the same lag, and the result records that they were
precomputed.

**Each period.** Holdings grow with their returns (weights drift). A target due for execution
becomes the current target. The rebalancing policy (4.2, or :class:`TradeOnSignal`) decides
whether and to what to trade, judged on the net portfolio and applied to both ledgers. Costs
(:class:`~qrlab.optimization.CostModel`) and capital-gains tax on realised gains (average cost
basis per asset; :class:`~qrlab.simulation.TaxModel`, wealth tax ignored) are paid pro rata from
the net ledger after the trade. The gross ledger has neither.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.core.series import NanPolicy, validate_frame
from qrlab.optimization.rebalancing import CalendarPolicy, CostModel, ThresholdPolicy
from qrlab.simulation.losses import LossBalance, fund_mask, realised_tax
from qrlab.simulation.plan import TaxModel

__all__ = [
    "BacktestResult",
    "Execution",
    "Strategy",
    "TradeOnSignal",
    "run_backtest",
    "run_backtest_targets",
]

Strategy = Callable[[pd.DataFrame], pd.Series | None]
"""Maps the returns up to the decision date to target weights, or ``None`` to keep them."""


@dataclass(frozen=True)
class TradeOnSignal:
    """Trade to each new target on its execution date, and never in between."""

    def describe(self) -> str:
        """Return a short description."""
        return "trade on each new signal"


Policy = TradeOnSignal | CalendarPolicy | ThresholdPolicy


@dataclass(frozen=True)
class Execution:
    """One executed trade, as seen in the net ledger."""

    executed: date
    decided: date | None
    turnover: float
    traded: float
    cost: float
    tax: float
    trades: int


@dataclass(frozen=True)
class BacktestResult:
    """Gross and net paths of one backtest, with its trades and settings."""

    gross_values: pd.Series
    net_values: pd.Series
    gross_returns: pd.Series
    net_returns: pd.Series
    weights: pd.DataFrame
    executions: tuple[Execution, ...]
    not_executed: tuple[date, ...]
    settings: dict[str, str | float]
    currency: str
    final_basis: pd.Series  # net-ledger cost basis per asset at the end (average cost)

    @property
    def costs_paid(self) -> float:
        """Total transaction costs (net ledger, currency units)."""
        return float(sum(e.cost for e in self.executions))

    @property
    def taxes_paid(self) -> float:
        """Total capital-gains tax (net ledger, currency units)."""
        return float(sum(e.tax for e in self.executions))


def run_backtest(
    returns: pd.DataFrame,
    strategy: Strategy,
    *,
    decide_every: int,
    execution_lag: int,
    policy: Policy,
    costs: CostModel,
    taxes: TaxModel | None,
    initial_weights: pd.Series,
    initial_value: Money,
    long_only: bool,
) -> BacktestResult:
    """Run ``strategy`` on ``returns``; it decides every ``decide_every`` periods."""
    frame = _returns(returns)
    _positive("decide_every", decide_every)
    targets: dict[int, pd.Series] = {}
    for t in range(1, len(frame) + 1):
        if t % decide_every:
            continue
        decision = strategy(frame.iloc[:t].copy())
        if decision is not None:
            targets[t] = _weights(
                decision, frame.columns, long_only, f"decision {frame.index[t - 1].date()}"
            )
    settings: dict[str, str | float] = {"targets": "strategy", "decide_every": float(decide_every)}
    return _run(
        frame,
        targets,
        execution_lag,
        policy,
        costs,
        taxes,
        initial_weights,
        initial_value,
        long_only,
        settings,
    )


def run_backtest_targets(
    returns: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    execution_lag: int,
    policy: Policy,
    costs: CostModel,
    taxes: TaxModel | None,
    initial_weights: pd.Series,
    initial_value: Money,
    long_only: bool,
) -> BacktestResult:
    """Run precomputed target weights, indexed by the date each was decided."""
    frame = _returns(returns)
    if not isinstance(targets.index, pd.DatetimeIndex) or not targets.index.isin(frame.index).all():
        raise ValidationError("target dates must be dates of the returns index")
    found = frame.index.get_indexer(targets.index)
    positions = {d: int(i) + 1 for d, i in zip(targets.index, found, strict=True)}
    decided = {
        positions[d]: _weights(targets.loc[d], frame.columns, long_only, f"target {d.date()}")
        for d in targets.index
    }
    settings: dict[str, str | float] = {"targets": "precomputed"}
    return _run(
        frame,
        decided,
        execution_lag,
        policy,
        costs,
        taxes,
        initial_weights,
        initial_value,
        long_only,
        settings,
    )


def _run(
    frame: pd.DataFrame,
    decisions: dict[int, pd.Series],
    lag: int,
    policy: Policy,
    costs: CostModel,
    taxes: TaxModel | None,
    initial_weights: pd.Series,
    initial_value: Money,
    long_only: bool,
    settings: dict[str, str | float],
) -> BacktestResult:
    if type(lag) is not int or lag < 1:
        raise ValidationError(
            "execution_lag must be an int >= 1 (trading on the signal's close leaks)"
        )
    if not isinstance(policy, TradeOnSignal | CalendarPolicy | ThresholdPolicy):
        raise ValidationError("policy must be TradeOnSignal, CalendarPolicy or ThresholdPolicy")
    value = float(initial_value.amount)
    if not (math.isfinite(value) and value > 0):
        raise ValidationError("initial_value must be positive")
    assets = frame.columns
    w0 = _weights(initial_weights, assets, long_only, "initial weights").to_numpy()
    rate = 0.0 if taxes is None else taxes.capital_gains_rate
    losses = None
    if taxes is not None and taxes.losses is not None:
        first_year = int(frame.index[0].year)
        losses = (
            fund_mask(taxes.losses, [str(a) for a in assets]),
            LossBalance(
                paths=1,
                years=int(frame.index[-1].year) - first_year + 1,
                carry_years=taxes.losses.carry_years,
            ),
            first_year,
        )
    gross = w0 * value
    net = w0 * value
    basis = net.copy()
    target = pd.Series(w0, index=assets)
    pending: dict[int, tuple[pd.Series, int]] = {}
    not_executed = []
    for when, weights in decisions.items():
        if when + lag > len(frame):
            not_executed.append(frame.index[when - 1].date())
        else:
            pending[when + lag] = (weights, when)
    values_gross, values_net, realised = [], [], []
    executions: list[Execution] = []
    r = frame.to_numpy()
    for t in range(1, len(frame) + 1):
        gross *= 1.0 + r[t - 1]
        net *= 1.0 + r[t - 1]
        new_signal = t in pending
        decided_at: int | None = None
        if new_signal:
            target, decided_at = pending[t]
        current = pd.Series(net / net.sum(), index=assets)
        if isinstance(policy, TradeOnSignal):
            due, destination = new_signal, target
        else:
            due = policy.due(t, current, target)
            destination = policy.destination(current, target) if due else target
        if due:
            d = destination.reindex(assets).to_numpy(dtype=np.float64)
            gross = d * gross.sum()
            year = int(frame.index[t - 1].year)
            (turnover, traded, cost, tax, count), net, basis = _trade_net(
                net, basis, d, costs, rate, losses, year
            )
            executions.append(
                Execution(
                    executed=frame.index[t - 1].date(),
                    decided=None if decided_at is None else frame.index[decided_at - 1].date(),
                    turnover=turnover,
                    traded=traded,
                    cost=cost,
                    tax=tax,
                    trades=count,
                )
            )
        values_gross.append(float(gross.sum()))
        values_net.append(float(net.sum()))
        realised.append(net / net.sum())
    index = frame.index
    start = index[0] - (index[1] - index[0]) if len(index) > 1 else index[0] - pd.Timedelta(days=1)
    gross_values = pd.Series([value, *values_gross], index=[start, *index], name="gross")
    net_values = pd.Series([value, *values_net], index=[start, *index], name="net")
    settings.update(
        {
            "execution_lag": float(lag),
            "policy": _describe(policy),
            "proportional_cost": costs.proportional,
            "fixed_cost": costs.fixed,
            "capital_gains_tax": rate,
        }
    )
    return BacktestResult(
        gross_values=gross_values,
        net_values=net_values,
        gross_returns=gross_values.pct_change().iloc[1:].rename("gross"),
        net_returns=net_values.pct_change().iloc[1:].rename("net"),
        weights=pd.DataFrame(realised, index=index, columns=assets),
        executions=tuple(executions),
        not_executed=tuple(not_executed),
        settings=settings,
        currency=initial_value.currency.code,
        final_basis=pd.Series(basis, index=assets, name="basis"),
    )


def _trade_net(
    holdings: np.ndarray,
    basis: np.ndarray,
    destination: np.ndarray,
    costs: CostModel,
    rate: float,
    losses: tuple[np.ndarray, LossBalance, int] | None = None,
    year: int = 0,
) -> tuple[tuple[float, float, float, float, int], np.ndarray, np.ndarray]:
    value = float(holdings.sum())
    new = destination * value
    delta = new - holdings
    delta[np.abs(delta) < 1e-12 * max(value, 1.0)] = 0.0
    traded = float(np.abs(delta).sum())
    count = int((delta != 0).sum())
    cost = costs.proportional * traded + costs.fixed * count
    sold = np.where(delta < 0, -delta / np.where(holdings > 0, holdings, 1.0), 0.0)
    gains = sold * (holdings - basis)
    if losses is None:
        tax = rate * float(np.clip(gains, 0.0, None).sum())
    else:
        funds, balance, first_year = losses
        tax = float(realised_tax(gains[None, :], rate, funds, balance, year - first_year)[0])
    basis = basis * (1.0 - sold) + np.clip(delta, 0.0, None)
    keep = 1.0 - (cost + tax) / value
    turnover = traded / value
    return (
        (turnover, traded, cost, tax, count),
        new * keep,
        basis * keep,
    )


def _returns(returns: pd.DataFrame) -> pd.DataFrame:
    frame = validate_frame(returns, nan_policy=NanPolicy.RAISE, name="returns")
    if frame.shape[1] == 0 or len(frame) < 1:
        raise ValidationError("returns need at least one period and one asset")
    if (frame.to_numpy() <= -1.0).any():
        raise ValidationError("simple returns must be above -1")
    return frame


def _weights(weights: object, assets: pd.Index, long_only: bool, where: str) -> pd.Series:
    if not isinstance(weights, pd.Series):
        raise ValidationError(f"{where}: weights must be a pandas Series")
    if set(weights.index) != set(assets):
        raise ValidationError(f"{where}: weights must cover exactly the assets {list(assets)}")
    values = weights.reindex(assets).astype("float64")
    if not np.all(np.isfinite(values.to_numpy())):
        raise ValidationError(f"{where}: weights must be finite")
    if abs(float(values.sum()) - 1.0) > 1e-9:
        raise ValidationError(f"{where}: weights must sum to 1, got {values.sum()}")
    if long_only and (values < 0).any():
        raise ValidationError(f"{where}: negative weights with long_only")
    return values


def _positive(name: str, value: object) -> None:
    if type(value) is not int or value < 1:
        raise ValidationError(f"{name} must be a positive int")


def _describe(policy: Policy) -> str:
    if isinstance(policy, TradeOnSignal):
        return policy.describe()
    if isinstance(policy, CalendarPolicy):
        return f"calendar every {policy.every} periods"
    return f"threshold band {policy.band:.2%} to {policy.to}"
