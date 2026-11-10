"""Provenance records and the documented :class:`Dataset` container."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy, validate_frame

__all__ = ["Dataset", "Provenance", "Unit"]

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Provenance:
    """Where a raw file came from and how to verify it.

    Parameters
    ----------
    source
        Identifier of the data source, e.g. ``"ken_french"``. A safe path component.
    dataset
        Identifier of the dataset within the source. A safe path component.
    url
        HTTPS URL the bytes were downloaded from.
    retrieved_at
        Time of download, timezone-aware and in UTC.
    sha256
        Lower-case hexadecimal SHA-256 of the raw bytes.
    size_bytes
        Size of the raw bytes.
    terms
        Short note on the source's terms of use, e.g. ``"ECB: free reuse with attribution"``.
    """

    source: str
    dataset: str
    url: str
    retrieved_at: datetime
    sha256: str
    size_bytes: int
    terms: str

    def __post_init__(self) -> None:
        """Validate every field."""
        for name in ("source", "dataset"):
            value = getattr(self, name)
            if not _is_safe_name(value):
                raise ValidationError(f"provenance {name} {value!r} is not a safe identifier")
        if not _is_https(self.url):
            raise ValidationError(f"provenance url must be https, got {self.url!r}")
        if not _is_utc(self.retrieved_at):
            raise ValidationError("provenance retrieved_at must be timezone-aware UTC")
        if not _is_sha256(self.sha256):
            raise ValidationError("provenance sha256 must be 64 lower-case hex characters")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValidationError(f"provenance size_bytes must be >= 0, got {self.size_bytes!r}")

    def to_json(self) -> str:
        """Serialise to an indented, human-readable JSON document."""
        record = asdict(self) | {"retrieved_at": self.retrieved_at.isoformat()}
        return json.dumps(record, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Provenance:
        """Parse a document produced by :meth:`to_json`."""
        record = json.loads(text)
        record["retrieved_at"] = datetime.fromisoformat(record["retrieved_at"])
        return cls(**record)


class Unit(Enum):
    """Unit of the values in a dataset. Percentages are always converted to decimals."""

    RETURN = "return"  # per-period return in decimals (0.01 = 1%)
    RATE_PER_YEAR = "rate_per_year"  # annualised rate in decimals, e.g. a policy rate
    INDEX_LEVEL = "index_level"  # e.g. a price index such as HICP
    PRICE = "price"  # price in a currency
    FX_RATE = "fx_rate"  # units of quote currency per one unit of base currency


@dataclass(frozen=True)
class Dataset:
    """A parsed dataset with the metadata needed to use it correctly.

    Parameters
    ----------
    data
        Values on a validated index; stored as a validated copy (NaNs kept).
    provenance
        Provenance of the raw file the data was parsed from.
    frequency
        Sampling frequency.
    unit
        Unit of the values.
    return_kind
        Required when ``unit`` is :attr:`Unit.RETURN`, and must be ``None`` otherwise.
    currency
        Currency of the values, if they are monetary or returns of a currency investment.
    availability
        How and when the values became known (point-in-time information).
    notes
        Transformations applied while parsing and other caveats.
    available_from
        Optional point-in-time information: for each row, the date from which the value was
        publicly known. Same index as ``data``; never earlier than the reference date.
    status
        Optional observation status codes as published (e.g. ECB ``A`` normal, ``E``
        estimate, ``Q`` missing). Same index as ``data``.
    """

    data: pd.DataFrame
    provenance: Provenance
    frequency: Frequency
    unit: Unit
    return_kind: ReturnKind | None
    currency: Currency | None
    availability: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    available_from: pd.Series | None = None
    status: pd.Series | None = None

    def __post_init__(self) -> None:
        """Validate the data and the consistency of the metadata."""
        valid = validate_frame(self.data, nan_policy=NanPolicy.KEEP, name=self.provenance.dataset)
        object.__setattr__(self, "data", valid)
        if (self.unit is Unit.RETURN) != (self.return_kind is not None):
            raise ValidationError("return_kind is required for returns and only for returns")
        if self.available_from is not None:
            available = self.available_from
            _require_aligned(available, valid, "available_from")
            if not pd.api.types.is_datetime64_dtype(available.dtype) or available.hasnans:
                raise ValidationError("available_from must hold dates without NaT")
            if (available.to_numpy() < valid.index.to_numpy()).any():
                raise ValidationError("available_from is before the reference date for some rows")
        if self.status is not None:
            _require_aligned(self.status, valid, "status")


def _require_aligned(series: object, data: pd.DataFrame, name: str) -> None:
    if not isinstance(series, pd.Series) or not series.index.equals(data.index):
        raise ValidationError(f"{name} must be a Series with the same index as data")


def _is_safe_name(value: object) -> bool:
    return isinstance(value, str) and bool(_NAME.match(value)) and ".." not in value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256.match(value))


def _is_https(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _is_utc(value: object) -> bool:
    return isinstance(value, datetime) and value.utcoffset() == timedelta(0)
