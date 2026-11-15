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

from qrlab.instruments.countries import COUNTRY_ALIASES, COUNTRY_NAMES, country_code
from qrlab.instruments.holdings import (
    HOLDING_COLUMNS,
    HoldingsSnapshot,
    holdings_issues,
    normalised_weights,
)
from qrlab.instruments.identifiers import COUNTRIES, Isin, is_valid_isin, validate_country
from qrlab.instruments.io import (
    INSTRUMENT_FIELDS,
    CountryFormat,
    HoldingsCsvMapping,
    HoldingsFileFormat,
    WeightUnit,
    instrument_fields,
    instrument_from_fields,
    load_holdings_mapping,
    load_instruments,
    load_issuer_map,
    parse_holdings_csv,
    parse_holdings_file,
    write_instruments_toml,
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
    "COUNTRY_ALIASES",
    "COUNTRY_NAMES",
    "FUND_TYPES",
    "HOLDING_COLUMNS",
    "INSTRUMENT_FIELDS",
    "MAX_TER",
    "AssetClass",
    "CountryFormat",
    "Distribution",
    "HoldingsCsvMapping",
    "HoldingsFileFormat",
    "HoldingsSnapshot",
    "Instrument",
    "InstrumentType",
    "Isin",
    "Issue",
    "IssueKind",
    "Replication",
    "WeightUnit",
    "country_code",
    "holdings_issues",
    "instrument_fields",
    "instrument_from_fields",
    "is_valid_isin",
    "load_holdings_mapping",
    "load_instruments",
    "load_issuer_map",
    "master_data_issues",
    "normalised_weights",
    "parse_holdings_csv",
    "parse_holdings_file",
    "validate_country",
    "write_instruments_toml",
]
