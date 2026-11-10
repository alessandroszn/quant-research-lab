"""Phase 2.2 example on synthetic data: factor exposures with robust inference.

Run with ``uv run python examples/factor_exposures.py``. Offline and deterministic.

A synthetic EUR fund is built from synthetic USD factors, converted to USD with dated EUR/USD
rates (Ken French factors are in USD), and regressed on a Fama-French 3-factor model with
momentum using Newey-West standard errors. A stationary bootstrap gives an interval for the
fund's mean monthly excess return.

The output is analytics on synthetic data, not investment advice.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from qrlab.core import ReturnKind, convert_return_currency
from qrlab.stats import (
    CovType,
    FactorModel,
    factor_exposures,
    newey_west_lags,
    stationary_bootstrap,
)

SEED = 20261110
MONTHS = 240
PERIODS_PER_YEAR = 12


def main() -> None:
    """Run the example and print a labelled report."""
    rng = np.random.default_rng(SEED)
    index = pd.date_range("2006-01-31", periods=MONTHS, freq="ME")
    factors = pd.DataFrame(
        rng.normal([0.006, 0.001, 0.001, 0.004], [0.045, 0.025, 0.03, 0.04], size=(MONTHS, 4)),
        index=index,
        columns=["Mkt-RF", "SMB", "HML", "WML"],
    )
    factors["RF"] = 0.0015
    # USD per EUR, one observation before the first month.
    eurusd = pd.Series(
        1.25 * np.exp(np.cumsum(rng.normal(0, 0.025, MONTHS + 1))),
        index=pd.date_range("2005-12-31", periods=MONTHS + 1, freq="ME"),
    )
    # A fund that is, in USD terms, 0.95 market + 0.2 size - 0.1 momentum, with tracking noise.
    usd_return = (
        factors["RF"]
        + 0.95 * factors["Mkt-RF"]
        + 0.2 * factors["SMB"]
        - 0.1 * factors["WML"]
        + rng.normal(0, 0.004, MONTHS)
    )
    eur_return = (1 + usd_return) / (eurusd.to_numpy()[1:] / eurusd.to_numpy()[:-1]) - 1

    fund_usd = convert_return_currency(eur_return, eurusd, kind=ReturnKind.SIMPLE)
    excess = fund_usd - factors["RF"]
    lags = newey_west_lags(MONTHS)
    result = factor_exposures(
        excess,
        factors,
        model=FactorModel.FF3_MOM,
        periods_per_year=PERIODS_PER_YEAR,
        cov_type=CovType.HAC,
        hac_lags=lags,
        momentum_column="WML",
    )
    interval = stationary_bootstrap(
        excess,
        lambda values: float(np.mean(values)),
        mean_block_length=6.0,
        n_resamples=2000,
        confidence=0.95,
        rng=rng,
    )

    print(f"Synthetic fund, {MONTHS} months, returns converted EUR -> USD to match the factors")
    print(f"Model {result.model.name}, Newey-West standard errors with {lags} lags, in-sample")
    print()
    print(
        f"  alpha  {result.alpha_annualised:8.2%} a year (SE {result.alpha_se_annualised:.2%}, "
        f"t {result.tvalues['const']:.2f})"
    )
    for name in map(str, result.betas.index):
        beta, se, t = result.betas[name], result.std_errors[name], result.tvalues[name]
        print(f"  {name:6s} {beta:8.3f} (SE {se:.3f}, t {t:.1f})")
    print(f"  R2     {result.r_squared:8.3f}")
    print()
    print(
        f"Mean monthly excess return {interval.estimate:.3%}, 95% stationary-bootstrap interval "
        f"[{interval.low:.3%}, {interval.high:.3%}] (mean block 6 months)"
    )
    print()
    print("No significance claims are made; analytics on synthetic data, not investment advice.")


if __name__ == "__main__":
    main()
