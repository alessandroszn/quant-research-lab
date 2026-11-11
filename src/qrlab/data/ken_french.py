"""Kenneth R. French Data Library: factor returns.

Source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html

Terms (checked 2026-11-10): the library publishes no licence, only a copyright notice for
Eugene F. Fama and Kenneth R. French. It is used for local research with citation; raw files are
never committed or redistributed.

File format: free text, then sections. A section starts with a header line beginning with a
comma (``,Mkt-RF,SMB,HML,RF``) and continues with ``date, value, ...`` rows until a blank line.
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


_FF3 = ("Mkt-RF", "SMB", "HML", "RF")
_FF5 = ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF")
_MONTHLY_ANNUAL = frozenset({Frequency.MONTHLY, Frequency.ANNUAL})
_DAILY = frozenset({Frequency.DAILY})

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


def parse_ken_french(content: bytes, provenance: Provenance, *, frequency: Frequency) -> Dataset:
    """Parse one section of a Ken French zip file into a :class:`Dataset` of decimal returns.

    Parameters
    ----------
    content
        Raw bytes of the downloaded zip file.
    provenance
        Provenance of ``content``; its dataset selects the expected columns.
    frequency
        Section to parse: ``DAILY`` for daily files, ``MONTHLY`` or ``ANNUAL`` for the others.

    Returns
    -------
    Dataset
        Simple returns in decimals (percent divided by 100), USD, missing codes as NaN.
    """
    if provenance.source != SOURCE:
        raise ParseError(f"provenance source must be {SOURCE!r}, got {provenance.source!r}")
    spec = _spec(provenance.dataset)
    if frequency not in spec.frequencies:
        available = sorted(f.name.lower() for f in spec.frequencies)
        raise ParseError(f"{provenance.dataset} has {available} data, not {frequency.name}")
    text = _single_member(content)
    sections = _sections(text)
    matching = [s for s in sections if s.date_length == _DATE_LENGTH[frequency]]
    if len(matching) != 1:
        raise ParseError(
            f"expected one {frequency.name} section in {provenance.dataset}, found {len(matching)}"
        )
    section = matching[0]
    if section.columns != spec.columns:
        raise ParseError(f"unexpected columns {section.columns}, expected {spec.columns}")
    frame = _to_frame(section, frequency)

    notes = [
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


# --------------------------------------------------------------------------- parsing helpers
@dataclass(frozen=True)
class _Section:
    columns: tuple[str, ...]
    dates: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    first_line: int

    @property
    def date_length(self) -> int:
        return len(self.dates[0])


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
            sections.append(_Section(columns, tuple(dates), tuple(rows), i + 1))
            i = j
            continue
        if _DATA_ROW.match(line):
            raise ParseError(f"line {i + 1}: data row outside a section")
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
    return pd.DataFrame(values / 100.0, index=index, columns=list(section.columns))


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
