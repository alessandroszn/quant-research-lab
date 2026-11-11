"""Synthetic fund holdings for look-through tests (no real issuer data)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd

from qrlab.checks.context import CheckContext
from qrlab.data.provenance import Provenance
from qrlab.instruments.holdings import HoldingsSnapshot
from qrlab.instruments.identifiers import Isin, is_valid_isin
from qrlab.lookthrough.exposures import WeightTreatment, look_through
from qrlab.lookthrough.inputs import LookThroughInputs
from qrlab.lookthrough.tracking import TrackingSeries


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


def with_lookthrough(
    ctx: CheckContext,
    snapshots: Mapping[Isin, HoldingsSnapshot],
    *,
    tracking: Mapping[Isin, tuple[TrackingSeries, TrackingSeries]] | None = None,
    issuers: Mapping[Isin, str] | None = None,
) -> CheckContext:
    """Return ``ctx`` with look-through inputs built from its own weights (as reported)."""
    exposures = look_through(
        as_of=ctx.as_of,
        position_weights=ctx.position_weights(),
        cash_weights=ctx.cash_weights(),
        instruments=ctx.instruments,
        snapshots=snapshots,
        treatment=WeightTreatment.AS_REPORTED,
        issuers=issuers,
    )
    used = {isin: s for isin, s in snapshots.items() if isin in exposures.snapshot_dates}
    inputs = LookThroughInputs(exposures, used, tracking or {})
    return replace(ctx, lookthrough=inputs)
