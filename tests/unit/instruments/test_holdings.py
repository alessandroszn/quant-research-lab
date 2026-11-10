"""Fund holdings snapshots: validation and explicit findings. All holdings are synthetic.

Hand calculations:

- weights 0.60, 0.30, 0.08 sum to 0.98: the 2 % gap is reported with tolerance 0.01 and
  accepted with tolerance 0.025 (a tolerance exactly equal to the gap is a floating-point
  coin toss); normalised they become 0.6/0.98 = 0.612245, 0.306122, 0.081633
- with country unknown for the 0.08 holding, 0.08 / 0.98 = 8.16 % of the weight has no country
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.provenance import Provenance
from qrlab.instruments.holdings import (
    HOLDING_COLUMNS,
    HoldingsSnapshot,
    holdings_issues,
    normalised_weights,
)
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import IssueKind

FUND = Isin("IE00B4L5Y983")
ON = date(2026, 11, 10)


def _frame(**overrides: list[object]) -> pd.DataFrame:
    columns: dict[str, list[object]] = {
        "name": ["Alpha Corp", "Beta Corp", "Gamma Corp"],
        "isin": ["US0378331005", "LU0274208692", None],
        "weight": [0.60, 0.30, 0.08],
        "country": ["US", "LU", None],
        "sector": ["Information Technology", "Financials", None],
        "currency": ["USD", "EUR", "JPY"],
        "asset_class": ["equity", "equity", "cash"],
    }
    columns.update(overrides)
    return pd.DataFrame(columns)


def _prov() -> Provenance:
    return Provenance(
        source="user",
        dataset="holdings_ie00b4l5y983",
        url="file:holdings.csv",
        retrieved_at=datetime(2026, 11, 1, tzinfo=UTC),
        sha256=hashlib.sha256(b"x").hexdigest(),
        size_bytes=1,
        terms="synthetic",
    )


def _snapshot(
    frame: pd.DataFrame | None = None, as_of: date = date(2026, 10, 31)
) -> HoldingsSnapshot:
    return HoldingsSnapshot(
        fund=FUND,
        as_of=as_of,
        holdings=_frame() if frame is None else frame,
        provenance=_prov(),
        weight_basis="market value, % of NAV",
        sector_taxonomy="GICS",
        notes=(),
    )


# --------------------------------------------------------------------------- validation
def test_valid_snapshot_is_a_canonical_copy() -> None:
    frame = _frame()[list(reversed(HOLDING_COLUMNS))]  # any column order is accepted
    snapshot = _snapshot(frame)
    assert tuple(snapshot.holdings.columns) == HOLDING_COLUMNS
    assert snapshot.holdings is not frame
    assert snapshot.holdings["weight"].dtype == np.float64
    assert snapshot.holdings.loc[2, "isin"] is None


def test_nan_text_cells_become_none() -> None:
    snapshot = _snapshot(_frame(country=["US", "LU", np.nan]))
    assert snapshot.holdings.loc[2, "country"] is None


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"weight": [0.6, np.nan, 0.08]}, "weight"),
        ({"weight": [0.6, np.inf, 0.08]}, "weight"),
        ({"isin": ["US0378331006", None, None]}, "ISIN"),
        ({"country": ["United States", "LU", None]}, "country"),
        ({"currency": ["usd", "EUR", "JPY"]}, "currency"),
        ({"asset_class": ["equity", "stocks", "cash"]}, "asset_class"),
        ({"name": ["Alpha Corp", "", "Gamma Corp"]}, "name"),
        ({"sector": ["IT", "", None]}, "sector"),
    ],
)
def test_invalid_cells_raise(overrides: dict[str, list[object]], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _snapshot(_frame(**overrides))


def test_missing_or_extra_columns_raise() -> None:
    with pytest.raises(ValidationError, match="columns"):
        _snapshot(_frame().drop(columns="sector"))
    with pytest.raises(ValidationError, match="columns"):
        _snapshot(_frame().assign(extra=1))


def test_empty_snapshot_raises() -> None:
    with pytest.raises(ValidationError, match="empty"):
        _snapshot(_frame().iloc[0:0])


def test_negative_weights_are_allowed() -> None:
    snapshot = _snapshot(_frame(weight=[0.70, 0.35, -0.05]))
    assert snapshot.holdings["weight"].min() == pytest.approx(-0.05)


def test_sector_taxonomy_must_be_named_when_sectors_are_present() -> None:
    with pytest.raises(ValidationError, match="taxonomy"):
        HoldingsSnapshot(
            fund=FUND,
            as_of=date(2026, 10, 31),
            holdings=_frame(),
            provenance=_prov(),
            weight_basis="market value",
            sector_taxonomy=None,
            notes=(),
        )


# --------------------------------------------------------------------------- findings
def test_weight_gap_depends_on_the_tolerance() -> None:
    snapshot = _snapshot()
    issues = holdings_issues(snapshot, on=ON, max_age_days=60, weight_tolerance=0.01)
    weights = [i for i in issues if i.kind is IssueKind.WEIGHTS]
    assert len(weights) == 1
    assert "98.00%" in weights[0].detail
    relaxed = holdings_issues(snapshot, on=ON, max_age_days=60, weight_tolerance=0.025)
    assert not [i for i in relaxed if i.kind is IssueKind.WEIGHTS]


def test_unknown_shares_are_reported_hand_example() -> None:
    issues = holdings_issues(_snapshot(), on=ON, max_age_days=60, weight_tolerance=0.05)
    unknown = {i.field: i.detail for i in issues if i.kind is IssueKind.UNKNOWN_SHARE}
    assert set(unknown) == {"country", "sector", "isin"}
    assert "8.16%" in unknown["country"]


def test_duplicated_isins_are_reported_not_merged() -> None:
    snapshot = _snapshot(_frame(isin=["US0378331005", "US0378331005", None]))
    issues = holdings_issues(snapshot, on=ON, max_age_days=60, weight_tolerance=0.05)
    assert [i.detail for i in issues if i.kind is IssueKind.DUPLICATE] == [
        "US0378331005 appears 2 times"
    ]
    assert len(snapshot.holdings) == 3


def test_stale_and_future_snapshots() -> None:
    stale = holdings_issues(
        _snapshot(as_of=date(2026, 6, 30)), on=ON, max_age_days=60, weight_tolerance=0.05
    )
    assert IssueKind.STALE in {i.kind for i in stale}
    future = holdings_issues(
        _snapshot(as_of=date(2026, 12, 31)), on=ON, max_age_days=60, weight_tolerance=0.05
    )
    assert IssueKind.FUTURE in {i.kind for i in future}


def test_complete_snapshot_has_no_issues() -> None:
    frame = _frame(
        isin=["US0378331005", "LU0274208692", "IE00B4L5Y983"],
        weight=[0.60, 0.30, 0.10],
        country=["US", "LU", "IE"],
        sector=["Information Technology", "Financials", "Cash"],
    )
    assert holdings_issues(_snapshot(frame), on=ON, max_age_days=60, weight_tolerance=0.001) == []


@pytest.mark.parametrize("bad", [-0.01, float("nan"), float("inf")])
def test_weight_tolerance_must_be_non_negative_and_finite(bad: float) -> None:
    with pytest.raises(ValidationError, match="weight_tolerance"):
        holdings_issues(_snapshot(), on=ON, max_age_days=60, weight_tolerance=bad)


# --------------------------------------------------------------------------- normalisation
def test_normalised_weights_hand_example() -> None:
    weights = normalised_weights(_snapshot())
    np.testing.assert_allclose(weights.to_numpy(), [0.6 / 0.98, 0.3 / 0.98, 0.08 / 0.98])
    assert weights.sum() == pytest.approx(1.0)


def test_normalisation_never_changes_the_snapshot() -> None:
    snapshot = _snapshot()
    normalised_weights(snapshot)
    assert snapshot.holdings["weight"].sum() == pytest.approx(0.98)


def test_normalisation_refuses_non_positive_total() -> None:
    with pytest.raises(ValidationError, match="total"):
        normalised_weights(_snapshot(_frame(weight=[0.5, -0.5, 0.0])))


def test_object_columns_with_none_are_accepted() -> None:
    frame = _frame()
    frame["isin"] = pd.Series(["US0378331005", None, None], dtype=object)
    assert _snapshot(frame).holdings.loc[1, "isin"] is None


def test_other_invalid_inputs() -> None:
    with pytest.raises(ValidationError, match="DataFrame"):
        _snapshot(frame=[1, 2])  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="numeric"):
        _snapshot(_frame(weight=["a", "b", "c"]))
    with pytest.raises(ValidationError, match="weight_basis"):
        HoldingsSnapshot(
            fund=FUND,
            as_of=date(2026, 10, 31),
            holdings=_frame(),
            provenance=_prov(),
            weight_basis="  ",
            sector_taxonomy="GICS",
            notes=(),
        )
    with pytest.raises(ValidationError, match="max_age_days"):
        holdings_issues(_snapshot(), on=ON, max_age_days=-1, weight_tolerance=0.01)
