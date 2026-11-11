r"""Overlap between funds and exposure duplicated across positions.

- **Pairwise overlap** of funds :math:`f` and :math:`g` is
  :math:`\sum_i \min(h_{f,i}, h_{g,i})` over securities matched by ISIN. Weights of a
  security listed more than once in a fund are summed first; negative weights (short
  derivatives) count as 0. Holdings without an ISIN cannot be matched and are reported as the
  unmatched share of each fund.
- **Duplicated exposure** is the look-through weight of securities (by ISIN) reached through two
  or more positions, direct holdings included.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qrlab.instruments.holdings import HoldingsSnapshot, normalised_weights
from qrlab.instruments.identifiers import Isin
from qrlab.lookthrough.exposures import LookThrough, WeightTreatment

__all__ = ["Overlap", "duplicated_exposure", "pair_overlap", "pairwise_overlaps"]


@dataclass(frozen=True)
class Overlap:
    """Overlap of two funds, with the weight of each that could not be matched."""

    first: Isin
    second: Isin
    overlap: float
    unmatched_first: float
    unmatched_second: float


def pair_overlap(
    first: HoldingsSnapshot, second: HoldingsSnapshot, *, treatment: WeightTreatment
) -> Overlap:
    """Return the overlap of two funds' holdings."""
    a, a_unmatched = _by_isin(first, treatment)
    b, b_unmatched = _by_isin(second, treatment)
    common = a.index.intersection(b.index)
    value = float(pd.concat([a[common], b[common]], axis=1).min(axis=1).sum())
    return Overlap(first.fund, second.fund, value, a_unmatched, b_unmatched)


def pairwise_overlaps(
    snapshots: dict[Isin, HoldingsSnapshot] | list[HoldingsSnapshot],
    *,
    treatment: WeightTreatment,
) -> list[Overlap]:
    """Overlap of every pair of funds, ordered by ISIN codes."""
    items = sorted(
        snapshots.values() if isinstance(snapshots, dict) else snapshots, key=lambda s: s.fund.code
    )
    return [
        pair_overlap(items[i], items[j], treatment=treatment)
        for i in range(len(items))
        for j in range(i + 1, len(items))
    ]


def duplicated_exposure(lookthrough: LookThrough) -> tuple[float, tuple[str, ...]]:
    """Weight of securities reached through two or more positions, and those ISINs."""
    rows = lookthrough.rows
    rows = rows[rows["kind"].isin(["holding", "direct"]) & rows["isin"].notna()]
    sources = rows.groupby("isin")["source"].nunique()
    duplicated = sorted(str(i) for i in sources[sources >= 2].index)
    weight = float(rows.loc[rows["isin"].isin(duplicated), "weight"].sum())
    return weight, tuple(duplicated)


def _by_isin(snapshot: HoldingsSnapshot, treatment: WeightTreatment) -> tuple[pd.Series, float]:
    table = snapshot.holdings
    weights = (
        normalised_weights(snapshot) if treatment is WeightTreatment.NORMALISED else table["weight"]
    )
    weights = weights.clip(lower=0.0)
    known = table["isin"].notna()
    grouped = weights[known].groupby(table.loc[known, "isin"]).sum()
    return grouped, float(weights[~known].sum())
