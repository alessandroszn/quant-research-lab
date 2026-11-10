"""The toy-portfolio report used by the reporting tests (all data synthetic)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

from qrlab.data.provenance import Provenance
from qrlab.instruments.master import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Replication,
)
from qrlab.portfolio.performance import FlowTiming
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import Report
from qrlab.reporting.portfolio_report import build_portfolio_report
from support.portfolio import D0, D1, D2, D3, EUR, X, eur_only, price_series, toy_setup

GENERATED = datetime(2026, 4, 1, 9, 30, tzinfo=UTC)
PROVENANCE = Provenance(
    source="user",
    dataset="synthetic_broker_export",
    url="file:movimenti.csv",
    retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
    sha256=hashlib.sha256(b"synthetic").hexdigest(),
    size_bytes=9,
    terms="synthetic",
)


def toy_instrument(name: str = "Example World Equity UCITS ETF") -> Instrument:
    """Return the master record of the toy fund."""
    return Instrument(
        isin=X,
        name=name,
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
        source="synthetic",
    )


def toy_report(language: Language = Language.IT, **changes: object) -> Report:
    """Build the toy report, with ``changes`` replacing any input."""
    history, valuation = toy_setup()
    kwargs: dict[str, object] = {
        "name": "Toy portfolio",
        "history": history,
        "valuation": valuation,
        "prices": {X: price_series({D0: 50.0, D1: 55.0, D2: 52.0, D3: 54.0})},
        "to_base": eur_only,
        "language": language,
        "generated_at": GENERATED,
        "flow_timing": FlowTiming.START_OF_DAY,
        "max_price_age_days": 0,
        "fx_description": "EUR only (no conversion)",
        "provenance": [PROVENANCE],
        "instruments": {X: toy_instrument()},
        "import_notes": ["File listed newest first; rows reversed as a whole."],
        "return_frequency": None,
        "checks": None,
    }
    kwargs.update(changes)
    return build_portfolio_report(**kwargs)  # type: ignore[arg-type]
