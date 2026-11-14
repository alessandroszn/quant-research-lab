"""Overnight-rate accrual (design 8.5), worked by hand with a constant rate R = 3.6 % ACT/360.

- Friday 2 January 2026 to Monday 5 January: one fixing (Friday) covering 3 days:
  R x 3 / 360 = 0.0003 exactly.
- Monday 5 to Monday 12 January: four fixings of 1 day and Friday's of 3 days:
  (1 + R/360)^4 x (1 + 3R/360) - 1.
- Easter 2026 (5 April): Good Friday 3 April and Easter Monday 6 April are TARGET closing days,
  so Thursday 2 April's fixing covers 5 days: R x 5 / 360.
- Saturday 3 to Tuesday 6 January: Saturday and Sunday use Friday's fixing (2 days), Monday its
  own (1 day): (1 + 2R/360)(1 + R/360) - 1.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from qrlab.core.calendar import target2_calendar
from qrlab.core.errors import ValidationError
from qrlab.core.rates import overnight_returns

R = 0.036
TARGET = target2_calendar(range(2025, 2028))


def _rates(start: str, end: str, value: float = R) -> pd.Series:
    days = TARGET.business_days(date.fromisoformat(start), date.fromisoformat(end))
    return pd.Series(value, index=days)


def _one(start: date, end: date, rates: pd.Series) -> float:
    result = overnight_returns(rates, [start, end], day_count=360, calendar=TARGET)
    assert list(result.index) == [pd.Timestamp(end)]
    return float(result.iloc[0])


def test_a_weekend_is_simple_interest_on_fridays_fixing() -> None:
    rates = _rates("2026-01-02", "2026-01-02")
    assert _one(date(2026, 1, 2), date(2026, 1, 5), rates) == pytest.approx(0.0003, abs=1e-16)


def test_one_week_compounds_daily() -> None:
    rates = _rates("2026-01-05", "2026-01-09")
    expected = (1 + R / 360) ** 4 * (1 + 3 * R / 360) - 1
    assert _one(date(2026, 1, 5), date(2026, 1, 12), rates) == pytest.approx(expected, abs=1e-16)


def test_easter_thursday_covers_five_days() -> None:
    rates = _rates("2026-04-02", "2026-04-02")
    assert _one(date(2026, 4, 2), date(2026, 4, 7), rates) == pytest.approx(R * 5 / 360, abs=1e-16)


def test_a_period_starting_on_a_saturday_uses_fridays_fixing() -> None:
    rates = _rates("2026-01-02", "2026-01-05")
    expected = (1 + 2 * R / 360) * (1 + R / 360) - 1
    assert _one(date(2026, 1, 3), date(2026, 1, 6), rates) == pytest.approx(expected, abs=1e-16)


def test_several_periods_and_a_varying_rate() -> None:
    rates = pd.Series(
        [0.02, 0.03, 0.04],
        index=pd.DatetimeIndex(["2026-01-07", "2026-01-08", "2026-01-09"]),
    )
    result = overnight_returns(
        rates, [date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 12)], day_count=360,
        calendar=TARGET,
    )  # fmt: skip
    assert result.tolist() == pytest.approx(
        [0.02 / 360, (1 + 0.03 / 360) * (1 + 0.04 * 3 / 360) - 1], abs=1e-16
    )
    assert list(result.index) == [pd.Timestamp("2026-01-08"), pd.Timestamp("2026-01-12")]
    assert result.name == "risk_free"


def test_365_day_count() -> None:
    rates = _rates("2026-01-02", "2026-01-02")
    result = overnight_returns(
        rates, [date(2026, 1, 2), date(2026, 1, 5)], day_count=365, calendar=TARGET
    )
    assert float(result.iloc[0]) == pytest.approx(R * 3 / 365, abs=1e-16)


@pytest.mark.parametrize(
    ("boundaries", "rates", "match"),
    [
        ([date(2026, 1, 5), date(2026, 1, 12)], _rates("2026-01-05", "2026-01-06"), "2026-01-07"),
        ([date(2026, 1, 12), date(2026, 1, 5)], _rates("2026-01-05", "2026-01-09"), "increasing"),
        ([date(2026, 1, 5), date(2026, 1, 5)], _rates("2026-01-05", "2026-01-09"), "increasing"),
        ([date(2026, 1, 5)], _rates("2026-01-05", "2026-01-09"), "two"),
        (
            [date(2026, 1, 5), date(2026, 1, 7)],
            _rates("2026-01-05", "2026-01-09").where(lambda s: s.index.day != 6),
            "2026-01-06",
        ),
    ],
)
def test_gaps_and_bad_boundaries_raise(
    boundaries: list[date], rates: pd.Series, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        overnight_returns(rates, boundaries, day_count=360, calendar=TARGET)


def test_day_count_must_be_360_or_365() -> None:
    with pytest.raises(ValidationError, match="day_count"):
        overnight_returns(
            _rates("2026-01-02", "2026-01-02"),
            [date(2026, 1, 2), date(2026, 1, 5)],
            day_count=252,
            calendar=TARGET,
        )
