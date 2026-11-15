"""Portfolio accounting and performance.

Transactions are replayed into positions, cash per currency and an average cost basis; the
ledger is valued in the base currency with dated prices and FX rates; performance is measured
as a **time-weighted return** (the investments) and a **money-weighted return** (the investor's
experience), always labelled and never mixed. See ``docs/design/2.1-portfolio.md``.

Modules:

- ``transactions``: :class:`Transaction` and :class:`TransactionKind`.
- ``ledger``: :func:`replay` into a :class:`LedgerHistory`.
- ``valuation``: :func:`value_portfolio`, :class:`PriceSeries`, :class:`EcbConverter`.
- ``performance``: TWR, MWR (XIRR), P&L decomposition, contribution, currency effect.
- ``broker_import``: broker exports through an explicit :class:`BrokerMapping`.
- ``native``: the native qrlab transactions file, read without a mapping (phase 8.8).
"""

from qrlab.portfolio.broker_import import (
    BrokerImport,
    BrokerMapping,
    load_broker_mapping,
    parse_broker_csv,
)
from qrlab.portfolio.ledger import (
    CashMovement,
    Cost,
    ExternalFlow,
    Income,
    LedgerHistory,
    LedgerState,
    Position,
    RealisedGain,
    ToBase,
    TradeCharge,
    TransferGain,
    check_transactions,
    replay,
)
from qrlab.portfolio.native import (
    NATIVE_COLUMNS,
    NATIVE_MAPPING,
    kind_columns,
    parse_native_csv,
    write_native_csv,
)
from qrlab.portfolio.performance import (
    CurrencyEffect,
    FlowTiming,
    PnlBreakdown,
    TwrResult,
    XirrResult,
    contribution_by_position,
    currency_effect,
    external_flows_by_date,
    money_weighted_return,
    pnl_breakdown,
    time_weighted_returns,
    xirr,
)
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.portfolio.valuation import EcbConverter, PriceSeries, Valuation, value_portfolio

__all__ = [
    "NATIVE_COLUMNS",
    "NATIVE_MAPPING",
    "BrokerImport",
    "BrokerMapping",
    "CashMovement",
    "Cost",
    "CurrencyEffect",
    "EcbConverter",
    "ExternalFlow",
    "FlowTiming",
    "Income",
    "LedgerHistory",
    "LedgerState",
    "PnlBreakdown",
    "Position",
    "PriceSeries",
    "RealisedGain",
    "ToBase",
    "TradeCharge",
    "Transaction",
    "TransactionKind",
    "TransferGain",
    "TwrResult",
    "Valuation",
    "XirrResult",
    "check_transactions",
    "contribution_by_position",
    "currency_effect",
    "external_flows_by_date",
    "kind_columns",
    "load_broker_mapping",
    "money_weighted_return",
    "parse_broker_csv",
    "parse_native_csv",
    "pnl_breakdown",
    "replay",
    "time_weighted_returns",
    "value_portfolio",
    "write_native_csv",
    "xirr",
]
