"""Phase 2.1 example on synthetic data: broker export -> ledger -> valuation -> TWR, MWR, P&L.

Run with ``uv run python examples/portfolio_toy.py``. Offline and deterministic; the numbers
are the hand-reconciled toy portfolio of ``docs/design/2.1-portfolio.md``.

The output is analytics on synthetic data, not investment advice.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from qrlab.core import Currency
from qrlab.data import PriceType, Provenance
from qrlab.instruments import Isin
from qrlab.portfolio import (
    FlowTiming,
    PriceSeries,
    external_flows_by_date,
    load_broker_mapping,
    money_weighted_return,
    parse_broker_csv,
    pnl_breakdown,
    replay,
    time_weighted_returns,
    value_portfolio,
)

EUR = Currency("EUR")
FUND = Isin("IE0000000012")  # made-up ISIN with a valid check digit
MAPPING = Path(__file__).parents[1] / "configs" / "csv_mappings" / "example_broker.toml"
EXPORT = """\
Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;\
Controvalore;Divisa controvalore;Descrizione
t5;31/03/2026;Vendita;IE0000000012;-50;54,00;EUR;;-10,00;;;;
t4;27/02/2026;Dividendo;IE0000000012;;;EUR;100,00;;;;;
t3;30/01/2026;Bonifico in entrata;;;;EUR;5.000,00;;;;;
t2;02/01/2026;Acquisto;IE0000000012;100;50,00;EUR;;-10,00;;;;
t1;02/01/2026;Bonifico in entrata;;;;EUR;10.000,00;;;;;
"""
DATES = [date(2026, 1, 2), date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31)]


def eur_only(amount, on):  # type: ignore[no-untyped-def]
    """Identity converter: this example is in EUR only (use EcbConverter for other currencies)."""
    return amount


def main() -> None:
    """Run the example and print a labelled report."""
    content = EXPORT.encode("utf-8")
    provenance = Provenance(
        source="user",
        dataset="synthetic_broker_export",
        url="file:movimenti.csv",
        retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic",
    )
    imported = parse_broker_csv(content, provenance, load_broker_mapping(MAPPING))
    history = replay(imported.transactions, base=EUR, to_base=eur_only)
    prices = {
        FUND: PriceSeries(
            pd.Series([50.0, 55.0, 52.0, 54.0], index=pd.DatetimeIndex(DATES)), EUR, PriceType.PRICE
        )
    }
    valuation = value_portfolio(history, prices, eur_only, dates=DATES, max_price_age_days=0)
    twr = time_weighted_returns(
        valuation, external_flows_by_date(history), flow_timing=FlowTiming.START_OF_DAY
    )
    mwr = money_weighted_return(history, valuation, end=DATES[-1])
    pnl = pnl_breakdown(history, valuation, eur_only, start=None, end=DATES[-1])

    print("Synthetic portfolio in EUR, 2026-01-02 to 2026-03-31")
    print(f"Imported {len(imported.transactions)} transactions; notes: {imported.notes[0]}")
    print()
    print("Values (EUR):", ", ".join(f"{d}: {v:,.2f}" for d, v in valuation.totals.items()))
    print(f"TWR (time-weighted, flows at start of day, not annualised): {twr.total:.4%}")
    print(f"{mwr.label}: {mwr.rate:.4%} a year (unique root: {mwr.unique_root_guaranteed})")
    print()
    print("Profit and loss (EUR)")
    print(f"  total     {pnl.total:>10,.2f}  = value change minus net deposits")
    print(f"  realised  {pnl.realised:>10,.2f}")
    print(f"  unrealised{pnl.unrealised_change:>10,.2f}")
    print(f"  income    {pnl.income:>10,.2f}")
    print(f"  costs     {pnl.costs:>10,.2f}")
    print(f"  cash FX   {pnl.cash_fx:>10,.2f}")
    print(f"  residual  {pnl.residual:>10,.2f}")
    print()
    print("TWR and MWR measure different things and are not comparable.")
    print("Analytics on synthetic data, not investment advice.")


if __name__ == "__main__":
    main()
