"""Phase 3.3 example on synthetic data: a savings plan and a withdrawal plan, projected.

Run with ``uv run python examples/projection_plan.py``. Offline and deterministic (fixed seed).

A synthetic 60/40 equity/bond history gives the return assumptions. A savings plan (a lump sum
and a monthly contribution indexed to inflation) is projected for 20 years with three engines;
a withdrawal plan is projected for 25 years to show depletion and sequence-of-returns risk;
the savings plan is re-run under changed assumptions. Taxes use example Italian rates (26 %
on realised gains, 0.20 % stamp duty a year), which are illustrations, not tax advice.

Projections are scenarios from stated assumptions, not forecasts or investment advice.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from qrlab.core import Currency, ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.simulation import (
    MAX_CELLS,
    Flow,
    Plan,
    SimulatedReturns,
    TaxModel,
    bootstrap_returns,
    log_moments,
    normal_returns,
    project,
    sensitivity,
    shifted_moments,
    student_t_returns,
    summarize,
)

SEED = 20261111
PATHS = 5000
START = date(2026, 6, 30)
EUR = Currency("EUR")
ITALY_EXAMPLE = TaxModel(capital_gains_rate=0.26, wealth_tax_rate=0.002)


def history() -> pd.DataFrame:
    """Return 20 years of synthetic monthly equity and bond returns."""
    rng = np.random.default_rng(SEED)
    index = pd.date_range("2006-01-31", periods=240, freq="ME")
    cov = np.array([[0.045**2, 0.3 * 0.045 * 0.015], [0.3 * 0.045 * 0.015, 0.015**2]])
    values = rng.multivariate_normal([0.006, 0.002], cov, size=240)
    return pd.DataFrame(values, index=index, columns=["equity", "bonds"])


def main() -> None:
    """Print the projections."""
    data = history()
    moments = log_moments(data, kind=ReturnKind.SIMPLE, missing=NanPolicy.RAISE)
    weights = pd.Series({"equity": 0.6, "bonds": 0.4})
    print("Projections from stated assumptions: scenarios, not forecasts or investment advice.")
    print(f"Return assumptions estimated on {moments.n_obs} synthetic monthly returns.\n")

    savings = Plan(
        initial_wealth=20_000.0,
        currency=EUR,
        weights=weights,
        periods_per_year=12,
        flows=(Flow("contribution", 500.0, 0, 239, True),),
        flow_timing="start",
        rebalance_every=12,
        annual_cost=0.003,
        inflation=0.02,
        taxes=ITALY_EXAMPLE,
    )
    goal = 200_000.0
    print("Savings plan: 20,000 EUR now, 500 EUR a month indexed to 2 % inflation, 20 years,")
    print(f"60/40 rebalanced yearly, costs 0.30 % a year. Goal: {goal:,.0f} EUR in today's money.")
    engines: dict[str, SimulatedReturns] = {
        "normal": normal_returns(
            moments,
            n_paths=PATHS,
            n_periods=240,
            rng=np.random.default_rng(SEED),
            max_cells=MAX_CELLS,
        ),
        "Student-t (5)": student_t_returns(
            moments,
            dof=5,
            n_paths=PATHS,
            n_periods=240,
            rng=np.random.default_rng(SEED),
            max_cells=MAX_CELLS,
        ),
        "block bootstrap (12)": bootstrap_returns(
            data,
            kind=ReturnKind.SIMPLE,
            missing=NanPolicy.RAISE,
            mean_block_length=12.0,
            n_paths=PATHS,
            n_periods=240,
            rng=np.random.default_rng(SEED),
            max_cells=MAX_CELLS,
        ),
    }
    for name, returns in engines.items():
        summary = summarize(
            project(savings, returns),
            returns,
            start=START,
            goal_real=goal,
            percentiles=(5, 50, 95),
            early_periods=60,
        )
        p5, p50, p95 = summary.terminal_real
        print(
            f"  {name:<21} real P5 {p5:>9,.0f}  P50 {p50:>9,.0f}  P95 {p95:>9,.0f}  "
            f"P(goal) {summary.p_goal:.1%} +/- {summary.p_goal_se:.1%}"
        )

    withdrawals = Plan(
        initial_wealth=500_000.0,
        currency=EUR,
        weights=weights,
        periods_per_year=12,
        flows=(Flow("withdrawal", 2_000.0, 0, 299, True),),
        flow_timing="start",
        rebalance_every=12,
        annual_cost=0.003,
        inflation=0.02,
        taxes=ITALY_EXAMPLE,
    )
    returns = normal_returns(
        moments, n_paths=PATHS, n_periods=300, rng=np.random.default_rng(SEED), max_cells=MAX_CELLS
    )
    summary = summarize(
        project(withdrawals, returns),
        returns,
        start=START,
        goal_real=0.0,
        percentiles=(5, 50, 95),
        early_periods=60,
    )
    print("\nWithdrawal plan: 500,000 EUR, 2,000 EUR a month net of tax, indexed, 25 years:")
    print(f"  P(running out) {summary.p_depleted:.1%} +/- {summary.p_depleted_se:.1%}")
    print(
        "  sequence risk: median real terminal wealth "
        f"{summary.sequence_worst:,.0f} EUR after the worst 10 % of first 5 years vs "
        f"{summary.sequence_best:,.0f} EUR after the best 10 %"
    )

    def simulate(shift: float, scale: float) -> SimulatedReturns:
        changed = shifted_moments(
            moments, annual_mean_shift=shift, vol_scale=scale, periods_per_year=12
        )
        return normal_returns(
            changed,
            n_paths=PATHS,
            n_periods=240,
            rng=np.random.default_rng(SEED),
            max_cells=MAX_CELLS,
        )

    print("\nSensitivity of the savings plan (same random numbers):")
    for row in sensitivity(savings, simulate, goal_real=goal):
        median = row.median_terminal_real
        print(f"  {row.label:<18} P(goal) {row.p_goal:6.1%}  median real {median:>9,.0f}")


if __name__ == "__main__":
    main()
