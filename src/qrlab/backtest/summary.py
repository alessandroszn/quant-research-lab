"""Gross and net summary statistics of a backtest.

Statistics reuse :mod:`qrlab.metrics`. Annualised return is given only when the backtest covers
at least one year (``periods_per_year`` periods); volatility and turnover are annualised with
the explicit ``periods_per_year``. A summary describes one historical path; it is not evidence
that a strategy works.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qrlab.backtest.engine import BacktestResult
from qrlab.core.errors import ValidationError
from qrlab.metrics.drawdown import max_drawdown
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.performance import annualised_volatility

__all__ = ["BacktestSummary", "LedgerSummary", "summarize_backtest"]


@dataclass(frozen=True)
class LedgerSummary:
    """Statistics of one ledger (gross or net)."""

    total_return: float
    annualised_return: float | None
    annualised_volatility: float | None
    max_drawdown: float
    final_value: float


@dataclass(frozen=True)
class BacktestSummary:
    """Gross and net statistics side by side, with trading activity."""

    gross: LedgerSummary
    net: LedgerSummary
    periods: int
    periods_per_year: int
    trades: int
    executions: int
    annual_turnover: float
    costs_paid: float
    taxes_paid: float


def summarize_backtest(result: BacktestResult, *, periods_per_year: int) -> BacktestSummary:
    """Summarise ``result`` with an explicit number of periods per year."""
    if type(periods_per_year) is not int or periods_per_year < 1:
        raise ValidationError("periods_per_year must be a positive int")
    periods = len(result.net_returns)
    years = periods / periods_per_year
    turnover = sum(e.turnover for e in result.executions)
    return BacktestSummary(
        gross=_ledger(result.gross_values, result.gross_returns, periods_per_year, years),
        net=_ledger(result.net_values, result.net_returns, periods_per_year, years),
        periods=periods,
        periods_per_year=periods_per_year,
        trades=sum(e.trades for e in result.executions),
        executions=len(result.executions),
        annual_turnover=turnover / years,
        costs_paid=result.costs_paid,
        taxes_paid=result.taxes_paid,
    )


def _ledger(values: pd.Series, returns: pd.Series, ppy: int, years: float) -> LedgerSummary:
    total = float(values.iloc[-1] / values.iloc[0]) - 1.0
    annualised = (1.0 + total) ** (1.0 / years) - 1.0 if years >= 1.0 else None
    try:
        vol: float | None = annualised_volatility(returns, periods_per_year=float(ppy))
    except UndefinedMetricError:
        vol = None
    return LedgerSummary(total, annualised, vol, max_drawdown(returns), float(values.iloc[-1]))
