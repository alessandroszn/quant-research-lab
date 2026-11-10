"""European Central Bank data: euro reference FX rates, €STR and euro-area HICP.

Terms (checked 2026-11-10, ECB website disclaimer): free use of information taken from the site
if reproduced accurately with the ECB cited as source; modifications must be stated. The
reference rates are published for information purposes only.

Sources:

- FX: ``https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip``: one CSV, newest date
  first, one column per currency quoted as units of that currency per 1 EUR, ``N/A`` for
  missing values, a trailing comma on every line. Published around 16:00 CET on TARGET2 days.
- €STR and HICP: ECB Data Portal SDMX API in CSV format (one row per observation). The HICP
  series moved from the discontinued ``ICP`` dataset to ``HICP`` on 4 February 2026 (base
  2025 = 100).

Nothing is forward-filled. A missing rate stays missing; callers decide how stale a rate may be.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency, target2_calendar
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, FxRate
from qrlab.data.errors import DataNotFoundError, ParseError
from qrlab.data.fetch import Fetcher
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.store import RawStore, StoredFile, download

__all__ = [
    "ECB_SERIES",
    "FX_DATASET",
    "FX_URL",
    "SOURCE",
    "TERMS",
    "download_ecb_fx",
    "download_ecb_series",
    "ecb_series_url",
    "fx_rate",
    "parse_ecb_fx",
    "parse_estr",
    "parse_hicp",
]

SOURCE = "ecb"
TERMS = "ECB: free reuse if reproduced accurately with the ECB cited as source"
FX_DATASET = "eurofxref-hist"
FX_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
_API = "https://data-api.ecb.europa.eu/service/data/"
_CODE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class _Series:
    flow: str
    key: str
    column: str
    frequency: Frequency
    unit_field: str  # SDMX attribute that carries the unit
    unit_code: str  # expected value of that attribute
    scale: float  # multiplier applied to OBS_VALUE (0.01 converts percent to decimal)

    @property
    def full_key(self) -> str:
        return f"{self.flow}.{self.key}"


ECB_SERIES: Mapping[str, _Series] = MappingProxyType(
    {
        "estr": _Series(
            flow="EST",
            key="B.EU000A2X2A25.WT",
            column="ESTR",
            frequency=Frequency.DAILY,
            unit_field="UNIT_MEASURE",
            unit_code="PC",
            scale=0.01,
        ),
        "hicp_euro_area": _Series(
            flow="HICP",
            key="M.U2.N.000000.4D0.INX",
            column="HICP",
            frequency=Frequency.MONTHLY,
            unit_field="UNIT",
            unit_code="IX",
            scale=1.0,
        ),
    }
)
"""Supported Data Portal series, pinned to exact SDMX keys."""


# --------------------------------------------------------------------------- downloads
def ecb_series_url(name: str) -> str:
    """Return the Data Portal CSV URL of a supported series."""
    series = _series_spec(name)
    return f"{_API}{series.flow}/{series.key}?format=csvdata"


def download_ecb_fx(
    fetcher: Fetcher, store: RawStore, *, now: Callable[[], datetime]
) -> StoredFile:
    """Download the full history of euro reference rates into the raw store."""
    return download(
        fetcher, store, url=FX_URL, source=SOURCE, dataset=FX_DATASET, terms=TERMS, now=now
    )


def download_ecb_series(
    fetcher: Fetcher, store: RawStore, name: str, *, now: Callable[[], datetime]
) -> StoredFile:
    """Download a supported Data Portal series into the raw store."""
    return download(
        fetcher, store, url=ecb_series_url(name), source=SOURCE, dataset=name, terms=TERMS, now=now
    )


# --------------------------------------------------------------------------- FX
def parse_ecb_fx(content: bytes, provenance: Provenance) -> Dataset:
    """Parse ``eurofxref-hist.zip`` into a dataset of rates per 1 EUR, oldest date first.

    The file lists the newest date first; the parser checks that dates are strictly decreasing
    and then reverses them. Legacy currencies (e.g. CYP, EEK) are kept as published.
    """
    _require_source(provenance, FX_DATASET)
    lines = _single_member(content).splitlines()
    if not lines or not lines[0].startswith("Date,"):
        raise ParseError("FX file must start with a 'Date' header")
    header = _strip_trailing_empty(lines[0].split(","))
    currencies = header[1:]
    if not currencies:
        raise ParseError("FX file has no currency columns")
    for code in currencies:
        if not _CODE.match(code):
            raise ParseError(f"invalid currency code {code!r} in FX header")
    dates: list[pd.Timestamp] = []
    rows: list[list[float]] = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        parts = _strip_trailing_empty(line.split(","))
        if len(parts) != len(header):
            raise ParseError(f"line {number}: expected {len(header)} values, got {len(parts)}")
        dates.append(_parse_date(parts[0], "%Y-%m-%d", number))
        rows.append([_fx_value(v, number) for v in parts[1:]])
    if not rows:
        raise ParseError("FX file has no rows")
    index = pd.DatetimeIndex(dates)
    if not index.is_monotonic_decreasing or index.has_duplicates:
        raise ParseError("FX dates must be strictly decreasing, as published by the ECB")
    frame = pd.DataFrame(np.array(rows), index=index, columns=currencies).iloc[::-1]
    return Dataset(
        data=frame,
        provenance=provenance,
        frequency=Frequency.DAILY,
        unit=Unit.FX_RATE,
        return_kind=None,
        currency=Currency("EUR"),
        availability="Published by the ECB around 16:00 CET on the reference date (TARGET2 days).",
        notes=(
            "Each column is units of that currency per 1 EUR.",
            "N/A replaced by NaN; no forward fill.",
            "Rows reversed from the published newest-first order.",
        ),
        available_from=frame.index.to_series(),
    )


def fx_rate(dataset: Dataset, *, quote: Currency, on: date) -> FxRate:
    """Return the published EUR/``quote`` reference rate for one date as a core ``FxRate``.

    Raises
    ------
    DataNotFoundError
        If there is no fixing on ``on`` or the value is missing. Rates are never carried
        forward here; staleness policy belongs to the caller.
    """
    if quote.code not in dataset.data.columns:
        raise DataNotFoundError(f"no {quote.code} column in {dataset.provenance.dataset}")
    stamp = pd.Timestamp(on)
    if stamp not in dataset.data.index:
        raise DataNotFoundError(f"no ECB fixing on {on.isoformat()}")
    row = int(dataset.data.index.get_indexer(pd.DatetimeIndex([stamp]))[0])
    value = float(dataset.data[quote.code].to_numpy()[row])
    if np.isnan(value):
        raise DataNotFoundError(f"EUR/{quote.code} is missing on {on.isoformat()}")
    # repr() of a float is the shortest string that round-trips, i.e. the published digits.
    return FxRate(Currency("EUR"), quote, Decimal(repr(value)), on)


# --------------------------------------------------------------------------- Data Portal series
def parse_estr(content: bytes, provenance: Provenance) -> Dataset:
    """Parse the euro short-term rate (€STR) as an annual rate in decimals.

    The rate for business day *T* is published on the next TARGET2 business day around
    08:00 CET; ``available_from`` records that day.
    """
    spec = _series_spec("estr")
    _require_source(provenance, "estr")
    frame, status = _parse_sdmx(content, spec)
    last_year = int(frame.index[-1].year)
    calendar = target2_calendar(range(int(frame.index[0].year), last_year + 2))
    business_days = calendar.business_days(frame.index[0].date(), date(last_year + 1, 12, 31))
    positions = business_days.searchsorted(frame.index, side="right")
    available = pd.Series(business_days[positions], index=frame.index)
    return Dataset(
        data=frame,
        provenance=provenance,
        frequency=Frequency.DAILY,
        unit=Unit.RATE_PER_YEAR,
        return_kind=None,
        currency=Currency("EUR"),
        availability="Published around 08:00 CET on the next TARGET2 business day.",
        notes=(
            "Converted from percent per year to decimal (divided by 100).",
            "Day-count convention ACT/360; conversion to per-period returns is left to callers.",
        ),
        available_from=available,
        status=status,
    )


def parse_hicp(content: bytes, provenance: Provenance, *, publication_lag_days: int) -> Dataset:
    """Parse the euro-area HICP overall index (monthly, base 2025 = 100).

    Parameters
    ----------
    content, provenance
        Raw CSV bytes from the Data Portal and their provenance.
    publication_lag_days
        Days after the end of the reference month from which a value is treated as known.
        Required: final HICP is usually published around mid-month, flash estimates around
        month end. A conservative lag avoids look-ahead.
    """
    if type(publication_lag_days) is not int or publication_lag_days < 0:
        raise ValidationError(
            f"publication_lag_days must be a non-negative int, got {publication_lag_days!r}"
        )
    spec = _series_spec("hicp_euro_area")
    _require_source(provenance, "hicp_euro_area")
    frame, status = _parse_sdmx(content, spec)
    available = frame.index.to_series() + pd.Timedelta(days=publication_lag_days)
    base = _index_base(content)
    return Dataset(
        data=frame,
        provenance=provenance,
        frequency=Frequency.MONTHLY,
        unit=Unit.INDEX_LEVEL,
        return_kind=None,
        currency=None,
        availability=(
            f"Treated as known {publication_lag_days} days after the reference month end "
            "(caller's choice). Latest values may be flash estimates and are revised."
        ),
        notes=(
            f"Index base {base}.",
            "Status codes kept: A normal, E estimate (flash, subject to revision), Q missing.",
            "Reference months labelled by month end.",
        ),
        available_from=available,
        status=status,
    )


# --------------------------------------------------------------------------- helpers
_SDMX_REQUIRED = ("KEY", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "UNIT_MULT")


def _parse_sdmx(content: bytes, spec: _Series) -> tuple[pd.DataFrame, pd.Series]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    fields = reader.fieldnames or []
    missing = [f for f in (*_SDMX_REQUIRED, spec.unit_field) if f not in fields]
    if missing:
        raise ParseError(f"SDMX CSV lacks required columns {missing}")
    dates: list[pd.Timestamp] = []
    values: list[float] = []
    statuses: list[str] = []
    date_format = "%Y-%m-%d" if spec.frequency is Frequency.DAILY else "%Y-%m"
    for number, row in enumerate(reader, start=2):
        if row["KEY"] != spec.full_key:
            raise ParseError(f"line {number}: series key {row['KEY']!r} is not {spec.full_key}")
        if row[spec.unit_field] != spec.unit_code:
            raise ParseError(
                f"line {number}: unit {row[spec.unit_field]!r} is not {spec.unit_code!r}"
            )
        if row["UNIT_MULT"] != "0":
            raise ParseError(f"line {number}: UNIT_MULT {row['UNIT_MULT']!r} is not supported")
        stamp = _parse_date(row["TIME_PERIOD"], date_format, number)
        if spec.frequency is Frequency.MONTHLY:
            stamp = stamp + pd.offsets.MonthEnd(0)
        dates.append(stamp)
        statuses.append(row["OBS_STATUS"])
        values.append(_sdmx_value(row["OBS_VALUE"], row["OBS_STATUS"], number) * spec.scale)
    if not dates:
        raise ParseError("SDMX CSV has no rows")
    index = pd.DatetimeIndex(dates)
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ParseError("SDMX dates must be strictly increasing")
    frame = pd.DataFrame({spec.column: values}, index=index)
    return frame, pd.Series(statuses, index=index, dtype=object)


def _sdmx_value(text: str, status: str, line: int) -> float:
    if text == "":
        if status != "Q":
            raise ParseError(f"line {line}: empty value with status {status!r} (expected 'Q')")
        return float("nan")
    try:
        return float(text)
    except ValueError:
        raise ParseError(f"line {line}: {text!r} is not a number") from None


def _index_base(content: bytes) -> str:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    bases = {row.get("UNIT_INDEX_BASE") or "" for row in reader} - {""}
    return ", ".join(sorted(bases)) or "not stated"


def _fx_value(text: str, line: int) -> float:
    if text == "N/A":
        return float("nan")
    if text == "":
        raise ParseError(f"line {line}: empty FX value (the ECB uses 'N/A' for missing)")
    try:
        value = float(text)
    except ValueError:
        raise ParseError(f"line {line}: {text!r} is not a number") from None
    if value <= 0:
        raise ParseError(f"line {line}: FX rate must be positive, got {value}")
    return value


def _parse_date(text: str, fmt: str, line: int) -> pd.Timestamp:
    try:
        return pd.Timestamp(datetime.strptime(text, fmt))
    except ValueError:
        raise ParseError(f"line {line}: invalid date {text!r}") from None


def _strip_trailing_empty(parts: list[str]) -> list[str]:
    return parts[:-1] if parts and parts[-1] == "" else parts


def _single_member(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) != 1:
                raise ParseError(f"zip must contain exactly one file, found {names}")
            return archive.read(names[0]).decode("utf-8")
    except zipfile.BadZipFile as exc:
        raise ParseError("content is not a valid zip file") from exc


def _series_spec(name: str) -> _Series:
    try:
        return ECB_SERIES[name]
    except KeyError:
        raise ParseError(f"unknown ECB series {name!r}") from None


def _require_source(provenance: Provenance, dataset: str) -> None:
    if provenance.source != SOURCE or provenance.dataset != dataset:
        raise ParseError(
            f"expected provenance {SOURCE}/{dataset}, got {provenance.source}/{provenance.dataset}"
        )
