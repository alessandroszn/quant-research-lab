"""Phase 4.4 example on synthetic data: where the active return came from.

Run with ``uv run python examples/attribution_example.py``. Offline and deterministic.

A synthetic portfolio is compared with a 60/40 benchmark over 36 months: it overweights
equity and picks its own funds inside each segment. The active return is attributed three
ways, each adding up exactly to it:

- Brinson-Fachler by segment, linked over the months with Carino;
- factor-based, on the equity market factor, with alpha and its t-statistic;
- currency, for one month in which part of the equity is in US dollars.

Attribution describes a result. It is not evidence of skill. The output is analytics on
synthetic data, not investment advice.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from qrlab.attribution import brinson_fachler, currency_attribution, factor_attribution
from qrlab.stats.regression import CovType

SEED = 20261112
MONTHS = 36
SEGMENTS = ["equity", "bonds"]


def synthetic() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return portfolio and benchmark weights and segment returns, month by month."""
    rng = np.random.default_rng(SEED)
    index = pd.date_range("2023-01-31", periods=MONTHS, freq="ME")
    market = rng.normal(0.006, 0.04, MONTHS)
    bonds = rng.normal(0.002, 0.012, MONTHS)
    rb = pd.DataFrame({"equity": market, "bonds": bonds}, index=index)
    picks = pd.DataFrame(
        {"equity": rng.normal(0.0005, 0.008, MONTHS), "bonds": rng.normal(0.0, 0.002, MONTHS)},
        index=index,
    )
    rp = rb + picks
    tilt = 0.7 + 0.05 * np.sin(np.arange(MONTHS) / 4)
    wp = pd.DataFrame({"equity": tilt, "bonds": 1.0 - tilt}, index=index)
    wb = pd.DataFrame({"equity": 0.6, "bonds": 0.4}, index=index)
    return wp, rp, wb, rb


def main() -> None:
    """Print the three attributions."""
    wp, rp, wb, rb = synthetic()
    print("Synthetic data, 36 months. Attribution describes; it is not evidence of skill.\n")
    result = brinson_fachler(wp, rp, wb, rb, interaction="separate", linking="carino")
    print(
        f"Portfolio {result.portfolio_return:+.2%}, benchmark {result.benchmark_return:+.2%}, "
        f"active {result.active_return:+.2%} (compounded)"
    )
    print("Brinson-Fachler by segment, Carino-linked:")
    print(result.totals.map(lambda v: f"{v:+.3%}").to_string())
    effects = result.effect_totals()
    print(
        "Total: "
        + ", ".join(f"{k} {v:+.3%}" for k, v in effects.items())
        + f" = {float(effects.sum()):+.3%}\n"
    )

    active = (wp * rp).sum(axis=1) - (wb * rb).sum(axis=1)
    factors = pd.DataFrame({"equity market": rb["equity"]})
    fa = factor_attribution(active, factors, cov_type=CovType.HAC, hac_lags=3)
    print("Factor attribution of the monthly active return (Newey-West, 3 lags):")
    print(
        f"  beta to the equity market {fa.betas['equity market']:+.3f}; "
        f"market contribution {fa.contributions['equity market']:+.3%}"
    )
    label = "significant" if fa.alpha_significant else "not significant"
    print(
        f"  alpha {fa.alpha:+.4%} a month (t = {fa.alpha_t:+.2f}, {label}); "
        f"alpha over the period {fa.alpha_total:+.3%}"
    )
    print(
        f"  arithmetic sum of monthly active returns {fa.active_total:+.3%} = market + alpha "
        f"(residual below 1e-12: {abs(fa.residual_total) < 1e-12})\n"
    )

    month = currency_attribution(
        pd.Series({"EU equity": 0.3, "US equity": 0.4, "bonds": 0.3}),
        pd.Series({"EU equity": 0.3, "US equity": 0.3, "bonds": 0.4}),
        pd.Series({"EU equity": 0.02, "US equity": 0.03, "bonds": 0.002}),
        pd.Series({"EU equity": 0.018, "US equity": 0.03, "bonds": 0.002}),
        pd.Series({"EU equity": 0.0, "US equity": -0.02, "bonds": 0.0}),
    )
    a = month.active
    print("Currency attribution of one month (USD -2 % against EUR):")
    print(
        f"  active local {a.local:+.3%}, currency {a.currency:+.3%}, cross {a.cross:+.4%}, "
        f"total {a.total:+.3%}"
    )


if __name__ == "__main__":
    main()
