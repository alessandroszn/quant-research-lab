"""Experiment kind ``backtest``: asset returns CSV + a named strategy -> gross and net results.

Input ``returns``: a CSV of simple returns, one column per asset, read with the explicit
``[parameters.returns_format]`` (date column and format, delimiter, decimal separator).

Strategies (``[parameters.strategy]``, ``name`` plus its own keys):

- ``buy_and_hold``: keep the initial weights;
- ``trend``: hold ``asset`` when its trailing ``lookback``-period return is positive, else
  ``cash``;
- ``momentum``: hold the asset of ``assets`` with the best trailing ``lookback`` return;
- ``walk_forward``: every ``step`` periods after ``min_train``, re-estimate a Ledoit-Wolf
  covariance on all returns so far and apply ``method`` (``equal_weights``,
  ``minimum_variance``, ``risk_parity``, ``maximum_diversification``, ``hrp``), long-only with
  ``max_weight``.

Results of ``walk_forward`` are tagged ``out_of_sample`` (each decision uses only past data).
Rule-based strategies are tagged ``in_sample``: their rules and parameters may have been chosen
after seeing the same history.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.backtest.engine import Policy, Strategy, TradeOnSignal, run_backtest
from qrlab.backtest.summary import summarize_backtest
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._frames import read_returns
from qrlab.experiments.kinds._params import choice, number, table, text, whole
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.optimization.constraints import Constraints
from qrlab.optimization.mean_variance import OptimizationResult, equal_weights, minimum_variance
from qrlab.optimization.rebalancing import CalendarPolicy, CostModel, ThresholdPolicy
from qrlab.optimization.risk_based import (
    hierarchical_risk_parity,
    maximum_diversification,
    risk_budgeting,
)
from qrlab.risk.covariance import CovarianceEstimate, ledoit_wolf_covariance
from qrlab.simulation.plan import TaxModel

__all__ = ["KIND", "NOTICE", "read_returns"]

NOTICE = (
    "One historical path, with the stated costs, lag and taxes. Past results are not a "
    "forecast. Research analytics, not investment advice."
)

_PARAMETERS = (
    "returns_format",
    "strategy",
    "execution_lag",
    "policy",
    "costs",
    "capital_gains_tax",
    "initial_weights",
    "initial_value",
    "currency",
    "periods_per_year",
)
_METHODS = {"equal_weights", "minimum_variance", "risk_parity", "maximum_diversification", "hrp"}


@dataclass(frozen=True)
class _Parameters:
    returns_format: Mapping[str, str]
    strategy: Mapping[str, object]
    lag: int
    policy: Policy
    costs: CostModel
    tax: TaxModel | None
    initial_weights: pd.Series
    initial_value: Money
    periods_per_year: int


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    fmt = table(
        parameters,
        "returns_format",
        required={"date_column", "date_format", "delimiter", "decimal_separator"},
        optional=set(),
    )
    strategy = parameters["strategy"]
    if not isinstance(strategy, dict):
        raise ValidationError("strategy must be a table")
    name = choice(strategy, "name", {"buy_and_hold", "trend", "momentum", "walk_forward"})
    keys = {
        "buy_and_hold": set(),
        "trend": {"asset", "cash", "lookback"},
        "momentum": {"assets", "lookback"},
        "walk_forward": {"method", "min_train", "step", "max_weight"},
    }[name]
    require_keys(strategy, required={"name", *keys}, optional=set(), where="strategy")
    if name == "walk_forward":
        choice(strategy, "method", _METHODS)
        whole(strategy, "min_train", minimum=2)
        whole(strategy, "step", minimum=1)
        if not 0.0 < number(strategy, "max_weight") <= 1.0:
            raise ValidationError("max_weight must be in (0, 1]")
    elif name in ("trend", "momentum"):
        whole(strategy, "lookback", minimum=1)
    policy_table = parameters["policy"]
    if not isinstance(policy_table, dict):
        raise ValidationError("policy must be a table")
    kind = choice(policy_table, "type", {"trade_on_signal", "calendar", "threshold"})
    policy: Policy
    if kind == "trade_on_signal":
        require_keys(policy_table, required={"type"}, optional=set(), where="policy")
        policy = TradeOnSignal()
    elif kind == "calendar":
        require_keys(policy_table, required={"type", "every"}, optional=set(), where="policy")
        policy = CalendarPolicy(whole(policy_table, "every", minimum=1))
    else:
        require_keys(policy_table, required={"type", "band", "to"}, optional=set(), where="policy")
        policy = ThresholdPolicy(
            number(policy_table, "band"), choice(policy_table, "to", {"target", "band"})
        )
    costs = table(parameters, "costs", required={"proportional", "fixed"}, optional=set())
    weights = parameters["initial_weights"]
    if not isinstance(weights, dict) or not weights:
        raise ValidationError("initial_weights must be a non-empty table")
    rate = number(parameters, "capital_gains_tax")
    return _Parameters(
        returns_format={k: text(fmt, k) if k != "delimiter" else str(fmt[k]) for k in fmt},
        strategy=strategy,
        lag=whole(parameters, "execution_lag", minimum=1),
        policy=policy,
        costs=CostModel(number(costs, "proportional"), number(costs, "fixed")),
        tax=None if rate == 0.0 else TaxModel(rate, 0.0),
        initial_weights=pd.Series({str(k): number(weights, k) for k in weights}),
        initial_value=Money.of(
            str(number(parameters, "initial_value")), text(parameters, "currency")
        ),
        periods_per_year=whole(parameters, "periods_per_year", minimum=1),
    )


def _strategy(spec: Mapping[str, object], assets: list[str]) -> Strategy:
    name = spec["name"]
    if name == "buy_and_hold":
        return lambda history: None
    if name == "trend":
        asset, cash, lookback = str(spec["asset"]), str(spec["cash"]), int(spec["lookback"])  # type: ignore[call-overload]
        _known({asset, cash}, assets)

        def trend(history: pd.DataFrame) -> pd.Series | None:
            if len(history) < lookback:
                return None
            trailing = float(np.prod(1.0 + history[asset].to_numpy()[-lookback:])) - 1.0
            return _one_hot(asset if trailing > 0 else cash, assets)

        return trend
    if name == "momentum":
        pool = [str(a) for a in spec["assets"]]  # type: ignore[attr-defined]
        lookback = int(spec["lookback"])  # type: ignore[call-overload]
        _known(set(pool), assets)

        def momentum(history: pd.DataFrame) -> pd.Series | None:
            if len(history) < lookback:
                return None
            trailing = np.prod(1.0 + history[pool].to_numpy()[-lookback:], axis=0) - 1.0
            return _one_hot(pool[int(np.argmax(trailing))], assets)

        return momentum
    method = str(spec["method"])
    min_train, step = int(spec["min_train"]), int(spec["step"])  # type: ignore[call-overload]
    cap = float(spec["max_weight"])  # type: ignore[arg-type]
    constraints = Constraints(
        long_only=True,
        bounds=dict.fromkeys(assets, (0.0, cap)),
        groups={},
        turnover=None,
        current=None,
    )
    solve = _optimiser(method, constraints, assets)

    def walk_forward(history: pd.DataFrame) -> pd.Series | None:
        t = len(history)
        if t < min_train or (t - min_train) % step:
            return None
        cov = ledoit_wolf_covariance(history, kind=ReturnKind.SIMPLE, missing=NanPolicy.RAISE)
        return solve(cov).weights.reindex(assets)

    return walk_forward


def _optimiser(
    method: str, constraints: Constraints, assets: list[str]
) -> Callable[[CovarianceEstimate], OptimizationResult]:
    budgets = pd.Series(1.0 / len(assets), index=assets)
    return {
        "equal_weights": lambda c: equal_weights(c, constraints),
        "minimum_variance": lambda c: minimum_variance(c, constraints),
        "risk_parity": lambda c: risk_budgeting(c, budgets),
        "maximum_diversification": maximum_diversification,
        "hrp": hierarchical_risk_parity,
    }[method]


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    returns = read_returns(context.inputs["returns"].read_bytes(), p.returns_format)
    assets = [str(c) for c in returns.columns]
    result = run_backtest(
        returns,
        _strategy(p.strategy, assets),
        decide_every=1,
        execution_lag=p.lag,
        policy=p.policy,
        costs=p.costs,
        taxes=p.tax,
        initial_weights=p.initial_weights,
        initial_value=p.initial_value,
        long_only=True,
    )
    summary = summarize_backtest(result, periods_per_year=p.periods_per_year)
    tag = "out_of_sample" if p.strategy["name"] == "walk_forward" else "in_sample"
    values = pd.DataFrame({"gross": result.gross_values, "net": result.net_values})
    trades = pd.DataFrame(
        [
            (e.executed, e.decided, e.turnover, e.traded, e.cost, e.tax, e.trades)
            for e in result.executions
        ],
        columns=["executed", "decided", "turnover", "traded", "cost", "tax", "trades"],
    )
    scalars: dict[str, Tagged] = {}
    for ledger_name, ledger in (("gross", summary.gross), ("net", summary.net)):
        scalars[f"{ledger_name}_total_return"] = Tagged(ledger.total_return, tag)
        scalars[f"{ledger_name}_max_drawdown"] = Tagged(ledger.max_drawdown, tag)
        if ledger.annualised_return is not None:
            scalars[f"{ledger_name}_annualised_return"] = Tagged(ledger.annualised_return, tag)
        if ledger.annualised_volatility is not None:
            scalars[f"{ledger_name}_annualised_volatility"] = Tagged(
                ledger.annualised_volatility, tag
            )
    scalars["costs_paid"] = Tagged(summary.costs_paid, tag)
    scalars["taxes_paid"] = Tagged(summary.taxes_paid, tag)
    scalars["annual_turnover"] = Tagged(summary.annual_turnover, tag)
    return ExperimentOutput(
        tables={
            "values": Tagged(values, tag),
            "weights": Tagged(result.weights, tag),
            "trades": Tagged(trades, tag),
        },
        scalars=scalars,
        notice=NOTICE,
    )


def _one_hot(asset: str, assets: list[str]) -> pd.Series:
    return pd.Series({a: float(a == asset) for a in assets})


def _known(names: set[str], assets: list[str]) -> None:
    unknown = sorted(names - set(assets))
    if unknown:
        raise ValidationError(f"strategy names assets not in the returns file: {unknown}")


KIND = ExperimentKind(
    name="backtest",
    description="Backtest a named strategy with lag, costs and taxes (gross and net)",
    inputs=("returns",),
    needs_seed=False,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
