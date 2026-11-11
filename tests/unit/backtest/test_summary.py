"""Backtest summaries (gross and net side by side)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.backtest import BacktestResult, TradeOnSignal, run_backtest
from qrlab.backtest.summary import summarize_backtest
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.optimization import CalendarPolicy, CostModel

INDEX = pd.date_range("2020-01-31", periods=4, freq="ME")
TOY = pd.DataFrame(
    [[0.10, 0.0, -0.05], [-0.05, 0.05, 0.0], [0.0, 0.0, 0.10], [0.05, -0.05, 0.0]],
    index=INDEX,
    columns=["A", "B", "C"],
)
THIRD = pd.Series(1 / 3, index=["A", "B", "C"])


def _result(
    returns: pd.DataFrame, policy: TradeOnSignal | CalendarPolicy, costs: CostModel
) -> BacktestResult:
    return run_backtest(
        returns,
        lambda h: None,
        decide_every=1,
        execution_lag=1,
        policy=policy,
        costs=costs,
        taxes=None,
        initial_weights=pd.Series(1 / returns.shape[1], index=returns.columns),
        initial_value=Money.of("300", "EUR"),
        long_only=True,
    )


def test_summary_of_the_toy() -> None:
    result = _result(TOY.iloc[:3], CalendarPolicy(1), CostModel(0.001, 0.0))
    summary = summarize_backtest(result, periods_per_year=12)
    assert summary.gross.total_return == pytest.approx(315.16667 / 300 - 1, abs=1e-6)
    assert summary.net.total_return == pytest.approx(315.12539 / 300 - 1, abs=1e-6)
    assert summary.net.annualised_return is None  # three months: never annualised
    assert summary.costs_paid == pytest.approx(0.0403871, abs=1e-6)
    # C is already at 1/3 after period 2 (it returned 0 % like the portfolio): no trade in C
    assert (summary.periods, summary.executions, summary.trades) == (3, 3, 8)
    assert summary.annual_turnover > 0
    assert summary.net.max_drawdown < 0  # 304.983 -> 304.973
    assert summary.gross.final_value == pytest.approx(315.16667, abs=1e-4)


def test_annualised_figures_over_two_years(rng: np.random.Generator) -> None:
    index = pd.date_range("2018-01-31", periods=24, freq="ME")
    data = pd.DataFrame(rng.normal(0.01, 0.03, size=(24, 2)), index=index, columns=["X", "Y"])
    result = _result(data, TradeOnSignal(), CostModel(0.0, 0.0))
    summary = summarize_backtest(result, periods_per_year=12)
    total = summary.net.total_return
    assert summary.net.annualised_return == pytest.approx((1 + total) ** 0.5 - 1)
    returns = result.net_returns
    assert summary.net.annualised_volatility == pytest.approx(
        float(returns.std(ddof=1)) * math.sqrt(12)
    )
    assert summary.annual_turnover == 0.0


def test_single_period_has_no_volatility_and_bad_frequency_raises() -> None:
    result = _result(TOY.iloc[:1], TradeOnSignal(), CostModel(0.0, 0.0))
    summary = summarize_backtest(result, periods_per_year=12)
    assert summary.net.annualised_volatility is None
    with pytest.raises(ValidationError, match="periods_per_year"):
        summarize_backtest(result, periods_per_year=0)
