"""Return conventions: hand-calculated examples first, then cross-checks and properties.

Hand calculations (from the approved design note):

- prices 100, 110, 99 -> simple returns 0.10, -0.10
- log returns ln(1.1) = 0.0953101798..., ln(0.9) = -0.1053605157...
- compounding (0.10, -0.10): 1.1 * 0.9 - 1 = -0.01; in log terms ln(0.99) = -0.0100503359...
- daily 0.01 x 3 in January and 0.02 x 2 in February -> monthly 1.01**3 - 1 = 0.030301 and
  1.02**2 - 1 = 0.0404
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.core.returns import (
    ReturnKind,
    aggregate_returns,
    compound,
    excess_returns,
    log_to_simple,
    prices_to_returns,
    simple_to_log,
    wealth_index,
)

SIMPLE, LOG = ReturnKind.SIMPLE, ReturnKind.LOG


def _s(values: list[float], start: str = "2026-01-05") -> pd.Series:
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), name="r")


# --------------------------------------------------------------------------- prices -> returns
def test_prices_to_simple_returns_hand_example() -> None:
    out = prices_to_returns(_s([100.0, 110.0, 99.0]), kind=SIMPLE)
    assert list(out.index) == list(pd.bdate_range("2026-01-06", periods=2))
    np.testing.assert_allclose(out.to_numpy(), [0.10, -0.10], rtol=0, atol=1e-15)


def test_prices_to_log_returns_hand_example() -> None:
    out = prices_to_returns(_s([100.0, 110.0, 99.0]), kind=LOG)
    np.testing.assert_allclose(out.to_numpy(), [0.0953101798043249, -0.1053605156578263])


def test_prices_to_returns_frame() -> None:
    idx = pd.bdate_range("2026-01-05", periods=3)
    prices = pd.DataFrame({"a": [100.0, 110.0, 99.0], "b": [50.0, 50.0, 55.0]}, index=idx)
    out = prices_to_returns(prices, kind=SIMPLE)
    expected = pd.DataFrame({"a": [0.10, -0.10], "b": [0.0, 0.10]}, index=idx[1:])
    pd.testing.assert_frame_equal(out, expected, atol=1e-15, rtol=0)


def test_nan_price_propagates_to_both_adjacent_returns_and_is_not_filled() -> None:
    out = prices_to_returns(_s([100.0, np.nan, 99.0, 99.0]), kind=SIMPLE)
    assert out.isna().tolist() == [True, True, False]


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_non_positive_prices_raise(bad: float) -> None:
    with pytest.raises(ValidationError, match="positive"):
        prices_to_returns(_s([100.0, bad]), kind=SIMPLE)


@pytest.mark.parametrize("n", [0, 1])
def test_too_few_prices_give_empty_returns(n: int) -> None:
    prices = _s([100.0] * n) if n else pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    assert prices_to_returns(prices, kind=SIMPLE).empty


def test_prices_input_not_mutated() -> None:
    prices = _s([100.0, 110.0, 99.0])
    before = prices.copy()
    prices_to_returns(prices, kind=LOG)
    pd.testing.assert_series_equal(prices, before)


def test_kind_must_be_enum() -> None:
    with pytest.raises(ValidationError, match="ReturnKind"):
        prices_to_returns(_s([1.0, 2.0]), kind="simple")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- simple <-> log
def test_simple_log_round_trip(rng: np.random.Generator) -> None:
    r = _s(list(rng.normal(0.0, 0.02, 500)))
    back = log_to_simple(simple_to_log(r))
    np.testing.assert_allclose(back.to_numpy(), r.to_numpy(), rtol=0, atol=1e-15)


def test_simple_to_log_matches_numpy() -> None:
    r = _s([0.10, -0.10, 0.0])
    np.testing.assert_allclose(simple_to_log(r).to_numpy(), np.log1p([0.10, -0.10, 0.0]))


@pytest.mark.parametrize("bad", [-1.0, -1.5])
def test_simple_return_at_or_below_minus_one_cannot_be_logged(bad: float) -> None:
    with pytest.raises(ValidationError, match="-1"):
        simple_to_log(_s([0.01, bad]))


def test_conversion_keeps_nan() -> None:
    assert simple_to_log(_s([np.nan, 0.1])).isna().tolist() == [True, False]


# --------------------------------------------------------------------------- excess returns
def test_excess_returns_hand_example() -> None:
    out = excess_returns(_s([0.05]), _s([0.01]), kind=SIMPLE)
    assert out.iloc[0] == pytest.approx(0.04, abs=1e-15)


def test_excess_returns_frame_minus_series() -> None:
    idx = pd.bdate_range("2026-01-05", periods=2)
    r = pd.DataFrame({"a": [0.05, 0.02], "b": [0.03, 0.00]}, index=idx)
    rf = pd.Series([0.01, 0.01], index=idx)
    out = excess_returns(r, rf, kind=SIMPLE)
    expected = pd.DataFrame({"a": [0.04, 0.01], "b": [0.02, -0.01]}, index=idx)
    pd.testing.assert_frame_equal(out, expected, atol=1e-15, rtol=0)


def test_excess_returns_refuse_misaligned_inputs() -> None:
    with pytest.raises(AlignmentError):
        excess_returns(_s([0.05, 0.01]), _s([0.01, 0.01], start="2026-01-06"), kind=SIMPLE)


# --------------------------------------------------------------------------- compounding
def test_compound_simple_hand_example() -> None:
    assert compound(_s([0.10, -0.10]), kind=SIMPLE) == pytest.approx(-0.01, abs=1e-15)


def test_compound_log_hand_example() -> None:
    r = simple_to_log(_s([0.10, -0.10]))
    assert compound(r, kind=LOG) == pytest.approx(math.log(0.99), abs=1e-15)


def test_compound_empty_is_zero() -> None:
    empty = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    assert compound(empty, kind=SIMPLE) == 0.0
    assert compound(empty, kind=LOG) == 0.0


def test_compound_frame_returns_one_value_per_column() -> None:
    idx = pd.bdate_range("2026-01-05", periods=2)
    r = pd.DataFrame({"a": [0.10, -0.10], "b": [0.0, 0.0]}, index=idx)
    out = compound(r, kind=SIMPLE)
    assert out["a"] == pytest.approx(-0.01, abs=1e-15)
    assert out["b"] == 0.0


def test_compound_refuses_nan() -> None:
    with pytest.raises(ValidationError, match="NaN"):
        compound(_s([0.1, np.nan]), kind=SIMPLE)


def test_compound_simple_and_log_agree(rng: np.random.Generator) -> None:
    r = _s(list(rng.normal(0.0005, 0.01, 1000)))
    via_log = compound(simple_to_log(r), kind=LOG)
    assert compound(r, kind=SIMPLE) == pytest.approx(math.expm1(via_log), rel=1e-12)


# --------------------------------------------------------------------------- wealth index
def test_wealth_index_hand_example() -> None:
    w = wealth_index(_s([0.10, -0.10]), kind=SIMPLE, initial=100.0)
    np.testing.assert_allclose(w.to_numpy(), [110.0, 99.0], rtol=1e-15)


def test_wealth_index_consistent_with_compound(rng: np.random.Generator) -> None:
    r = _s(list(rng.normal(0.0, 0.01, 250)))
    for kind, series in ((SIMPLE, r), (LOG, simple_to_log(r))):
        w = wealth_index(series, kind=kind, initial=1.0)
        expected = compound(series, kind=kind)
        total = w.iloc[-1] - 1.0 if kind is SIMPLE else math.log(w.iloc[-1])
        assert total == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("bad", [0.0, -1.0, math.inf, math.nan])
def test_wealth_index_requires_positive_finite_initial(bad: float) -> None:
    with pytest.raises(ValidationError, match="initial"):
        wealth_index(_s([0.1]), kind=SIMPLE, initial=bad)


# --------------------------------------------------------------------------- aggregation
def _jan_feb() -> pd.Series:
    jan = pd.DatetimeIndex(["2026-01-28", "2026-01-29", "2026-01-30"])
    feb = pd.DatetimeIndex(["2026-02-02", "2026-02-03"])
    return pd.Series([0.01, 0.01, 0.01, 0.02, 0.02], index=jan.append(feb))


def test_aggregate_monthly_hand_example() -> None:
    agg = aggregate_returns(_jan_feb(), kind=SIMPLE, to=Frequency.MONTHLY, min_periods=1)
    assert list(agg.returns.index) == [pd.Timestamp("2026-01-31"), pd.Timestamp("2026-02-28")]
    np.testing.assert_allclose(agg.returns.to_numpy(), [0.030301, 0.0404], rtol=0, atol=1e-15)
    assert agg.counts.tolist() == [3, 2]


def test_aggregate_flags_partial_periods_as_nan() -> None:
    agg = aggregate_returns(_jan_feb(), kind=SIMPLE, to=Frequency.MONTHLY, min_periods=3)
    assert agg.returns.iloc[0] == pytest.approx(0.030301, abs=1e-15)
    assert np.isnan(agg.returns.iloc[1])  # kept, not dropped
    assert agg.counts.tolist() == [3, 2]


def test_aggregate_log_sums() -> None:
    r = simple_to_log(_jan_feb())
    agg = aggregate_returns(r, kind=LOG, to=Frequency.MONTHLY, min_periods=1)
    np.testing.assert_allclose(
        agg.returns.to_numpy(), [3 * math.log(1.01), 2 * math.log(1.02)], rtol=1e-14
    )


def test_aggregate_nan_inside_bucket_gives_nan_not_zero() -> None:
    r = _jan_feb()
    r.iloc[1] = np.nan
    agg = aggregate_returns(r, kind=SIMPLE, to=Frequency.MONTHLY, min_periods=1)
    assert np.isnan(agg.returns.iloc[0])
    assert agg.returns.iloc[1] == pytest.approx(0.0404, abs=1e-15)


def test_aggregate_empty_bucket_in_gap_is_nan() -> None:
    r = pd.Series([0.01, 0.02], index=pd.DatetimeIndex(["2026-01-30", "2026-03-31"]))
    agg = aggregate_returns(r, kind=SIMPLE, to=Frequency.MONTHLY, min_periods=1)
    assert agg.counts.tolist() == [1, 0, 1]
    assert np.isnan(agg.returns.iloc[1])


def test_aggregate_frame_nan_is_per_column() -> None:
    r = pd.DataFrame({"a": _jan_feb(), "b": _jan_feb()})
    r.iloc[0, 0] = np.nan
    agg = aggregate_returns(r, kind=SIMPLE, to=Frequency.MONTHLY, min_periods=1)
    assert agg.returns.isna().iloc[0, 0]
    assert agg.returns.iloc[0, 1] == pytest.approx(0.030301, abs=1e-15)


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_aggregate_min_periods_must_be_positive_int(bad: object) -> None:
    with pytest.raises(ValidationError, match="min_periods"):
        aggregate_returns(_jan_feb(), kind=SIMPLE, to=Frequency.MONTHLY, min_periods=bad)  # type: ignore[arg-type]


def test_aggregate_matches_independent_groupby(rng: np.random.Generator) -> None:
    idx = pd.bdate_range("2024-01-01", "2025-12-31")
    r = pd.Series(rng.normal(0.0003, 0.01, len(idx)), index=idx)
    agg = aggregate_returns(r, kind=SIMPLE, to=Frequency.MONTHLY, min_periods=1)
    months = pd.DatetimeIndex(r.index).to_period("M")
    reference = r.groupby(months).apply(lambda x: float(np.prod(1 + x) - 1))
    np.testing.assert_allclose(agg.returns.to_numpy(), reference.to_numpy(), rtol=1e-12)


def test_aggregation_preserves_total_return(rng: np.random.Generator) -> None:
    idx = pd.bdate_range("2024-01-01", "2025-12-31")
    r = pd.Series(rng.normal(0.0003, 0.01, len(idx)), index=idx)
    for to in (Frequency.WEEKLY, Frequency.MONTHLY, Frequency.QUARTERLY, Frequency.ANNUAL):
        agg = aggregate_returns(r, kind=SIMPLE, to=to, min_periods=1)
        assert compound(agg.returns, kind=SIMPLE) == pytest.approx(compound(r, kind=SIMPLE))


def test_aggregate_input_not_mutated() -> None:
    r = _jan_feb()
    before = r.copy()
    aggregate_returns(r, kind=SIMPLE, to=Frequency.MONTHLY, min_periods=1)
    pd.testing.assert_series_equal(r, before)
