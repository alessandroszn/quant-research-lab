"""Tracking difference and tracking error. All series synthetic.

Hand values (design note 2.5):

- fund 100 -> 109.8 and index 100 -> 110 over 365 days: TD -0.20 %, annualised -0.20 % (exponent
  365 / 365 = 1); with TER 0.20 %, TD + TER = 0;
- monthly return differences 0.1 %, -0.1 %, 0.1 %, -0.1 % (index flat): TE =
  sqrt(4e-6 / 3) x sqrt(12) = 0.40 %;
- six months of data: the period difference is given, never annualised.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.core.money import Currency
from qrlab.data.user_csv import PriceType
from qrlab.lookthrough.tracking import (
    TrackingSeries,
    td_vs_ter,
    tracking_difference,
    tracking_error,
)
from qrlab.metrics.errors import UndefinedMetricError

EUR, USD = Currency("EUR"), Currency("USD")


def _series(
    levels: dict[date, float],
    price_type: PriceType = PriceType.TOTAL_RETURN,
    currency: Currency = EUR,
    hedged_to: Currency | None = None,
) -> TrackingSeries:
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in levels])
    return TrackingSeries(
        pd.Series(list(levels.values()), index=index), price_type, currency, hedged_to
    )


def test_one_year_hand_example() -> None:
    dates = (date(2025, 6, 30), date(2026, 6, 30))
    fund = _series(dict(zip(dates, (100.0, 109.8), strict=True)), PriceType.NAV)
    index = _series(dict(zip(dates, (100.0, 110.0), strict=True)))
    td = tracking_difference(fund, index)
    assert td.difference == pytest.approx(-0.002)
    assert td.annualised == pytest.approx(-0.002)
    assert (td.start, td.end) == dates
    assert td.fund_return == pytest.approx(0.098)
    assert td.index_return == pytest.approx(0.10)
    assert td_vs_ter(td.difference, Decimal("0.0020")) == pytest.approx(0.0, abs=1e-12)


def test_short_period_is_never_annualised() -> None:
    dates = (date(2026, 1, 1), date(2026, 6, 30))
    td = tracking_difference(
        _series(dict(zip(dates, (100.0, 101.0), strict=True))),
        _series(dict(zip(dates, (100.0, 101.5), strict=True))),
    )
    assert td.annualised is None
    assert td.difference == pytest.approx(-0.005)
    assert td.by_year == {}


def test_two_year_annualisation() -> None:
    dates = (date(2024, 6, 30), date(2026, 6, 30))  # 730 days
    td = tracking_difference(
        _series(dict(zip(dates, (100.0, 121.0), strict=True))),
        _series(dict(zip(dates, (100.0, 123.21), strict=True))),
    )
    assert td.annualised == pytest.approx(1.1 - 1.11)  # sqrt(1.21) - sqrt(1.2321)


def test_calendar_years_are_complete_years_only() -> None:
    levels = {
        date(2023, 6, 30): (100.0, 100.0),
        date(2023, 12, 29): (104.0, 104.5),  # 2023 starts mid-year: no 2023 figure
        date(2024, 12, 31): (110.0, 111.0),
        date(2025, 12, 31): (121.0, 122.0),
        date(2026, 6, 30): (125.0, 126.0),  # 2026 is not complete
    }
    fund = _series({d: v[0] for d, v in levels.items()})
    index = _series({d: v[1] for d, v in levels.items()})
    by_year = tracking_difference(fund, index).by_year
    assert set(by_year) == {2024, 2025}
    assert by_year[2024] == pytest.approx(110 / 104 - 111 / 104.5)
    assert by_year[2025] == pytest.approx(121 / 110 - 122 / 111)


def test_tracking_error_hand_example() -> None:
    dates = [date(2026, m, 28) for m in range(1, 6)]
    fund_levels = [100.0]
    for diff in (0.001, -0.001, 0.001, -0.001):
        fund_levels.append(fund_levels[-1] * (1 + diff))
    fund = _series(dict(zip(dates, fund_levels, strict=True)))
    index = _series(dict.fromkeys(dates, 100.0))
    te = tracking_error(fund, index, periods_per_year=12)
    assert te == pytest.approx(math.sqrt(4e-6 / 3) * math.sqrt(12))
    assert te == pytest.approx(0.004)


def test_tracking_error_needs_two_differences() -> None:
    dates = (date(2026, 1, 31), date(2026, 2, 28))
    fund = _series(dict(zip(dates, (100.0, 101.0), strict=True)))
    with pytest.raises(UndefinedMetricError):
        tracking_error(fund, fund, periods_per_year=12)


def test_series_must_be_comparable() -> None:
    dates = (date(2026, 1, 31), date(2026, 2, 28))
    levels = dict(zip(dates, (100.0, 101.0), strict=True))
    index = _series(levels)
    with pytest.raises(ValidationError, match="NAV or total return"):
        tracking_difference(_series(levels, PriceType.PRICE), index)
    with pytest.raises(ValidationError, match="index series must be total return"):
        tracking_difference(_series(levels), _series(levels, PriceType.NAV))
    with pytest.raises(ValidationError, match="currency effect"):
        tracking_difference(_series(levels, currency=USD), index)
    with pytest.raises(ValidationError, match="hedged to EUR"):
        tracking_error(_series(levels, currency=USD, hedged_to=EUR),
                       _series(levels, currency=USD), periods_per_year=12)  # fmt: skip
    hedged = tracking_difference(
        _series(levels, currency=USD, hedged_to=EUR), _series(levels, currency=USD, hedged_to=EUR)
    )
    assert hedged.difference == 0.0
    other_dates = _series({date(2026, 1, 30): 100.0, date(2026, 2, 28): 101.0})
    with pytest.raises(AlignmentError):
        tracking_difference(_series(levels), other_dates)


def test_levels_are_validated() -> None:
    with pytest.raises(ValidationError, match="positive"):
        _series({date(2026, 1, 31): 100.0, date(2026, 2, 28): 0.0})
    with pytest.raises(ValidationError):
        _series({date(2026, 1, 31): 100.0, date(2026, 2, 28): float("nan")})
    single = _series({date(2026, 1, 31): 100.0})
    with pytest.raises(UndefinedMetricError, match="two dates"):
        tracking_difference(single, single)
