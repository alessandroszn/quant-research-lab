"""Kenneth R. French Data Library: factor returns.

Source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html

Terms (checked 2026-11-10): the library publishes no licence, only a copyright notice for
Eugene F. Fama and Kenneth R. French. It is used for local research with citation; raw files are
never committed or redistributed.

File format: free text, then sections. A section starts with a header line beginning with a
comma (``,Mkt-RF,SMB,HML,RF``) and continues with ``date, value, ...`` rows until a blank line.
The non-blank line before the header is the section's title. Portfolio files hold several
sections of the same frequency (value- and equal-weighted returns, number of firms, average firm
size); for them the section is selected by its exact title.
Dates are ``YYYYMMDD`` (daily), ``YYYYMM`` (monthly) or ``YYYY`` (annual). Values are percent;
missing values are coded ``-99.99`` or ``-999``.

Parsing is strict: unexpected columns, malformed rows, invalid or unsorted dates raise
:class:`~qrlab.data.errors.ParseError`. A changed format must never produce wrong numbers.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.money import Currency
from qrlab.core.returns import ReturnKind
from qrlab.data.errors import ParseError
from qrlab.data.fetch import Fetcher
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.store import RawStore, StoredFile, download

__all__ = [
    "KEN_FRENCH_DATASETS",
    "SOURCE",
    "TERMS",
    "download_ken_french",
    "ken_french_url",
    "parse_ken_french",
    "parse_ken_french_table",
]

SOURCE = "ken_french"
TERMS = (
    "Kenneth R. French Data Library; copyright Eugene F. Fama and Kenneth R. French; "
    "no licence published; local research use with citation; do not redistribute raw files"
)
_BASE_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
_MISSING_CODES = (-99.99, -999.0)
_DATA_ROW = re.compile(r"^\s*\d+\s*,")


@dataclass(frozen=True)
class _Spec:
    columns: tuple[str, ...]
    frequencies: frozenset[Frequency]
    # Titled files: the return sections and the other (non-return) sections that can be read.
    return_sections: frozenset[str] = frozenset()
    table_sections: frozenset[str] = frozenset()


_FF3 = ("Mkt-RF", "SMB", "HML", "RF")
_FF5 = ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF")
_MONTHLY_ANNUAL = frozenset({Frequency.MONTHLY, Frequency.ANNUAL})
_DAILY = frozenset({Frequency.DAILY})
_MONTHLY = frozenset({Frequency.MONTHLY})
_INDUSTRIES_10 = (
    "NoDur",
    "Durbl",
    "Manuf",
    "Enrgy",
    "HiTec",
    "Telcm",
    "Shops",
    "Hlth",
    "Utils",
    "Other",
)
_SIZE_NAMES = {1: "SMALL", 5: "BIG"}
_BM_NAMES = {1: "LoBM", 5: "HiBM"}
_SIZE_BM_25 = tuple(
    f"{_SIZE_NAMES[size]} {_BM_NAMES[bm]}"
    if size in _SIZE_NAMES and bm in _BM_NAMES
    else f"ME{size} BM{bm}"
    for size in range(1, 6)
    for bm in range(1, 6)
)
VALUE_WEIGHTED_MONTHLY = "Average Value Weighted Returns -- Monthly"
EQUAL_WEIGHTED_MONTHLY = "Average Equal Weighted Returns -- Monthly"
VALUE_WEIGHTED_DAILY = "Average Value Weighted Returns -- Daily"
EQUAL_WEIGHTED_DAILY = "Average Equal Weighted Returns -- Daily"
NUMBER_OF_FIRMS = "Number of Firms in Portfolios"
AVERAGE_FIRM_SIZE = "Average Firm Size"
AVERAGE_MARKET_CAP = "Average Market Cap"  # the size section of the 25 size/BM file
_MONTHLY_RETURNS = frozenset({VALUE_WEIGHTED_MONTHLY, EQUAL_WEIGHTED_MONTHLY})
_DAILY_RETURNS = frozenset({VALUE_WEIGHTED_DAILY, EQUAL_WEIGHTED_DAILY})
_FIRM_TABLES = frozenset({NUMBER_OF_FIRMS, AVERAGE_FIRM_SIZE})
_MARKET_CAP_TABLES = frozenset({NUMBER_OF_FIRMS, AVERAGE_MARKET_CAP})

KEN_FRENCH_DATASETS: Mapping[str, _Spec] = MappingProxyType(
    {
        "F-F_Research_Data_Factors": _Spec(_FF3, _MONTHLY_ANNUAL),
        "F-F_Research_Data_Factors_daily": _Spec(_FF3, _DAILY),
        "F-F_Research_Data_5_Factors_2x3": _Spec(_FF5, _MONTHLY_ANNUAL),
        "F-F_Research_Data_5_Factors_2x3_daily": _Spec(_FF5, _DAILY),
        "F-F_Momentum_Factor": _Spec(("Mom",), _MONTHLY_ANNUAL),
        "F-F_Momentum_Factor_daily": _Spec(("Mom",), _DAILY),
        # International factors (Bloomberg data, USD), monthly and annual sections.
        "Developed_3_Factors": _Spec(_FF3, _MONTHLY_ANNUAL),
        "Developed_5_Factors": _Spec(_FF5, _MONTHLY_ANNUAL),
        "Developed_Mom_Factor": _Spec(("WML",), _MONTHLY_ANNUAL),
        "Europe_3_Factors": _Spec(_FF3, _MONTHLY_ANNUAL),
        "Europe_5_Factors": _Spec(_FF5, _MONTHLY_ANNUAL),
        "Europe_Mom_Factor": _Spec(("WML",), _MONTHLY_ANNUAL),
        # Portfolio files (titled sections). Monthly files also carry firm counts and sizes.
        "10_Industry_Portfolios": _Spec(_INDUSTRIES_10, _MONTHLY, _MONTHLY_RETURNS, _FIRM_TABLES),
        "10_Industry_Portfolios_daily": _Spec(_INDUSTRIES_10, _DAILY, _DAILY_RETURNS),
        "25_Portfolios_5x5": _Spec(_SIZE_BM_25, _MONTHLY, _MONTHLY_RETURNS, _MARKET_CAP_TABLES),
        "25_Portfolios_5x5_Daily": _Spec(_SIZE_BM_25, _DAILY, _DAILY_RETURNS),
    }
)
"""Supported datasets: expected columns and available frequencies."""

_DATE_LENGTH = {Frequency.DAILY: 8, Frequency.MONTHLY: 6, Frequency.ANNUAL: 4}


def ken_french_url(dataset: str) -> str:
    """Return the download URL of a supported dataset."""
    _spec(dataset)
    return f"{_BASE_URL}{dataset}_CSV.zip"


def download_ken_french(
    fetcher: Fetcher, store: RawStore, dataset: str, *, now: Callable[[], datetime]
) -> StoredFile:
    """Download a dataset's zip file into the raw store (deduplicated by hash)."""
    return download(
        fetcher,
        store,
        url=ken_french_url(dataset),
        source=SOURCE,
        dataset=dataset,
        terms=TERMS,
        now=now,
    )


def parse_ken_french(
    content: bytes, provenance: Provenance, *, frequency: Frequency, section: str | None = None
) -> Dataset:
    """Parse one section of a Ken French zip file into a :class:`Dataset` of decimal returns.

    Parameters
    ----------
    content
        Raw bytes of the downloaded zip file.
    provenance
        Provenance of ``content``; its dataset selects the expected columns.
    frequency
        Section to parse: ``DAILY`` for daily files, ``MONTHLY`` or ``ANNUAL`` for the others.
    section
        Title of the return section, required for portfolio files (e.g.
        :data:`VALUE_WEIGHTED_MONTHLY`) and forbidden for factor files.

    Returns
    -------
    Dataset
        Simple returns in decimals (percent divided by 100), USD, missing codes as NaN.
    """
    spec = _checked_spec(provenance, frequency)
    if spec.return_sections and section not in spec.return_sections:
        raise ParseError(
            f"{provenance.dataset}: section must be one of {sorted(spec.return_sections)}, "
            f"got {section!r}"
        )
    if not spec.return_sections and section is not None:
        raise ParseError(f"{provenance.dataset} has no titled sections; do not pass a section")
    found = _select(content, provenance.dataset, spec, frequency, section)
    frame = _to_frame(found, frequency) / 100.0

    notes = [
        *([f"Section: {section}."] if section else []),
        "Converted from percent to decimal (divided by 100).",
        "Missing-value codes -99.99 and -999 replaced by NaN.",
    ]
    if "RF" in spec.columns:
        notes.append("Mkt-RF is an excess return over RF; RF is the one-month T-bill return.")
    if "Mom" in spec.columns or "WML" in spec.columns:
        notes.append("Momentum (Mom or WML) is a long-short (zero-cost) factor return.")
    return Dataset(
        data=frame,
        provenance=provenance,
        frequency=frequency,
        unit=Unit.RETURN,
        return_kind=ReturnKind.SIMPLE,
        currency=Currency("USD"),
        availability=(
            "Updated irregularly and revised between vintages; the download time in the "
            "provenance is the only availability information."
        ),
        notes=tuple(notes),
    )


def parse_ken_french_table(
    content: bytes, provenance: Provenance, *, frequency: Frequency, section: str
) -> pd.DataFrame:
    """Parse a non-return section of a portfolio file, with values as published.

    ``Number of Firms in Portfolios`` is a count; ``Average Firm Size`` (industry files) and
    ``Average Market Cap`` (25 size/BM file) are in millions of USD.
    Missing-value codes become NaN; nothing is rescaled.
    """
    spec = _checked_spec(provenance, frequency)
    if section not in spec.table_sections:
        raise ParseError(
            f"{provenance.dataset}: table section must be one of {sorted(spec.table_sections)}, "
            f"got {section!r}"
        )
    return _to_frame(_select(content, provenance.dataset, spec, frequency, section), frequency)


# --------------------------------------------------------------------------- parsing helpers
@dataclass(frozen=True)
class _Section:
    title: str
    columns: tuple[str, ...]
    dates: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    first_line: int

    @property
    def date_length(self) -> int:
        return len(self.dates[0])


def _checked_spec(provenance: Provenance, frequency: Frequency) -> _Spec:
    if provenance.source != SOURCE:
        raise ParseError(f"provenance source must be {SOURCE!r}, got {provenance.source!r}")
    spec = _spec(provenance.dataset)
    if frequency not in spec.frequencies:
        available = sorted(f.name.lower() for f in spec.frequencies)
        raise ParseError(f"{provenance.dataset} has {available} data, not {frequency.name}")
    return spec


def _select(
    content: bytes, dataset: str, spec: _Spec, frequency: Frequency, title: str | None
) -> _Section:
    sections = _sections(_single_member(content))
    matching = [
        s
        for s in sections
        if s.date_length == _DATE_LENGTH[frequency] and (title is None or s.title == title)
    ]
    if len(matching) != 1:
        what = f"{frequency.name} section" + (f" titled {title!r}" if title else "")
        raise ParseError(f"expected one {what} in {dataset}, found {len(matching)}")
    found = matching[0]
    if found.columns != spec.columns:
        raise ParseError(f"unexpected columns {found.columns}, expected {spec.columns}")
    return found


def _spec(dataset: str) -> _Spec:
    try:
        return KEN_FRENCH_DATASETS[dataset]
    except KeyError:
        raise ParseError(f"unknown Ken French dataset {dataset!r}") from None


def _single_member(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) != 1:
                raise ParseError(f"zip must contain exactly one file, found {names}")
            raw = archive.read(names[0])
    except zipfile.BadZipFile as exc:
        raise ParseError("content is not a valid zip file") from exc
    # The library's files are plain ASCII; latin-1 maps every byte, so decoding cannot fail
    # and any unexpected character surfaces as a parse error below rather than here.
    return raw.decode("latin-1")


def _sections(text: str) -> list[_Section]:
    lines = text.splitlines()
    sections: list[_Section] = []
    title = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(","):
            columns = tuple(c.strip() for c in line.split(",")[1:])
            dates: list[str] = []
            rows: list[tuple[str, ...]] = []
            j = i + 1
            while j < len(lines) and lines[j].strip():
                parts = [p.strip() for p in lines[j].split(",")]
                if len(parts) != len(columns) + 1:
                    raise ParseError(
                        f"line {j + 1}: expected {len(columns) + 1} values, got {len(parts)}"
                    )
                dates.append(parts[0])
                rows.append(tuple(parts[1:]))
                j += 1
            if not rows:
                raise ParseError(f"section at line {i + 1} has no rows")
            sections.append(_Section(title, columns, tuple(dates), tuple(rows), i + 1))
            title = ""
            i = j
            continue
        if _DATA_ROW.match(line):
            raise ParseError(f"line {i + 1}: data row outside a section")
        if line.strip():
            title = " ".join(line.split())
        i += 1
    return sections


def _to_frame(section: _Section, frequency: Frequency) -> pd.DataFrame:
    index = pd.DatetimeIndex([_parse_date(d, frequency) for d in section.dates])
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ParseError(f"dates in section at line {section.first_line} are not increasing")
    try:
        values = np.array([[float(v) for v in row] for row in section.rows], dtype=np.float64)
    except ValueError as exc:
        raise ParseError(f"section at line {section.first_line}: not a number ({exc})") from exc
    values[np.isin(values, _MISSING_CODES)] = np.nan
    return pd.DataFrame(values, index=index, columns=list(section.columns))


def _parse_date(text: str, frequency: Frequency) -> pd.Timestamp:
    expected = _DATE_LENGTH[frequency]
    if len(text) != expected or not text.isdigit():
        raise ParseError(f"invalid {frequency.name} date {text!r}")
    try:
        if frequency is Frequency.DAILY:
            return pd.Timestamp(datetime.strptime(text, "%Y%m%d"))
        if frequency is Frequency.MONTHLY:
            return pd.Timestamp(datetime.strptime(text, "%Y%m")) + pd.offsets.MonthEnd(0)
        return pd.Timestamp(year=int(text), month=12, day=31)
    except ValueError as exc:
        raise ParseError(f"invalid {frequency.name} date {text!r}") from exc
