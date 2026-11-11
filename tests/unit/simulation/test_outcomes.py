"""Projection summaries and sensitivity, on hand-built paths and seeded simulations."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.simulation import (
    MAX_CELLS,
    Flow,
    LogMoments,
    Plan,
    SimulatedReturns,
    TaxModel,
    normal_returns,
    project,
    sensitivity,
    shifted_moments,
    summarize,
)

EUR = Currency("EUR")
START = date(2026, 6, 30)


def _plan(**changes: object) -> Plan:
    fields: dict[str, object] = {
        "initial_wealth": 100.0,
        "currency": EUR,
        "weights": pd.Series([1.0], index=["a0"]),
        "periods_per_year": 12,
        "flows": (),
        "flow_timing": "end",
        "rebalance_every": None,
        "annual_cost": 0.0,
        "inflation": 0.0,
        "taxes": TaxModel(0.0, 0.0),
    }
    fields.update(changes)
    return Plan(**fields)  # type: ignore[arg-type]


def _ten_paths() -> SimulatedReturns:
    """Ten paths of two periods: path k returns k x 10 % in period 0 and 0 in period 1."""
    values = np.zeros((10, 2, 1))
    values[:, 0, 0] = np.arange(10) * 0.1
    return SimulatedReturns(values, ("a0",), "fixed")


def test_summary_on_hand_built_paths() -> None:
    returns = _ten_paths()
    projection = project(_plan(), returns)
    summary = summarize(
        projection, returns, start=START, goal_real=150.0, percentiles=(10, 50, 90), early_periods=1
    )
    terminal = 100.0 * (1.0 + np.arange(10) * 0.1)  # 100, 110, ..., 190
    assert summary.p_goal == pytest.approx(0.5)  # 150, 160, 170, 180, 190
    assert summary.p_goal_se == pytest.approx(math.sqrt(0.25 / 10))
    assert summary.terminal_mean_real == pytest.approx(145.0)
    assert summary.terminal_mean_real_se == pytest.approx(terminal.std(ddof=1) / math.sqrt(10))
    assert summary.terminal_real == pytest.approx(tuple(np.percentile(terminal, (10, 50, 90))))
    assert summary.fan_real.shape == (3, 3)
    assert summary.fan_real[:, 0].tolist() == [100.0, 100.0, 100.0]
    assert summary.dates == (START, date(2026, 7, 30), date(2026, 8, 30))
    assert (summary.sequence_worst, summary.sequence_best) == (100.0, 190.0)
    assert (summary.p_depleted, summary.median_depletion_period) == (0.0, None)
    assert (summary.n_paths, summary.engine) == (10, "fixed")


def test_depletion_probability() -> None:
    returns = _ten_paths()
    plan = _plan(flows=(Flow("withdrawal", 130.0, 0, 0, False),))
    summary = summarize(
        project(plan, returns),
        returns,
        start=START,
        goal_real=0.0,
        percentiles=(50,),
        early_periods=2,
    )
    assert summary.p_depleted == pytest.approx(0.3)  # wealth 100, 110, 120 < 130
    assert summary.median_depletion_period == 0.0
    assert summary.p_depleted_se == pytest.approx(math.sqrt(0.21 / 10))


def test_after_tax_and_nominal_terminal_values() -> None:
    returns = _ten_paths()
    plan = _plan(taxes=TaxModel(0.26, 0.0), inflation=0.12)
    summary = summarize(
        project(plan, returns),
        returns,
        start=START,
        goal_real=0.0,
        percentiles=(0, 100),
        early_periods=1,
    )
    assert summary.terminal_nominal == pytest.approx((100.0, 190.0))
    assert summary.terminal_after_tax == pytest.approx((100.0, 190.0 - 0.26 * 90.0))
    assert summary.terminal_real[1] == pytest.approx(190.0 / 1.12 ** (2 / 12))


def test_quarterly_dates_and_validation() -> None:
    returns = _ten_paths()
    quarterly = _plan(periods_per_year=4)
    summary = summarize(
        project(quarterly, returns),
        returns,
        start=START,
        goal_real=0.0,
        percentiles=(50,),
        early_periods=1,
    )
    assert summary.dates[-1] == date(2026, 12, 30)
    projection = project(_plan(), returns)
    bad: list[dict[str, object]] = [
        {"percentiles": ()},
        {"percentiles": (50, 10)},
        {"percentiles": (101,)},
        {"goal_real": -1.0},
        {"goal_real": float("nan")},
        {"early_periods": 0},
        {"early_periods": 3},
    ]
    for changes in bad:
        kwargs: dict[str, object] = {
            "start": START,
            "goal_real": 0.0,
            "percentiles": (50,),
            "early_periods": 1,
        }
        kwargs.update(changes)
        with pytest.raises(ValidationError):
            summarize(projection, returns, **kwargs)  # type: ignore[arg-type]
    weekly = project(_plan(periods_per_year=52), returns)
    with pytest.raises(ValidationError, match="periods_per_year"):
        summarize(weekly, returns, start=START, goal_real=0.0, percentiles=(50,), early_periods=1)
    with pytest.raises(ValidationError, match="do not match"):
        summarize(
            projection,
            SimulatedReturns(np.zeros((10, 3, 1)), ("a0",), "x"),
            start=START,
            goal_real=0.0,
            percentiles=(50,),
            early_periods=1,
        )
    few = SimulatedReturns(np.zeros((5, 1, 1)), ("a0",), "x")
    with pytest.raises(ValidationError, match="10 paths"):
        summarize(
            project(_plan(), few),
            few,
            start=START,
            goal_real=0.0,
            percentiles=(50,),
            early_periods=1,
        )


def test_sequence_risk_shows_with_withdrawals() -> None:
    moments = LogMoments(
        pd.Series([0.004], index=["a0"]),
        pd.DataFrame([[0.05**2]], index=["a0"], columns=["a0"]),
        120,
    )
    returns = normal_returns(
        moments, n_paths=4000, n_periods=240, rng=np.random.default_rng(11), max_cells=MAX_CELLS
    )
    plan = _plan(
        initial_wealth=100_000.0, flows=(Flow("withdrawal", 500.0, 0, 239, True),), inflation=0.02
    )
    summary = summarize(
        project(plan, returns),
        returns,
        start=START,
        goal_real=50_000.0,
        percentiles=(5, 50, 95),
        early_periods=60,
    )
    assert summary.sequence_worst < summary.sequence_best
    assert 0.0 < summary.p_depleted < 1.0


def test_sensitivity_with_common_random_numbers() -> None:
    moments = LogMoments(
        pd.Series([0.005], index=["a0"]),
        pd.DataFrame([[0.04**2]], index=["a0"], columns=["a0"]),
        120,
    )

    def simulate(shift: float, scale: float) -> SimulatedReturns:
        shifted = shifted_moments(
            moments, annual_mean_shift=shift, vol_scale=scale, periods_per_year=12
        )
        return normal_returns(
            shifted, n_paths=2000, n_periods=120, rng=np.random.default_rng(12), max_cells=MAX_CELLS
        )

    plan = _plan(
        initial_wealth=10_000.0,
        flows=(Flow("contribution", 200.0, 0, 119, True),),
        inflation=0.02,
        annual_cost=0.004,
    )
    rows = {row.label: row for row in sensitivity(plan, simulate, goal_real=40_000.0)}
    assert "costs -0.5 pp" not in rows  # 0.4 % - 0.5 % would be negative
    base = rows["base"]
    assert rows["mean return +1 pp"].median_terminal_real > base.median_terminal_real
    assert rows["mean return -1 pp"].median_terminal_real < base.median_terminal_real
    assert rows["inflation +1 pp"].median_terminal_real < base.median_terminal_real
    assert rows["costs +0.5 pp"].median_terminal_real < base.median_terminal_real
    assert rows["volatility x1.2"].p_goal_se == pytest.approx(
        math.sqrt(rows["volatility x1.2"].p_goal * (1 - rows["volatility x1.2"].p_goal) / 2000)
    )
    with_cost = {
        r.label
        for r in sensitivity(_plan(annual_cost=0.01, initial_wealth=1.0), simulate, goal_real=1.0)
    }
    assert "costs -0.5 pp" in with_cost


def test_shifted_moments() -> None:
    moments = LogMoments(
        pd.Series([0.005], index=["a0"]), pd.DataFrame([[0.0016]], index=["a0"], columns=["a0"]), 60
    )
    shifted = shifted_moments(moments, annual_mean_shift=0.012, vol_scale=1.5, periods_per_year=12)
    assert float(shifted.mean.iloc[0]) == pytest.approx(0.006)
    assert shifted.covariance.to_numpy()[0, 0] == pytest.approx(0.0036)
    with pytest.raises(ValidationError, match="vol_scale"):
        shifted_moments(moments, annual_mean_shift=0.0, vol_scale=0.0, periods_per_year=12)
