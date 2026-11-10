"""Phase 2.3 example: an HTML report of the synthetic toy portfolio.

Run with ``uv run python examples/portfolio_report.py [output.html] [it|en]``. The default
output is ``results/portfolio_report_example.html`` (git-ignored). Offline and deterministic;
all data are synthetic. The report is analytics, not investment advice.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from qrlab.core import Currency, Money
from qrlab.data import PriceType, Provenance
from qrlab.instruments import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Isin,
    Replication,
)
from qrlab.portfolio import (
    FlowTiming,
    PriceSeries,
    load_broker_mapping,
    parse_broker_csv,
    replay,
    value_portfolio,
)
from qrlab.reporting import Language, build_portfolio_report, write_report

ROOT = Path(__file__).parents[1]
EUR = Currency("EUR")
FUND = Isin("IE0000000012")  # made-up ISIN with a valid check digit
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


def eur_only(amount: Money, on: date) -> Money:
    """Identity converter: the example is in EUR only (use EcbConverter otherwise)."""
    return amount


def main(output: Path, language: Language) -> Path:
    """Build the report and write it to ``output``; return the path."""
    import pandas as pd

    content = EXPORT.encode("utf-8")
    provenance = Provenance(
        source="user",
        dataset="synthetic_broker_export",
        url="file:movimenti.csv",
        retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic example data",
    )
    mapping = load_broker_mapping(ROOT / "configs" / "csv_mappings" / "example_broker.toml")
    imported = parse_broker_csv(content, provenance, mapping)
    history = replay(imported.transactions, base=EUR, to_base=eur_only)
    prices = {
        FUND: PriceSeries(
            pd.Series([50.0, 55.0, 52.0, 54.0], index=pd.DatetimeIndex(DATES)), EUR, PriceType.PRICE
        )
    }
    valuation = value_portfolio(history, prices, eur_only, dates=DATES, max_price_age_days=0)
    fund = Instrument(
        isin=FUND,
        name="Example World Equity UCITS ETF",
        instrument_type=InstrumentType.ETF,
        asset_class=AssetClass.EQUITY,
        currency=EUR,
        as_of=date(2026, 1, 2),
        domicile="IE",
        replication=Replication.PHYSICAL_SAMPLING,
        distribution=Distribution.ACCUMULATING,
        ter=Decimal("0.0020"),
        benchmark="Example World Index",
        hedged_to=None,
        inception=None,
        fund_size=None,
        source="synthetic example",
    )
    report = build_portfolio_report(
        name="Synthetic example",
        history=history,
        valuation=valuation,
        prices=prices,
        to_base=eur_only,
        language=language,
        generated_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        flow_timing=FlowTiming.START_OF_DAY,
        max_price_age_days=0,
        fx_description="EUR only (no conversion)",
        provenance=[provenance],
        instruments={FUND: fund},
        import_notes=list(imported.notes),
        return_frequency=None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    return write_report(report, output, overwrite=True)


if __name__ == "__main__":
    target = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT / "results" / "portfolio_report_example.html"
    )
    lang = Language(sys.argv[2]) if len(sys.argv) > 2 else Language.IT
    print(main(target, lang))
