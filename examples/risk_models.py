"""Phases 3.1-3.2 example on synthetic data: risk models, VaR backtests and stress tests.

Run with ``uv run python examples/risk_models.py``. Offline and deterministic.

Four synthetic assets driven by two synthetic factors with fat-tailed (Student-t) shocks. The
example compares covariance estimators, splits portfolio risk into asset and factor
contributions, computes one-day VaR and ES at 99 % with four methods, and backtests rolling
VaR forecasts that use only earlier data. Every figure is one day and not annualised.
Finally it runs the example stress scenarios of ``configs/scenarios/example.toml`` on
today's weights: the synthetic history starts in 2020, so the 2008 replay is not covered.

The output is analytics on synthetic data, not investment advice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from qrlab.core import Currency, Money, ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.instruments import Isin
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var
from qrlab.risk import (
    cornish_fisher,
    effective_number_of_bets,
    ewma_covariance,
    factor_contributions,
    filtered_historical,
    fit_factor_model,
    historical_es_contributions,
    ledoit_wolf_covariance,
    sample_covariance,
    var_backtest,
    var_forecasts,
    volatility_contributions,
)
from qrlab.scenarios import (
    MarketData,
    PositionSeries,
    StressPortfolio,
    load_scenarios,
    run_scenario,
)

ROOT = Path(__file__).parents[1]
EUR = Currency("EUR")
ISINS = {  # made-up ISINs with valid check digits
    "Equity A": Isin("IE0000002018"),
    "Equity B": Isin("IE0000002026"),
    "Balanced": Isin("IE0000002034"),
    "Bonds": Isin("IE0000002042"),
}
SEED = 20261111
DAYS = 1500
CONFIDENCE = 0.99
WINDOW = 250
SIMPLE, RAISE = ReturnKind.SIMPLE, NanPolicy.RAISE


def synthetic_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return synthetic daily asset and factor returns (Student-t shocks, 4 d.o.f.)."""
    rng = np.random.default_rng(SEED)
    index = pd.bdate_range("2020-01-01", periods=DAYS)
    scale = np.sqrt(4 / 2)  # Student-t(4) has variance 2: rescale to unit variance
    factors = pd.DataFrame(
        rng.standard_t(4, size=(DAYS, 2)) / scale * [0.010, 0.006],
        index=index,
        columns=["Mkt-RF", "rates"],
    )
    betas = np.array([[1.1, 0.0], [0.9, 0.2], [0.3, 1.0], [0.0, 0.8]])
    noise = rng.standard_t(4, size=(DAYS, 4)) / scale * [0.006, 0.005, 0.003, 0.002]
    assets = pd.DataFrame(
        factors.to_numpy() @ betas.T + noise,
        index=index,
        columns=["Equity A", "Equity B", "Balanced", "Bonds"],
    )
    return assets, factors


def main() -> None:
    """Print the risk analysis of the synthetic portfolio."""
    assets, factors = synthetic_data()
    weights = pd.Series({"Equity A": 0.35, "Equity B": 0.25, "Balanced": 0.2, "Bonds": 0.2})
    portfolio = assets @ weights
    print("Synthetic data, one-day figures, not annualised. Analytics, not investment advice.\n")

    print("Asset volatility by covariance estimator (one day):")
    sample = sample_covariance(assets, kind=SIMPLE, missing=RAISE)
    ewma = ewma_covariance(assets, kind=SIMPLE, missing=RAISE, decay=0.94, demean=False)
    shrunk = ledoit_wolf_covariance(assets, kind=SIMPLE, missing=RAISE)
    table = pd.DataFrame(
        {
            "sample": sample.volatilities(),
            "EWMA (lambda 0.94)": ewma.volatilities(),
            "Ledoit-Wolf": shrunk.volatilities(),
        }
    )
    print(table.map(lambda v: f"{v:.4%}").to_string())
    print(f"Ledoit-Wolf shrinkage intensity: {shrunk.params['shrinkage']:.4f}\n")

    contributions = volatility_contributions(sample, weights)
    print(f"Portfolio volatility {contributions.total:.4%}, contributions (share):")
    for asset in weights.index:
        print(
            f"  {asset:<9} {contributions.component[asset]:.4%} ({contributions.share[asset]:.1%})"
        )
    print(f"Effective number of bets: {effective_number_of_bets(sample, weights):.2f} of 4\n")

    tail = historical_es_contributions(
        assets, weights, confidence=CONFIDENCE, kind=SIMPLE, missing=RAISE
    )
    print(f"Historical ES {CONFIDENCE:.0%} {tail.total:.4%}, shares:")
    print("  " + ", ".join(f"{a} {s:.1%}" for a, s in tail.share.items()) + "\n")

    sample_cov = lambda f: sample_covariance(f, kind=SIMPLE, missing=RAISE)  # noqa: E731
    model = fit_factor_model(
        assets, factors, kind=SIMPLE, missing=RAISE, factor_covariance=sample_cov
    )
    split = factor_contributions(model, weights)
    print("Factor model (OLS betas, sample factor covariance):")
    print(model.betas.round(3).to_string())
    print(
        f"Volatility {split.total:.4%} = factors "
        + " + ".join(f"{k} {v:.4%}" for k, v in split.factor.items())
        + f" + specific {split.specific.sum():.4%}\n"
    )

    cf = cornish_fisher(portfolio, confidence=CONFIDENCE)
    fhs = filtered_historical(portfolio, confidence=CONFIDENCE, decay=0.94, warmup=WINDOW)
    print(f"One-day VaR / ES at {CONFIDENCE:.0%} (positive losses):")
    rows = [
        ("historical", historical_var(portfolio, confidence=CONFIDENCE),
         historical_es(portfolio, confidence=CONFIDENCE)),
        ("normal", parametric_var(portfolio, confidence=CONFIDENCE),
         parametric_es(portfolio, confidence=CONFIDENCE)),
        ("Cornish-Fisher", cf.var, cf.es),
        ("filtered historical (next day)", fhs.var, fhs.es),
    ]  # fmt: skip
    for name, var, es in rows:
        print(f"  {name:<31} VaR {var:.4%}  ES {es:.4%}")
    print(f"  (skewness {cf.skewness:.2f}, excess kurtosis {cf.excess_kurtosis:.2f})\n")

    print(f"Backtest of rolling {WINDOW}-day VaR forecasts (only earlier data), {CONFIDENCE:.0%}:")
    for name, method in (
        ("historical", lambda r: historical_var(r, confidence=CONFIDENCE)),
        ("normal", lambda r: parametric_var(r, confidence=CONFIDENCE)),
    ):
        forecasts = var_forecasts(portfolio, window=WINDOW, model=method)
        result = var_backtest(portfolio.loc[forecasts.index], forecasts, confidence=CONFIDENCE)
        print(
            f"  {name:<10} {result.exceedances} exceedances, {result.expected:.1f} expected; "
            f"Kupiec p {result.kupiec_pvalue:.3f}; Christoffersen cc p "
            f"{result.conditional_coverage_pvalue:.3f}"
        )
    print("A test that does not reject is not proof that the model is right.\n")

    stress(assets, factors, weights, model.betas)


def stress(
    assets: pd.DataFrame, factors: pd.DataFrame, weights: pd.Series, betas: pd.DataFrame
) -> None:
    """Run the example scenarios on today's weights (90 % invested, 10 % EUR cash)."""
    invested = 0.9
    portfolio = StressPortfolio(
        as_of=date(2026, 6, 30),
        value=Money(Decimal("100000"), EUR),
        position_weights={ISINS[str(a)]: invested * float(w) for a, w in weights.items()},
        cash_weights={EUR: 1.0 - invested},
        exposure_currencies=dict.fromkeys(ISINS.values(), EUR),
    )
    market = MarketData(
        positions={ISINS[a]: PositionSeries(assets[a], EUR) for a in ["Equity A", "Bonds"]},
        factors=factors,
        betas=betas.rename(index={a: ISINS[a].code for a in betas.index}),
        fx={},
    )
    print("Stress scenarios on today's weights ('what if', not forecasts):")
    for scenario in load_scenarios(ROOT / "configs" / "scenarios" / "example.toml"):
        result = run_scenario(scenario, portfolio, market)
        methods = sorted({r.method for r in result.rows})
        print(
            f"  {scenario.id:<16} {result.portfolio_return:+.2%}  P&L {result.pnl.amount:>10}  "
            f"not covered {result.not_covered_weight:.0%}  methods {methods}"
        )


if __name__ == "__main__":
    main()
