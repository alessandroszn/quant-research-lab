"""M1 end-to-end example on synthetic data: CSV with provenance -> returns -> verified metrics.

Run with ``uv run python examples/m1_analytics_core.py``. Everything is synthetic and seeded;
no network access, and nothing is written outside a temporary folder.

Steps:

1. Write a synthetic price file in an Italian broker format (``;`` delimiter, ``,`` decimals,
   dd/mm/yyyy dates) and import it byte-for-byte into a raw store with provenance.
2. Read it through an explicit mapping (formats and price type declared, never guessed).
3. Convert prices to simple monthly returns and compute excess returns over a synthetic
   risk-free rate.
4. Compute performance, risk and benchmark-relative metrics, all labelled.

The output is analytics on synthetic data, not investment advice.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from qrlab.core import Currency, Frequency, ReturnKind, excess_returns, prices_to_returns
from qrlab.data import (
    ColumnSpec,
    CsvMapping,
    FileFormat,
    PriceType,
    RawStore,
    import_local_file,
    parse_price_csv,
)
from qrlab.metrics import (
    SharpeSE,
    UndefinedMetricError,
    annualised_geometric_return,
    annualised_volatility,
    capm_regression,
    down_capture,
    historical_es,
    historical_var,
    information_ratio,
    max_drawdown,
    sharpe_ratio,
    tracking_error,
    up_capture,
)

SEED = 20261110
PERIODS_PER_YEAR = 12


def synthetic_price_file(path: Path) -> None:
    """Write ten years of month-end prices for a fund and its benchmark (synthetic)."""
    rng = np.random.default_rng(SEED)
    dates = pd.date_range("2016-01-31", periods=121, freq="ME")
    market = rng.normal(0.006, 0.04, len(dates) - 1)
    fund = 0.0005 + 0.95 * market + rng.normal(0, 0.008, len(dates) - 1)
    bench_prices = 100 * np.concatenate([[1.0], np.cumprod(1 + market)])
    fund_prices = 50 * np.concatenate([[1.0], np.cumprod(1 + fund)])
    lines = ["Data;Fondo;Indice"]
    for day, f, b in zip(dates, fund_prices, bench_prices, strict=True):
        lines.append(f"{day:%d/%m/%Y};{f:.4f}".replace(".", ",") + f";{b:.4f}".replace(".", ","))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Run the example and print a labelled report."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "synthetic_prices.csv"
        synthetic_price_file(source)

        store = RawStore(root / "data")
        stored = import_local_file(
            source,
            store,
            dataset="synthetic_prices",
            now=lambda: datetime(2026, 11, 10, tzinfo=UTC),
        )
        mapping = CsvMapping(
            date_column="Data",
            date_format="%d/%m/%Y",
            delimiter=";",
            decimal_separator=",",
            thousands_separator=None,
            encoding="utf-8",
            currency=Currency("EUR"),
            frequency=Frequency.MONTHLY,
            columns={
                "Fondo": ColumnSpec("SYNTHETIC_FUND", PriceType.TOTAL_RETURN),
                "Indice": ColumnSpec("SYNTHETIC_INDEX", PriceType.TOTAL_RETURN),
            },
            file_format=FileFormat.CSV,
            sheet=None,
            skip_rows=0,
            value_affixes=(),
        )
        prices = parse_price_csv(store.read(stored), stored.provenance, mapping).dataset

    returns = prices_to_returns(prices.data, kind=ReturnKind.SIMPLE)
    fund, bench = returns["SYNTHETIC_FUND"], returns["SYNTHETIC_INDEX"]
    risk_free = pd.Series(0.02 / 12, index=returns.index)  # synthetic flat 2 % a year
    fund_excess = excess_returns(fund, risk_free, kind=ReturnKind.SIMPLE)
    bench_excess = excess_returns(bench, risk_free, kind=ReturnKind.SIMPLE)

    sharpe = sharpe_ratio(
        fund_excess, periods_per_year=PERIODS_PER_YEAR, se_method=SharpeSE.IID_NORMAL
    )
    capm = capm_regression(fund_excess, bench_excess, periods_per_year=PERIODS_PER_YEAR)
    p = PERIODS_PER_YEAR

    print("Synthetic fund vs synthetic index - monthly total returns in EUR (time-weighted)")
    print(f"Sample: {returns.index[0]:%Y-%m} to {returns.index[-1]:%Y-%m}, {len(returns)} months")
    print(f"Provenance: {stored.provenance.url}, sha256 {stored.provenance.sha256[:12]}...")
    print()
    print("In-sample results (no out-of-sample claim is made)")
    print(
        f"  CAGR                     {annualised_geometric_return(fund, periods_per_year=p):8.2%}"
    )
    print(f"  Volatility (annualised)  {annualised_volatility(fund, periods_per_year=p):8.2%}")
    print(
        f"  Sharpe (annualised)      {sharpe.value:8.2f}  (Lo SE {sharpe.standard_error:.2f}, iid)"
    )
    print(f"  Max drawdown             {max_drawdown(fund):8.2%}")
    print(f"  VaR 95% (1 month, hist.) {historical_var(fund, confidence=0.95):8.2%}")
    print(f"  ES 95% (1 month, hist.)  {historical_es(fund, confidence=0.95):8.2%}")
    print(f"  Tracking error           {tracking_error(fund, bench, periods_per_year=p):8.2%}")
    try:
        ir = information_ratio(fund, bench, periods_per_year=p)
        print(f"  Information ratio        {ir:8.2f}")
    except UndefinedMetricError:
        print("  Information ratio             n/a")
    print(
        f"  Beta {capm.beta:.3f} (SE {capm.se_beta:.3f}), "
        f"alpha {capm.alpha_annualised:.2%} a year (SE {capm.se_alpha_annualised:.2%})"
    )
    print(
        f"  Up / down capture        {up_capture(fund, bench, periods_per_year=p):.2f} / "
        f"{down_capture(fund, bench, periods_per_year=p):.2f}"
    )
    print()
    print("Analytics on synthetic data, not investment advice.")


if __name__ == "__main__":
    main()
