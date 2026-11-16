"""Total-return index from prices and distributions (design note 11.1).

Hand calculations (from the approved design note):

- prices 100 (d0), 98 (d1, ex-date d1, D = 2), 99 (d2): index 100, 100, 101.0204...;
  returns 0 % and 99/98 - 1 = 1.0204 %; price returns -2 % and +1.0204 %;
- prices 100 (d0), 97.5 (d2), D = 2 with ex-date d1 (no price): return 99.5/100 - 1 = -0.5 %;
- two distributions in one period are summed: 100 -> 96 with 1.5 + 2.5 gives 0 %.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind, distribution_adjusted, prices_to_returns

D0, D1, D2, D3 = (pd.Timestamp(d) for d in ("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"))


def _prices(values: list[float], dates: list[pd.Timestamp]) -> pd.Series:
    return pd.Series(values, index=pd.DatetimeIndex(dates), name="IE0000000012")


def _paid(amounts: list[float], dates: list[pd.Timestamp]) -> pd.Series:
    return pd.Series(amounts, index=pd.DatetimeIndex(dates), dtype="float64")


def test_distribution_on_a_price_date() -> None:
    prices = _prices([100.0, 98.0, 99.0], [D0, D1, D2])
    index = distribution_adjusted(prices, _paid([2.0], [D1]))
    assert index.tolist() == pytest.approx([100.0, 100.0, 100.0 * 99.0 / 98.0], abs=1e-12)
    assert index.index.equals(prices.index)
    assert index.name == prices.name
    returns = prices_to_returns(index, kind=ReturnKind.SIMPLE)
    assert returns.tolist() == pytest.approx([0.0, 99.0 / 98.0 - 1.0], abs=1e-12)
    assert prices_to_returns(prices, kind=ReturnKind.SIMPLE).tolist() == pytest.approx(
        [-0.02, 99.0 / 98.0 - 1.0], abs=1e-12
    )


def test_distribution_between_price_dates_enters_the_next_period() -> None:
    prices = _prices([100.0, 97.5], [D0, D2])
    index = distribution_adjusted(prices, _paid([2.0], [D1]))
    assert index.iloc[-1] / index.iloc[0] - 1.0 == pytest.approx(-0.005, abs=1e-12)


def test_two_distributions_in_one_period_are_summed() -> None:
    prices = _prices([100.0, 96.0], [D0, D2])
    index = distribution_adjusted(prices, _paid([1.5, 2.5], [D1, D2]))
    assert index.tolist() == pytest.approx([100.0, 100.0], abs=1e-12)


def test_no_distributions_leave_the_prices_unchanged() -> None:
    prices = _prices([100.0, 98.0, 99.0], [D0, D1, D2])
    assert distribution_adjusted(prices, _paid([], [])).equals(prices.astype("float64"))


def test_inputs_are_not_modified() -> None:
    prices = _prices([100.0, 98.0, 99.0], [D0, D1, D2])
    paid = _paid([2.0], [D1])
    before = (prices.copy(), paid.copy())
    distribution_adjusted(prices, paid)
    assert prices.equals(before[0])
    assert paid.equals(before[1])


def test_cross_check_against_a_cumulative_product(rng: np.random.Generator) -> None:
    dates = pd.bdate_range("2024-01-01", periods=300)
    prices = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, 300))), index=dates)
    ex_dates = dates[rng.choice(np.arange(1, 300), size=8, replace=False)].sort_values()
    paid = pd.Series(rng.uniform(0.2, 1.5, 8), index=ex_dates)
    index = distribution_adjusted(prices, paid)
    d = paid.reindex(dates, fill_value=0.0)
    expected = ((prices + d) / prices.shift(1)).fillna(1.0).cumprod() * prices.iloc[0]
    np.testing.assert_allclose(index.to_numpy(), expected.to_numpy(), rtol=1e-12)


@pytest.mark.parametrize(
    ("amounts", "dates", "message"),
    [
        ([2.0], [D0], "on or before the first price date"),
        ([2.0], [D3], "after the last price date"),
        ([0.0], [D1], "positive"),
        ([-1.0], [D1], "positive"),
    ],
)
def test_bad_distributions_raise(
    amounts: list[float], dates: list[pd.Timestamp], message: str
) -> None:
    prices = _prices([100.0, 98.0, 99.0], [D0, D1, D2])
    with pytest.raises(ValidationError, match=message):
        distribution_adjusted(prices, _paid(amounts, dates))


def test_bad_prices_raise() -> None:
    with pytest.raises(ValidationError, match="NaN"):
        distribution_adjusted(_prices([100.0, np.nan, 99.0], [D0, D1, D2]), _paid([], []))
    with pytest.raises(ValidationError, match="strictly positive"):
        distribution_adjusted(_prices([100.0, 0.0, 99.0], [D0, D1, D2]), _paid([], []))
    with pytest.raises(ValidationError, match="at least two"):
        distribution_adjusted(_prices([100.0], [D0]), _paid([], []))


def test_duplicate_or_unsorted_ex_dates_raise() -> None:
    prices = _prices([100.0, 98.0, 99.0], [D0, D1, D2])
    with pytest.raises(ValidationError):
        distribution_adjusted(prices, _paid([1.0, 1.0], [D1, D1]))
    with pytest.raises(ValidationError):
        distribution_adjusted(prices, _paid([1.0, 1.0], [D2, D1]))
