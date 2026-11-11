"""Synthetic fund holdings for look-through tests (no real issuer data)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime

import pandas as pd

from qrlab.data.provenance import Provenance
from qrlab.instruments.holdings import HoldingsSnapshot
from qrlab.instruments.identifiers import Isin, is_valid_isin


def security(prefix: str, number: int) -> str:
    """Return a made-up ISIN ``<prefix>00000000<n><check>`` with a valid check digit."""
    body = f"{prefix}{number:09d}"
    for digit in "0123456789":
        if is_valid_isin(body + digit):
            return body + digit
    raise AssertionError(body)  # pragma: no cover - every body has one check digit


X, Y, Z, W = (security("US", n) for n in (1, 2, 3, 4))


def holding(
    name: str,
    weight: float,
    *,
    isin: str | None = None,
    country: str | None = None,
    sector: str | None = None,
    currency: str | None = None,
    asset_class: str = "equity",
) -> dict[str, object]:
    """Return one holdings row."""
    return {
        "name": name,
        "isin": isin,
        "weight": weight,
        "country": country,
        "sector": sector,
        "currency": currency,
        "asset_class": asset_class,
    }


def snapshot(
    fund: Isin, rows: Sequence[dict[str, object]], as_of: date = date(2026, 5, 31)
) -> HoldingsSnapshot:
    """Return a holdings snapshot of ``fund`` with the given rows."""
    return HoldingsSnapshot(
        fund=fund,
        as_of=as_of,
        holdings=pd.DataFrame(list(rows)),
        provenance=Provenance(
            source="user",
            dataset=f"holdings_{fund.code.lower()}",
            url="file:holdings.csv",
            retrieved_at=datetime(2026, 6, 1, tzinfo=UTC),
            sha256=hashlib.sha256(fund.code.encode()).hexdigest(),
            size_bytes=12,
            terms="synthetic",
        ),
        weight_basis="market value, % of NAV",
        sector_taxonomy="Synthetic sectors" if any(r.get("sector") for r in rows) else None,
        notes=(),
    )


def countries(fund: Isin, weights: dict[str, float]) -> HoldingsSnapshot:
    """Return a fund holding one security per country, with the given weights."""
    return snapshot(
        fund,
        [
            holding(f"{code} Corp", w, isin=security(code, n), country=code, currency="USD")
            for n, (code, w) in enumerate(weights.items(), start=1)
        ],
    )
