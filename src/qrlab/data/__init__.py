"""Data access, provenance and point-in-time handling.

Invariants: raw source data is stored byte-for-byte, read-only and never overwritten; every
dataset records where it came from (:class:`Provenance`) and, where known, when each value
became available; units, currency and total- vs. price-return treatment are declared, never
implied; parsers are strict and never guess formats.

Modules:

- ``store``, ``provenance``, ``fetch``: raw store with vintages, provenance records, the
  :class:`Dataset` container and an HTTPS fetcher.
- ``ken_french``: Fama-French and momentum factors.
- ``ecb``: euro reference FX rates, €STR and euro-area HICP.
- ``user_csv``: user price files read through explicit mappings.

Downloading (network) and parsing (pure functions of bytes) are always separate.
"""

from qrlab.data.ecb import (
    ECB_SERIES,
    download_ecb_fx,
    download_ecb_series,
    fx_rate,
    parse_ecb_fx,
    parse_estr,
    parse_hicp,
)
from qrlab.data.errors import DataNotFoundError, FetchError, IntegrityError, ParseError
from qrlab.data.fetch import Fetcher, UrlFetcher
from qrlab.data.ken_french import KEN_FRENCH_DATASETS, download_ken_french, parse_ken_french
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.store import RawStore, StoredFile, download
from qrlab.data.user_csv import (
    ColumnSpec,
    CsvMapping,
    PriceData,
    PriceType,
    import_local_file,
    load_csv_mapping,
    parse_price_csv,
)

__all__ = [
    "ECB_SERIES",
    "KEN_FRENCH_DATASETS",
    "ColumnSpec",
    "CsvMapping",
    "DataNotFoundError",
    "Dataset",
    "FetchError",
    "Fetcher",
    "IntegrityError",
    "ParseError",
    "PriceData",
    "PriceType",
    "Provenance",
    "RawStore",
    "StoredFile",
    "Unit",
    "UrlFetcher",
    "download",
    "download_ecb_fx",
    "download_ecb_series",
    "download_ken_french",
    "fx_rate",
    "import_local_file",
    "load_csv_mapping",
    "parse_ecb_fx",
    "parse_estr",
    "parse_hicp",
    "parse_ken_french",
    "parse_price_csv",
]
