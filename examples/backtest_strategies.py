"""Phase 4.3 example on synthetic data: two strategies backtested with lag, costs and taxes.

Run with ``uv run python examples/backtest_strategies.py``. Offline and deterministic.

Twenty years of synthetic monthly returns for three equity-like assets and cash. Two strategies
decide at each month-end from the history up to that date and trade one month later
(execution lag 1). Costs are 0.10 % of the amount traded plus 1 EUR per trade, and the
capital-gains tax is 26 % (an example rate, not tax advice):

- time-series trend: hold the equity asset when its trailing 12-month return is positive,
  otherwise cash;
- cross-sectional momentum: hold the asset with the best trailing 6-month return.

Gross and net results are shown side by side against buy-and-hold equal weights. One synthetic
path proves nothing about a strategy; the example shows the mechanics, not evidence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from qrlab.backtest import (
    BacktestResult,
    Strategy,
    TradeOnSignal,
    run_backtest,
    summarize_backtest,
)
from qrlab.core import Money
from qrlab.optimization import CostModel
from qrlab.simulation import TaxModel

SEED = 20261111
MONTHS = 240
ASSETS = ["Equity A", "Equity B", "Equity C", "Cash"]
COSTS = CostModel(0.001, 1.0)
TAX = TaxModel(capital_gains_rate=0.26, wealth_tax_rate=0.0)
START = Money.of("100000", "EUR")


def synthetic_returns() -> pd.DataFrame:
    """Return synthetic monthly returns with mild momentum in the equity assets."""
    rng = np.random.default_rng(SEED)
    index = pd.date_range("2006-01-31", periods=MONTHS, freq="ME")
    shocks = rng.normal(0.0, 1.0, size=(MONTHS, 3)) * 0.045
    returns = np.zeros((MONTHS, 3))
    for t in range(MONTHS):
        persistence = 0.1 * returns[t - 1] if t else 0.0
        returns[t] = 0.005 + persistence + shocks[t]
    cash = np.full((MONTHS, 1), 0.0015)
    return pd.DataFrame(np.hstack([returns, cash]), index=index, columns=ASSETS)


def one_hot(asset: str) -> pd.Series:
    """Return target weights fully in ``asset``."""
    return pd.Series({a: float(a == asset) for a in ASSETS})


def trend(history: pd.DataFrame) -> pd.Series | None:
    """Hold Equity A when its trailing 12-month return is positive, otherwise cash."""
    if len(history) < 12:
        return None
    trailing = float(np.prod(1.0 + history["Equity A"].to_numpy()[-12:])) - 1.0
    return one_hot("Equity A" if trailing > 0 else "Cash")


def momentum(history: pd.DataFrame) -> pd.Series | None:
    """Hold the equity asset with the best trailing 6-month return."""
    if len(history) < 6:
        return None
    trailing = (1.0 + history[ASSETS[:3]].iloc[-6:]).prod() - 1.0
    return one_hot(str(trailing.idxmax()))


def run(strategy: Strategy, initial: pd.Series) -> BacktestResult:
    """Run one strategy with the example's lag, costs and taxes."""
    return run_backtest(
        synthetic_returns(),
        strategy,
        decide_every=1,
        execution_lag=1,
        policy=TradeOnSignal(),
        costs=COSTS,
        taxes=TAX,
        initial_weights=initial,
        initial_value=START,
        long_only=True,
    )


def main() -> None:
    """Print gross and net results."""
    equal = pd.Series(0.25, index=ASSETS)
    runs = {
        "buy and hold (1/4 each)": run(lambda h: None, equal),
        "time-series trend": run(trend, one_hot("Cash")),
        "cross-sectional momentum": run(momentum, one_hot("Cash")),
    }
    print("Synthetic data; lag 1 month, costs 0.10 % + 1 EUR, tax 26 %. Not investment advice.\n")
    print(
        f"{'strategy':<26} {'gross ann.':>10} {'net ann.':>9} {'net vol':>8} {'net maxDD':>10} "
        f"{'turnover/yr':>11} {'costs':>8} {'taxes':>9}"
    )
    for name, result in runs.items():
        s = summarize_backtest(result, periods_per_year=12)
        print(
            f"{name:<26} {s.gross.annualised_return:>10.2%} {s.net.annualised_return:>9.2%} "
            f"{s.net.annualised_volatility:>8.2%} {s.net.max_drawdown:>10.2%} "
            f"{s.annual_turnover:>11.0%} {s.costs_paid:>8,.0f} {s.taxes_paid:>9,.0f}"
        )
    print("\nGross minus net is what trading costs and taxes took. One path is not evidence.")


if __name__ == "__main__":
    main()
