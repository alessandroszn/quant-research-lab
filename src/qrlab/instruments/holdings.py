"""Fund holdings at a known date, for look-through analysis.

A :class:`HoldingsSnapshot` stores what a fund reported holding on ``as_of``. Weights are
decimals and are never rescaled silently: gaps from 100 %, duplicated holdings, unknown
countries or sectors and stale snapshots are reported by :func:`holdings_issues`, and
rescaling happens only through the explicit :func:`normalised_weights`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.data.provenance import Provenance
from qrlab.instruments.identifiers import Isin, is_valid_isin, validate_country
from qrlab.instruments.master import AssetClass, Issue, IssueKind

__all__ = ["HOLDING_COLUMNS", "HoldingsSnapshot", "holdings_issues", "normalised_weights"]

HOLDING_COLUMNS: tuple[str, ...] = (
    "name",
    "isin",
    "weight",
    "country",
    "sector",
    "currency",
    "asset_class",
)
"""Canonical columns of a holdings table, in order."""

_OPTIONAL_TEXT = ("isin", "country", "sector", "currency")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_ASSET_CLASSES = frozenset(member.value for member in AssetClass)


@dataclass(frozen=True)
class HoldingsSnapshot:
    """What a fund held on ``as_of``.

    Parameters
    ----------
    fund
        ISIN of the fund.
    as_of
        Date of the holdings as reported by the issuer.
    holdings
        One row per holding with exactly the :data:`HOLDING_COLUMNS`:

        - ``name``: non-empty text;
        - ``isin``: valid ISIN or missing;
        - ``weight``: finite decimal weight (may be negative, e.g. derivatives);
        - ``country``: ISO 3166-1 alpha-2 code or missing;
        - ``sector``: text as reported (see ``sector_taxonomy``) or missing;
        - ``currency``: three upper-case letters or missing;
        - ``asset_class``: an :class:`AssetClass` value such as ``"equity"``.

        Missing values (``None`` or NaN) are stored as ``None``. The table is stored as a
        validated copy with a fresh integer index and canonical column order.
    provenance
        Provenance of the file the holdings were read from.
    weight_basis
        What the weights measure, as stated by the issuer (e.g. "market value, % of NAV").
    sector_taxonomy
        Name of the sector classification (e.g. "GICS"); required when any sector is present.
    notes
        Transformations and caveats from loading.
    """

    fund: Isin
    as_of: date
    holdings: pd.DataFrame
    provenance: Provenance
    weight_basis: str
    sector_taxonomy: str | None
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate and store a canonical copy of the holdings table."""
        object.__setattr__(self, "holdings", _validated(self.holdings))
        if not self.weight_basis.strip():
            raise ValidationError("weight_basis must describe what the weights measure")
        if self.sector_taxonomy is None and self.holdings["sector"].notna().any():
            raise ValidationError("sector_taxonomy is required when sectors are present")


def holdings_issues(
    snapshot: HoldingsSnapshot, *, on: date, max_age_days: int, weight_tolerance: float
) -> list[Issue]:
    """Report data-quality findings for a holdings snapshot.

    Parameters
    ----------
    snapshot
        Snapshot to check.
    on
        Date of the analysis.
    max_age_days
        Snapshots older than this many days before ``on`` are reported as stale.
    weight_tolerance
        Largest accepted absolute gap between the sum of weights and 1 (e.g. ``0.005``). Sums
        are floating-point, so a gap exactly equal to the tolerance may fall on either side.

    Returns
    -------
    list of Issue
        Weight-sum gap, duplicated ISINs, the share of (absolute) weight with unknown ISIN,
        country, sector or currency, and stale or future snapshots.
    """
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValidationError(f"max_age_days must be a non-negative int, got {max_age_days!r}")
    if not (math.isfinite(weight_tolerance) and weight_tolerance >= 0):
        raise ValidationError(f"weight_tolerance must be finite and >= 0, got {weight_tolerance}")
    subject = snapshot.fund.code
    table = snapshot.holdings
    weights = table["weight"].to_numpy(dtype=np.float64)
    issues: list[Issue] = []

    total = float(weights.sum())
    if abs(total - 1.0) > weight_tolerance:
        issues.append(
            Issue(
                subject,
                "weight",
                IssueKind.WEIGHTS,
                f"weights sum to {total:.2%} (tolerance {weight_tolerance:.2%}); not rescaled",
            )
        )
    counts = table["isin"].dropna().value_counts()
    issues.extend(
        Issue(subject, "isin", IssueKind.DUPLICATE, f"{isin} appears {int(n)} times")
        for isin, n in counts.items()
        if n > 1
    )
    gross = float(np.abs(weights).sum())
    for field in _OPTIONAL_TEXT:
        unknown = table[field].isna().to_numpy()
        share = float(np.abs(weights[unknown]).sum()) / gross if gross > 0 else 0.0
        if share > 0:
            issues.append(
                Issue(
                    subject,
                    field,
                    IssueKind.UNKNOWN_SHARE,
                    f"{share:.2%} of the absolute weight has unknown {field}",
                )
            )
    age = (on - snapshot.as_of).days
    if age < 0:
        issues.append(
            Issue(subject, "as_of", IssueKind.FUTURE, f"holdings dated {snapshot.as_of} after {on}")
        )
    elif age > max_age_days:
        issues.append(
            Issue(
                subject,
                "as_of",
                IssueKind.STALE,
                f"holdings are {age} days old on {on} (limit {max_age_days})",
            )
        )
    return issues


def normalised_weights(snapshot: HoldingsSnapshot) -> pd.Series:
    """Return weights divided by their sum. Explicit: the snapshot itself is never changed.

    Raises
    ------
    ValidationError
        If the total weight is not positive.
    """
    weights = snapshot.holdings["weight"]
    total = float(weights.sum())
    if not total > 0:
        raise ValidationError(f"cannot normalise: total weight is {total}")
    return weights / total


# --------------------------------------------------------------------------- validation
def _validated(frame: object) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("holdings must be a pandas DataFrame")
    if set(frame.columns) != set(HOLDING_COLUMNS) or len(frame.columns) != len(HOLDING_COLUMNS):
        raise ValidationError(f"holdings columns must be exactly {list(HOLDING_COLUMNS)}")
    if frame.empty:
        raise ValidationError("holdings snapshot is empty")
    table = frame.loc[:, list(HOLDING_COLUMNS)].reset_index(drop=True)
    try:
        weights = table["weight"].astype("float64")
    except (TypeError, ValueError) as exc:
        raise ValidationError("weight must be numeric") from exc
    if not np.isfinite(weights.to_numpy()).all():
        raise ValidationError("every weight must be finite (no NaN or inf)")

    text = {name: [_none_if_missing(v) for v in table[name]] for name in HOLDING_COLUMNS}
    for row, value in enumerate(text["name"]):
        _require_text(value, f"name (row {row})")
    for row, value in enumerate(text["isin"]):
        if value is not None and not is_valid_isin(value):  # type: ignore[arg-type]
            raise ValidationError(f"invalid ISIN {value!r} in row {row}")
    for value in text["country"]:
        if value is not None:
            validate_country(value)
    for row, value in enumerate(text["sector"]):
        if value is not None:
            _require_text(value, f"sector (row {row})")
    for row, value in enumerate(text["currency"]):
        if value is not None and not (isinstance(value, str) and _CURRENCY.match(value)):
            raise ValidationError(f"currency {value!r} in row {row} is not an ISO 4217 code")
    for row, value in enumerate(text["asset_class"]):
        if value not in _ASSET_CLASSES:
            raise ValidationError(f"asset_class {value!r} in row {row} is not an AssetClass value")

    columns: dict[str, object] = {
        name: pd.Series(text[name], dtype=object) for name in HOLDING_COLUMNS
    }
    columns["weight"] = weights
    return pd.DataFrame(columns)


def _none_if_missing(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be non-empty text")
