"""Frequencies, Easter computus and business-day calendars.

Reference values: Easter Sunday dates from published tables; TARGET2 closing days from the
ECB (New Year, Good Friday, Easter Monday, 1 May, 25 and 26 December).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

import pandas as pd
import pytest

from qrlab.core.calendar import (
    CONVENTIONAL_PERIODS_PER_YEAR,
    BusinessCalendar,
    Frequency,
    easter_sunday,
    infer_frequency,
    target2_calendar,
    weekday_calendar,
)
from qrlab.core.errors import ValidationError


# --------------------------------------------------------------------------- frequencies
def test_conventional_periods_per_year() -> None:
    assert CONVENTIONAL_PERIODS_PER_YEAR == {
        Frequency.DAILY: 252,
        Frequency.WEEKLY: 52,
        Frequency.MONTHLY: 12,
        Frequency.QUARTERLY: 4,
        Frequency.ANNUAL: 1,
    }


def test_conventional_table_is_read_only() -> None:
    with pytest.raises(TypeError):
        CONVENTIONAL_PERIODS_PER_YEAR[Frequency.DAILY] = 260  # type: ignore[index]


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (pd.bdate_range("2026-01-01", periods=30), Frequency.DAILY),
        (pd.date_range("2026-01-02", periods=20, freq="W-FRI"), Frequency.WEEKLY),
        (pd.date_range("2020-01-31", periods=24, freq="ME"), Frequency.MONTHLY),
        (pd.date_range("2010-03-31", periods=12, freq="QE"), Frequency.QUARTERLY),
        (pd.date_range("2000-12-31", periods=10, freq="YE"), Frequency.ANNUAL),
    ],
    ids=["daily", "weekly", "monthly", "quarterly", "annual"],
)
def test_infer_frequency(index: pd.DatetimeIndex, expected: Frequency) -> None:
    assert infer_frequency(index) is expected


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_infer_frequency_is_independent_of_index_resolution(
    unit: Literal["s", "ms", "us", "ns"],
) -> None:
    # Regression: the first version divided raw integers by nanoseconds per day, which broke
    # on pandas 3, whose default resolution is microseconds.
    index = pd.date_range("2020-01-31", periods=24, freq="ME").as_unit(unit)
    assert infer_frequency(index) is Frequency.MONTHLY


def test_infer_frequency_tolerates_holiday_gaps() -> None:
    index = pd.bdate_range("2026-03-30", "2026-04-10").drop(
        pd.DatetimeIndex(["2026-04-03", "2026-04-06"])
    )
    assert infer_frequency(index) is Frequency.DAILY


@pytest.mark.parametrize(
    "index",
    [
        pd.DatetimeIndex([]),
        pd.DatetimeIndex(["2026-01-05"]),
        pd.date_range("2026-01-01", periods=10, freq="14D"),  # fortnightly: unsupported
    ],
    ids=["empty", "single", "fortnightly"],
)
def test_infer_frequency_returns_none_when_unknown(index: pd.DatetimeIndex) -> None:
    assert infer_frequency(index) is None


# --------------------------------------------------------------------------- Easter
@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2000, date(2000, 4, 23)),
        (2008, date(2008, 3, 23)),
        (2011, date(2011, 4, 24)),
        (2019, date(2019, 4, 21)),
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2038, date(2038, 4, 25)),  # latest possible date
        (2285, date(2285, 3, 22)),  # earliest possible date
    ],
)
def test_easter_sunday(year: int, expected: date) -> None:
    assert easter_sunday(year) == expected


def test_easter_sunday_rejects_pre_gregorian_years() -> None:
    with pytest.raises(ValidationError):
        easter_sunday(1582)


# --------------------------------------------------------------------------- TARGET2
def test_target2_closing_days_2026() -> None:
    cal = target2_calendar(range(2026, 2027))
    assert cal.holidays == frozenset(
        {
            date(2026, 1, 1),
            date(2026, 4, 3),  # Good Friday
            date(2026, 4, 6),  # Easter Monday
            date(2026, 5, 1),
            date(2026, 12, 25),
            date(2026, 12, 26),
        }
    )


def test_target2_business_days_in_2026() -> None:
    # 2026 has 261 weekdays; five closing days fall on weekdays (26 Dec is a Saturday).
    cal = target2_calendar(range(2026, 2027))
    days = cal.business_days(date(2026, 1, 1), date(2026, 12, 31))
    assert len(days) == 256
    assert pd.Timestamp("2026-04-03") not in days
    assert pd.Timestamp("2026-04-02") in days


def test_target2_rejects_years_before_2002() -> None:
    with pytest.raises(ValidationError, match="2002"):
        target2_calendar(range(2001, 2003))


def test_target2_rejects_empty_or_stepped_ranges() -> None:
    with pytest.raises(ValidationError):
        target2_calendar(range(2026, 2026))
    with pytest.raises(ValidationError):
        target2_calendar(range(2020, 2030, 2))


# --------------------------------------------------------------------------- calendar behaviour
def test_is_business_day() -> None:
    cal = target2_calendar(range(2026, 2027))
    assert cal.is_business_day(date(2026, 4, 2))
    assert not cal.is_business_day(date(2026, 4, 3))  # holiday
    assert not cal.is_business_day(date(2026, 4, 4))  # Saturday


def test_is_business_day_accepts_timestamps() -> None:
    cal = target2_calendar(range(2026, 2027))
    assert not cal.is_business_day(pd.Timestamp("2026-04-03 15:30"))
    assert not cal.is_business_day(datetime(2026, 4, 3, 9, 0))


def test_queries_outside_coverage_raise() -> None:
    cal = target2_calendar(range(2026, 2027))
    with pytest.raises(ValidationError, match="covers"):
        cal.is_business_day(date(2027, 1, 1))
    with pytest.raises(ValidationError, match="covers"):
        cal.business_days(date(2025, 12, 1), date(2026, 1, 31))


def test_business_days_is_inclusive_and_ordered() -> None:
    cal = weekday_calendar()
    days = cal.business_days(date(2026, 1, 2), date(2026, 1, 5))  # Fri .. Mon
    assert list(days) == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-05")]


def test_business_days_start_after_end_raises() -> None:
    with pytest.raises(ValidationError):
        weekday_calendar().business_days(date(2026, 1, 5), date(2026, 1, 2))


def test_weekday_calendar_is_unbounded() -> None:
    cal = weekday_calendar()
    assert cal.years is None
    assert cal.is_business_day(date(1990, 1, 1))  # a Monday


def test_custom_calendar_validates_holidays_within_coverage() -> None:
    with pytest.raises(ValidationError, match="outside"):
        BusinessCalendar(name="x", holidays=frozenset({date(2027, 1, 1)}), years=range(2026, 2027))


def test_custom_calendar_rejects_datetimes_as_holidays() -> None:
    with pytest.raises(ValidationError, match="date"):
        BusinessCalendar(name="x", holidays=frozenset({datetime(2026, 1, 1)}), years=None)


@pytest.mark.parametrize("years", [range(2026, 2026), range(2020, 2030, 2)])
def test_custom_calendar_rejects_empty_or_stepped_years(years: range) -> None:
    with pytest.raises(ValidationError, match="step 1"):
        BusinessCalendar(name="x", holidays=frozenset(), years=years)
