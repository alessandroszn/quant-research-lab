"""Phase 4.2 example on synthetic data: portfolio construction judged out of sample.

Run with ``uv run python examples/portfolio_construction.py``. Offline and deterministic.

Six synthetic assets with a two-factor structure and noisy expected returns. Each method is
re-estimated on an expanding training window (4.1 walk-forward splits, Ledoit-Wolf covariance)
and held over the next 12 months, which it has never seen. Only these out-of-sample months are
reported; no in-sample figure is shown as evidence. 1/N is the benchmark to beat.

The output is analytics on synthetic data, not investment advice.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from qrlab.core import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.metrics.drawdown import max_drawdown
from qrlab.optimization import (
    Constraints,
    CostModel,
    OptimizationResult,
    ThresholdPolicy,
    equal_weights,
    hierarchical_risk_parity,
    maximum_diversification,
    mean_variance,
    minimum_variance,
    risk_budgeting,
    trade,
)
from qrlab.risk import CovarianceEstimate, ledoit_wolf_covariance
from qrlab.validation import expanding_splits, take

SEED = 20261111
MONTHS = 240
ASSETS = ["US equity", "EU equity", "EM equity", "Gov bonds", "Corp bonds", "Gold"]
LONG = Constraints(
    long_only=True, bounds=dict.fromkeys(ASSETS, (0.0, 0.4)), groups={}, turnover=None, current=None
)


def synthetic_returns() -> pd.DataFrame:
    """Return synthetic monthly returns of six assets driven by two factors."""
    rng = np.random.default_rng(SEED)
    index = pd.date_range("2006-01-31", periods=MONTHS, freq="ME")
    factors = rng.normal(0.0, 1.0, size=(MONTHS, 2)) * [0.04, 0.012]
    loadings = np.array([[1.0, 0.1], [1.1, 0.0], [1.3, -0.2], [-0.1, 1.0], [0.3, 0.8], [0.1, 0.3]])
    specific = rng.normal(0.0, 1.0, size=(MONTHS, 6)) * [0.01, 0.015, 0.03, 0.004, 0.006, 0.04]
    drift = np.array([0.006, 0.005, 0.007, 0.002, 0.003, 0.004])
    return pd.DataFrame(drift + factors @ loadings.T + specific, index=index, columns=ASSETS)


def methods(train: pd.DataFrame) -> dict[str, OptimizationResult]:
    """Fit every method on the training window only."""
    cov: CovarianceEstimate = ledoit_wolf_covariance(
        train, kind=ReturnKind.SIMPLE, missing=NanPolicy.RAISE
    )
    mu = train.mean()
    equal = pd.Series(1.0 / len(ASSETS), index=ASSETS)
    return {
        "1/N": equal_weights(cov, LONG),
        "minimum variance": minimum_variance(cov, LONG),
        "mean-variance (lambda 4)": mean_variance(mu, cov, LONG, risk_aversion=4.0),
        "equal risk contribution": risk_budgeting(cov, equal),
        "maximum diversification": maximum_diversification(cov),
        "hierarchical risk parity": hierarchical_risk_parity(cov),
    }


def main() -> None:
    """Print out-of-sample results of each method."""
    data = synthetic_returns()
    index = pd.DatetimeIndex(data.index)
    splits = expanding_splits(
        index, min_train=60, test_size=12, step=12, embargo=0, label_ends=None
    )
    print("Synthetic data; out-of-sample months only. Analytics, not investment advice.")
    print(f"{len(splits)} walk-forward splits: train from 60 months, test 12 months each.\n")
    oos: dict[str, list[pd.Series]] = {}
    turnover: dict[str, list[float]] = {}
    previous: dict[str, pd.Series] = {}
    for split in splits.splits:
        train = take(data, splits, split.train)
        test = take(data, splits, split.test)
        assert isinstance(train, pd.DataFrame)
        assert isinstance(test, pd.DataFrame)
        for name, result in methods(train).items():
            oos.setdefault(name, []).append(test @ result.weights)
            if name in previous:
                turnover.setdefault(name, []).append(
                    float((result.weights - previous[name]).abs().sum())
                )
            previous[name] = result.weights
    widths = (-26, 11, 9, 6, 8, 9)
    header = ("method", "ann. return", "ann. vol", "ratio", "max DD", "turnover")
    print(
        " ".join(
            f"{h:<{-w}}" if w < 0 else f"{h:>{w}}" for h, w in zip(header, widths, strict=True)
        )
    )
    for name, pieces in oos.items():
        returns = pd.concat(pieces)
        ann_return = (1.0 + returns).prod() ** (12 / len(returns)) - 1.0
        ann_vol = float(returns.std(ddof=1)) * math.sqrt(12)
        print(
            f"{name:<26} {ann_return:>11.2%} {ann_vol:>9.2%} {ann_return / ann_vol:>6.2f} "
            f"{max_drawdown(returns):>8.2%} {np.mean(turnover[name]):>9.2%}"
        )
    months = len(returns)
    print(f"\n{months} out-of-sample months; ratio = annualised return / volatility.")
    print("Small differences between methods are within sampling noise; this is not evidence.")

    target = pd.Series({"equity": 0.6, "bonds": 0.4})
    drifted = pd.Series({"equity": 0.66, "bonds": 0.34})
    policy = ThresholdPolicy(0.05, "band")
    destination = policy.destination(drifted, target)
    cost = trade(drifted, destination, 100_000.0, CostModel(0.001, 2.0))
    print(
        f"\nThreshold policy (band 5 %, to the band edge): 66/34 -> "
        f"{destination['equity']:.0%}/{destination['bonds']:.0%}, "
        f"traded {cost.traded:,.0f} EUR, cost {cost.cost:,.2f} EUR"
    )


if __name__ == "__main__":
    main()
