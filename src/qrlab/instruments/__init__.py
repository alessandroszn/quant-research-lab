"""Instrument master data and fund holdings snapshots.

Identifiers are validated (ISIN check digits, ISO country codes); unknown values are ``None``
rather than defaults; incomplete or stale records produce explicit :class:`Issue` findings
instead of being filled in; holdings weights are never rescaled silently.

Modules:

- ``identifiers``: :class:`Isin` and ISO 3166-1 alpha-2 country codes.
- ``master``: :class:`Instrument` master data and :func:`master_data_issues`.
- ``holdings``: :class:`HoldingsSnapshot`, :func:`holdings_issues`, :func:`normalised_weights`.
- ``io``: loading master data (TOML) and holdings (CSV with an explicit mapping).

Layering: ``instruments`` may import ``core`` and ``data`` (documented exception).
"""

from qrlab.instruments.holdings import (
    HOLDING_COLUMNS,
    HoldingsSnapshot,
    holdings_issues,
    normalised_weights,
)
from qrlab.instruments.identifiers import COUNTRIES, Isin, is_valid_isin, validate_country
from qrlab.instruments.io import (
    HoldingsCsvMapping,
    WeightUnit,
    load_holdings_mapping,
    load_instruments,
    parse_holdings_csv,
)
from qrlab.instruments.master import (
    FUND_TYPES,
    MAX_TER,
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Issue,
    IssueKind,
    Replication,
    master_data_issues,
)

__all__ = [
    "COUNTRIES",
    "FUND_TYPES",
    "HOLDING_COLUMNS",
    "MAX_TER",
    "AssetClass",
    "Distribution",
    "HoldingsCsvMapping",
    "HoldingsSnapshot",
    "Instrument",
    "InstrumentType",
    "Isin",
    "Issue",
    "IssueKind",
    "Replication",
    "WeightUnit",
    "holdings_issues",
    "is_valid_isin",
    "load_holdings_mapping",
    "load_instruments",
    "master_data_issues",
    "normalised_weights",
    "parse_holdings_csv",
    "validate_country",
]
