"""Open Source Asset Pricing (Chen and Zimmermann): predictor long-short returns and documentation.

Source: https://www.openassetpricing.com, files on Hugging Face (``OpenSourceAP/CrossSection``),
pinned to one revision so that a download is reproducible.

Terms (checked 2026-11-12): the dataset is licensed CC BY 4.0 and asks users to cite Chen and
Zimmermann (2022, *Critical Finance Review*). Only portfolio returns and documentation are used;
the firm-level files (derived from CRSP and Compustat) are not downloaded. Raw files stay in the
git-ignored raw store and are never redistributed.

Files:

- ``long_short_returns``: ``Portfolios/Full Sets OP/PredictorLSretWide.parquet``, monthly
  long-short returns in percent, one column per predictor, signed as in the original paper
  (original-paper construction). Reading Parquet needs the optional ``pyarrow`` dependency
  (``qrlab[parquet]``).
- ``signal_doc``: ``SignalDoc.csv``, one row per signal with its category, the original paper's
  publication year and sample years, and its sign.

Parsing is strict: missing columns, duplicated names, unknown categories or malformed dates raise
:class:`~qrlab.data.errors.ParseError`.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from urllib.parse import quote

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
    "OSAP_FILES",
    "REVISION",
    "SIGNAL_DOC_COLUMNS",
    "SOURCE",
    "TERMS",
    "download_osap",
    "osap_url",
    "parse_long_short_returns",
    "parse_signal_doc",
]

SOURCE = "osap"
TERMS = (
    "Open Source Asset Pricing (Chen and Zimmermann): CC BY 4.0; cite Chen and Zimmermann "
    "(2022, Critical Finance Review); do not redistribute raw files"
)
REVISION = "ad1dfba5a6d80c4ce53ce6b8127f5a949dda1e40"
"""Hugging Face revision of release 2026.10."""

OSAP_FILES: Mapping[str, str] = MappingProxyType(
    {
        "long_short_returns": "Portfolios/Full Sets OP/PredictorLSretWide.parquet",
        "signal_doc": "SignalDoc.csv",
    }
)
"""Dataset name -> path in the Hugging Face repository."""

SIGNAL_DOC_COLUMNS = (
    "Acronym",
    "Cat.Signal",
    "Predictability in OP",
    "Authors",
    "Year",
    "Journal",
    "LongDescription",
    "Cat.Data",
    "SampleStartYear",
    "SampleEndYear",
    "Sign",
)
"""Columns of ``SignalDoc.csv`` that are required and kept."""

_BASE_URL = "https://huggingface.co/datasets/OpenSourceAP/CrossSection/resolve/"
_SIGNAL_CATEGORIES = frozenset({"Predictor", "Placebo"})
_PREDICTABILITY = re.compile(r"^\d+_[a-z]+$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")


def osap_url(dataset: str, *, revision: str) -> str:
    """Return the download URL of a dataset at a pinned revision (40-hex commit)."""
    if dataset not in OSAP_FILES:
        raise ParseError(f"unknown OSAP dataset {dataset!r}; known: {sorted(OSAP_FILES)}")
    if not _REVISION.match(revision):
        raise ParseError(f"revision must be a 40-character commit hash, got {revision!r}")
    return f"{_BASE_URL}{revision}/{quote(OSAP_FILES[dataset])}"


def download_osap(
    fetcher: Fetcher,
    store: RawStore,
    dataset: str,
    *,
    revision: str,
    now: Callable[[], datetime],
) -> StoredFile:
    """Download a dataset into the raw store (deduplicated by hash)."""
    return download(
        fetcher,
        store,
        url=osap_url(dataset, revision=revision),
        source=SOURCE,
        dataset=dataset,
        terms=TERMS,
        now=now,
    )


def parse_signal_doc(content: bytes, provenance: Provenance) -> pd.DataFrame:
    """Parse ``SignalDoc.csv`` into a frame indexed by acronym with :data:`SIGNAL_DOC_COLUMNS`.

    Predictors must have integer publication and sample years with start <= end; placebos may
    lack them (NaN).
    """
    _check(provenance, "signal_doc")
    try:
        frame = pd.read_csv(io.BytesIO(content), encoding="utf-8")
    except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ParseError(f"SignalDoc is not a readable UTF-8 CSV: {exc}") from exc
    missing = [c for c in SIGNAL_DOC_COLUMNS if c not in frame.columns]
    if missing:
        raise ParseError(f"SignalDoc is missing columns {missing}")
    frame = frame.loc[:, list(SIGNAL_DOC_COLUMNS)]
    names = frame["Acronym"]
    if names.isna().any() or (names.astype(str).str.strip() == "").any():
        raise ParseError("SignalDoc has rows without an acronym")
    if names.duplicated().any():
        raise ParseError(f"duplicated acronyms {sorted(set(names[names.duplicated()]))}")
    categories = set(frame["Cat.Signal"].dropna())
    if frame["Cat.Signal"].isna().any() or not categories <= _SIGNAL_CATEGORIES:
        found = sorted(map(str, categories))
        raise ParseError(f"Cat.Signal must be one of {sorted(_SIGNAL_CATEGORIES)}, got {found}")
    levels = frame["Predictability in OP"].dropna().astype(str)
    bad = sorted({v for v in levels if not _PREDICTABILITY.match(v)})
    if bad:
        raise ParseError(f"unexpected 'Predictability in OP' values {bad}")
    if frame["Sign"].isna().any() or not frame["Sign"].isin([1.0, -1.0]).all():
        raise ParseError("Sign must be 1 or -1 for every signal")
    predictors = frame[frame["Cat.Signal"] == "Predictor"]
    years = predictors[["Year", "SampleStartYear", "SampleEndYear"]]
    values = years.to_numpy(dtype=np.float64)
    if np.isnan(values).any() or (values != np.round(values)).any():
        raise ParseError("predictors need whole publication and sample years")
    if (predictors["SampleStartYear"] > predictors["SampleEndYear"]).any():
        raise ParseError("a predictor's SampleStartYear is after its SampleEndYear")
    out = frame.set_index("Acronym")
    out.index = out.index.astype(str)
    for column in ("Year", "SampleStartYear", "SampleEndYear"):
        out[column] = out[column].astype("Float64")
    return out


def parse_long_short_returns(content: bytes, provenance: Provenance) -> Dataset:
    """Parse ``PredictorLSretWide.parquet`` into monthly long-short returns in decimals."""
    _check(provenance, "long_short_returns")
    try:
        raw = pd.read_parquet(io.BytesIO(content))
    except ImportError as exc:
        raise ParseError(
            "reading Parquet needs pyarrow: install the optional extra qrlab[parquet]"
        ) from exc
    except Exception as exc:  # pyarrow raises its own error types for corrupt files
        raise ParseError(f"long-short returns are not a readable Parquet file: {exc}") from exc
    if "date" not in raw.columns:
        raise ParseError("long-short returns need a 'date' column")
    columns = [str(c) for c in raw.columns if c != "date"]
    if not columns or len(set(columns)) != len(columns):
        raise ParseError("long-short returns need unique predictor columns")
    try:
        dates = pd.to_datetime(raw["date"], errors="raise")
    except (ValueError, TypeError) as exc:
        raise ParseError(f"invalid dates in long-short returns: {exc}") from exc
    index = pd.DatetimeIndex(dates).normalize() + pd.offsets.MonthEnd(0)
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ParseError("long-short return months are not increasing and unique")
    try:
        values = raw[columns].to_numpy(dtype=np.float64)
    except (ValueError, TypeError) as exc:
        raise ParseError(f"non-numeric long-short returns: {exc}") from exc
    frame = pd.DataFrame(
        values / 100.0, index=pd.DatetimeIndex(index, name="month"), columns=columns
    )
    return Dataset(
        data=frame,
        provenance=provenance,
        frequency=Frequency.MONTHLY,
        unit=Unit.RETURN,
        return_kind=ReturnKind.SIMPLE,
        currency=Currency("USD"),
        availability=(
            "Released yearly and revised between releases; the provenance records the pinned "
            "revision and download time."
        ),
        notes=(
            "Converted from percent to decimal (divided by 100).",
            "Long-short returns signed as in the original papers (original-paper construction).",
            "Gross paper-portfolio returns: no trading costs.",
        ),
    )


def _check(provenance: Provenance, dataset: str) -> None:
    if provenance.source != SOURCE or provenance.dataset != dataset:
        raise ParseError(
            f"provenance must be {SOURCE}/{dataset}, got {provenance.source}/{provenance.dataset}"
        )
