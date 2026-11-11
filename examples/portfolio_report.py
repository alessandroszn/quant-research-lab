"""Phase 2.3-2.5 example: an HTML report of the synthetic toy portfolio.

The report includes look-through and health checks.

Run with ``uv run python examples/portfolio_report.py [output.html] [it|en]``. The default
output is ``results/portfolio_report_example.html`` (git-ignored). Offline and deterministic;
all data are synthetic. Health-check thresholds come from ``configs/checks/example.toml``
(example values, not recommendations). The fund's holdings file and its NAV and index
series are synthetic too. The report is analytics, not investment advice.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from qrlab.checks import CheckContext, load_check_config, run_checks
from qrlab.core import Currency, Money
from qrlab.data import PriceType, Provenance
from qrlab.instruments import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Isin,
    Replication,
    load_holdings_mapping,
    parse_holdings_csv,
)
from qrlab.lookthrough import (
    LookThroughInputs,
    TrackingSeries,
    WeightTreatment,
    look_through,
)
from qrlab.portfolio import (
    FlowTiming,
    PriceSeries,
    external_flows_by_date,
    load_broker_mapping,
    parse_broker_csv,
    replay,
    time_weighted_returns,
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
HOLDINGS = """\
Synthetic World Equity UCITS ETF
Holdings as of 31/03/2026
Name,ISIN,Weight (%),Country Code,Sector,Currency,Asset Class
Example Corp A,US0000000119,40.0,US,Technology,USD,Equity
Example Corp B,US0000000127,25.0,US,Health Care,USD,Equity
Example Corp C,JP0000000133,20.0,JP,Industrials,JPY,Equity
Example Corp D,DE0000000140,14.0,DE,Financials,EUR,Equity

Synthetic file: the weights deliberately sum to 99 % to show the unexplained bucket.
"""
NAV = [50.0, 55.0, 52.0, 54.0]
INDEX = [1000.0, 1100.3, 1040.5, 1080.9]
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
    twr = time_weighted_returns(
        valuation, external_flows_by_date(history), flow_timing=FlowTiming.START_OF_DAY
    )
    context = CheckContext(
        as_of=DATES[-1],
        history=history,
        valuation=valuation,
        to_base=eur_only,
        instruments={FUND: fund},
        prices=prices,
        portfolio_returns=twr.returns,  # monthly, matching periods_per_year = 12
        benchmark_returns=None,
        target_weights={FUND.code: 0.6, "cash": 0.4},
        lookthrough=None,
    )
    holdings_content = HOLDINGS.encode("utf-8")
    holdings = parse_holdings_csv(
        holdings_content,
        Provenance(
            source="user",
            dataset="synthetic_holdings",
            url="file:holdings.csv",
            retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
            sha256=hashlib.sha256(holdings_content).hexdigest(),
            size_bytes=len(holdings_content),
            terms="synthetic example data",
        ),
        load_holdings_mapping(ROOT / "configs" / "csv_mappings" / "example_holdings.toml"),
        fund=FUND,
        as_of=date(2026, 3, 31),
        weight_basis="market value, % of NAV",
        sector_taxonomy="Synthetic sectors",
    )
    nav_index = pd.DatetimeIndex(DATES)
    lookthrough = LookThroughInputs(
        exposures=look_through(
            as_of=DATES[-1],
            position_weights=context.position_weights(),
            cash_weights=context.cash_weights(),
            instruments={FUND: fund},
            snapshots={FUND: holdings},
            treatment=WeightTreatment.AS_REPORTED,
            issuers=None,
        ),
        snapshots={FUND: holdings},
        tracking={
            FUND: (
                TrackingSeries(pd.Series(NAV, index=nav_index), PriceType.NAV, EUR, None),
                TrackingSeries(
                    pd.Series(INDEX, index=nav_index), PriceType.TOTAL_RETURN, EUR, None
                ),
            )
        },
    )
    context = replace(context, lookthrough=lookthrough)
    checks = run_checks(context, load_check_config(ROOT / "configs" / "checks" / "example.toml"))
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
        checks=checks,
        lookthrough=lookthrough,
        risk=None,
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
