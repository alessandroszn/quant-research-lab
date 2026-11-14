r"""Overlap between funds and exposure duplicated across positions.

- **Pairwise overlap** of funds :math:`f` and :math:`g` is
  :math:`\sum_i \min(h_{f,i}, h_{g,i})` over matched securities. Weights of a security listed
  more than once in a fund are summed first; negative weights (short derivatives) count as 0.

  1. **By ISIN** first, exactly.
  2. **By name** for what is left, only where at least one of the two funds lists the name
     without an ISIN (design 8.2): the weights left after step 1 are grouped by
     :func:`qrlab.lookthrough.names.name_key` and matched in the same way. Two holdings that
     both have an ISIN are never matched by name, and cash lines never are. This part is
     reported on its own (:attr:`Overlap.by_name`), because a name match is approximate.

  The weight of each fund's holdings without an ISIN is reported as its unmatched share.
- **Duplicated exposure** is the look-through weight of securities (by ISIN) reached through two
  or more positions, direct holdings included.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from qrlab.instruments.holdings import HoldingsSnapshot, normalised_weights
from qrlab.instruments.identifiers import Isin
from qrlab.lookthrough.exposures import LookThrough, WeightTreatment
from qrlab.lookthrough.names import name_key

__all__ = ["Overlap", "duplicated_exposure", "pair_overlap", "pairwise_overlaps"]


@dataclass(frozen=True)
class Overlap:
    """Overlap of two funds, with the weight of each that has no ISIN.

    ``overlap`` includes ``by_name``, the part matched by normalised name (approximate).
    """

    first: Isin
    second: Isin
    overlap: float
    unmatched_first: float
    unmatched_second: float
    by_name: float = 0.0


def pair_overlap(
    first: HoldingsSnapshot, second: HoldingsSnapshot, *, treatment: WeightTreatment
) -> Overlap:
    """Return the overlap of two funds' holdings, by ISIN and then by name."""
    a, b = _Holdings.of(first, treatment), _Holdings.of(second, treatment)
    common = sorted(set(a.by_isin) & set(b.by_isin))
    matched = {isin: min(a.by_isin[isin], b.by_isin[isin]) for isin in common}
    by_isin = sum(matched.values())
    a_names, a_without = a.names_left(matched)
    b_names, b_without = b.names_left(matched)
    by_name = sum(
        min(a_names[key], b_names[key])
        for key in set(a_names) & set(b_names)
        if key in a_without or key in b_without
    )
    return Overlap(
        first.fund, second.fund, by_isin + by_name, a.unmatched, b.unmatched, by_name=by_name
    )


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


@dataclass(frozen=True)
class _Holdings:
    """One fund's non-negative holding weights, by ISIN and, without one, by name key."""

    by_isin: Mapping[str, float]
    isin_names: Mapping[str, str]  # ISIN -> name key of its first listing
    without_isin: Mapping[str, float]  # name key -> weight, cash lines excluded
    unmatched: float  # weight without an ISIN, cash lines included

    @classmethod
    def of(cls, snapshot: HoldingsSnapshot, treatment: WeightTreatment) -> _Holdings:
        table = snapshot.holdings
        weights = (
            normalised_weights(snapshot)
            if treatment is WeightTreatment.NORMALISED
            else table["weight"]
        ).clip(lower=0.0)
        by_isin: dict[str, float] = {}
        isin_names: dict[str, str] = {}
        without: dict[str, float] = {}
        unmatched = 0.0
        for row, weight in zip(table.itertuples(index=False), weights, strict=True):
            isin = row.isin if isinstance(row.isin, str) else None  # missing: None or NaN
            if isin is not None:
                by_isin[isin] = by_isin.get(isin, 0.0) + float(weight)
                isin_names.setdefault(isin, name_key(str(row.name)))
                continue
            unmatched += float(weight)
            if row.asset_class != "cash":
                key = name_key(str(row.name))
                without[key] = without.get(key, 0.0) + float(weight)
        return cls(by_isin, isin_names, without, unmatched)

    def names_left(self, matched: Mapping[str, float]) -> tuple[dict[str, float], set[str]]:
        """Return the weight left after the ISIN matches, by name key, and the keys without ISIN."""
        left = dict(self.without_isin)
        for isin, weight in self.by_isin.items():
            rest = weight - matched.get(isin, 0.0)
            if rest > 0.0:
                key = self.isin_names[isin]
                left[key] = left.get(key, 0.0) + rest
        return left, set(self.without_isin)
