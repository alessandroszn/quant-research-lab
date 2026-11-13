"""Frequencies and business-day calendars.

Annualisation always takes ``periods_per_year`` as an explicit argument (see
:mod:`qrlab.metrics`). :data:`CONVENTIONAL_PERIODS_PER_YEAR` documents the usual conventions
but is never applied silently, and :func:`infer_frequency` is a diagnostic only.

A :class:`BusinessCalendar` knows which years its holiday list covers; queries outside that
range raise instead of silently treating missing holidays as business days.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from types import MappingProxyType

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError

__all__ = [
    "CONVENTIONAL_PERIODS_PER_YEAR",
    "BusinessCalendar",
    "Frequency",
    "easter_sunday",
    "infer_frequency",
    "require_periods_per_year",
    "target2_calendar",
    "weekday_calendar",
]


class Frequency(Enum):
    """Sampling frequency of a time series.

    The value is the pandas resampling rule; labels are period ends (business day, Friday,
    month end, quarter end, year end).
    """

    DAILY = "B"
    WEEKLY = "W-FRI"
    MONTHLY = "ME"
    QUARTERLY = "QE"
    ANNUAL = "YE"


CONVENTIONAL_PERIODS_PER_YEAR: Mapping[Frequency, int] = MappingProxyType(
    {
        Frequency.DAILY: 252,
        Frequency.WEEKLY: 52,
        Frequency.MONTHLY: 12,
        Frequency.QUARTERLY: 4,
        Frequency.ANNUAL: 1,
    }
)
"""Conventional periods per year. Reference only: functions never default to these values."""

# Median gap between observations, in calendar days, accepted for each frequency.
_GAP_RANGES: tuple[tuple[Frequency, float, float], ...] = (
    (Frequency.DAILY, 1, 4),
    (Frequency.WEEKLY, 6, 8),
    (Frequency.MONTHLY, 27, 32),
    (Frequency.QUARTERLY, 88, 93),
    (Frequency.ANNUAL, 360, 371),
)


def infer_frequency(index: pd.DatetimeIndex) -> Frequency | None:
    """Guess the sampling frequency from the median gap between observations.

    This is a diagnostic (e.g. for warnings and reports). It is never used to choose an
    annualisation factor implicitly.

    Parameters
    ----------
    index
        Observation timestamps, assumed sorted.

    Returns
    -------
    Frequency or None
        The matching frequency, or ``None`` with fewer than two observations or when the median
        gap matches no supported frequency.
    """
    if len(index) < 2:
        return None
    # Divide timedeltas, not raw integers: pandas 3 indexes may be in s, ms, us or ns.
    gaps = np.diff(index.to_numpy()) / np.timedelta64(1, "D")
    median_gap = float(np.median(gaps))
    for frequency, low, high in _GAP_RANGES:
        if low <= median_gap <= high:
            return frequency
    return None


_ACCEPTED_PERIODS: Mapping[Frequency, tuple[float, float]] = MappingProxyType(
    {
        Frequency.DAILY: (250.0, 366.0),  # trading-day and calendar-day conventions
        Frequency.WEEKLY: (50.0, 53.0),
        Frequency.MONTHLY: (12.0, 12.0),
        Frequency.QUARTERLY: (4.0, 4.0),
        Frequency.ANNUAL: (1.0, 1.0),
    }
)


def require_periods_per_year(periods_per_year: float, index: object) -> float:
    """Return ``periods_per_year`` after checking it does not contradict the dates.

    The value is never chosen here: it is only refused when the dates show another frequency.

    Parameters
    ----------
    periods_per_year
        The number of periods per year the caller uses to annualise; a positive finite number.
    index
        The dates of the series being annualised. The check applies only to a
        ``DatetimeIndex`` with at least two dates whose frequency :func:`infer_frequency`
        recognises; otherwise (irregular dates, no dates, one observation) nothing is checked.

    Returns
    -------
    float
        ``periods_per_year`` as a float.

    Raises
    ------
    ValidationError
        If the value is not a positive finite number, or lies outside the accepted range of
        the inferred frequency: daily 250-366, weekly 50-53, monthly 12, quarterly 4,
        annual 1.
    """
    value: object = periods_per_year
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValidationError(f"periods_per_year must be a positive number, got {value!r}")
    if not (math.isfinite(value) and value > 0):
        raise ValidationError(f"periods_per_year must be positive and finite, got {value!r}")
    number = float(value)
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return number
    dates = index.sort_values()
    frequency = infer_frequency(dates)
    if frequency is None:
        return number
    low, high = _ACCEPTED_PERIODS[frequency]
    if not low <= number <= high:
        gap = float(np.median(np.diff(dates.to_numpy()) / np.timedelta64(1, "D")))
        raise ValidationError(
            f"periods_per_year is {number:g}, but the dates are {frequency.name.lower()} "
            f"(median gap {gap:.0f} days): use {CONVENTIONAL_PERIODS_PER_YEAR[frequency]}"
        )
    return number


def easter_sunday(year: int) -> date:
    """Return the date of Western (Gregorian) Easter Sunday.

    Uses the anonymous Gregorian algorithm (Meeus/Jones/Butcher).

    Parameters
    ----------
    year
        Gregorian calendar year, 1583 or later.

    Returns
    -------
    datetime.date
        Easter Sunday of ``year``.
    """
    if year < 1583:
        raise ValidationError(f"Gregorian Easter is defined from 1583, got {year}")
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


@dataclass(frozen=True)
class BusinessCalendar:
    """Monday-to-Friday calendar minus a set of holidays.

    Parameters
    ----------
    name
        Human-readable identifier, e.g. ``"TARGET2"``.
    holidays
        Closing days that fall inside ``years``.
    years
        Years covered by ``holidays`` (a contiguous range). Queries outside it raise. ``None``
        means the calendar is valid for every year, which is only correct if the holiday list
        really is complete (e.g. a calendar with no holidays).
    """

    name: str
    holidays: frozenset[date]
    years: range | None

    def __post_init__(self) -> None:
        """Validate holidays and coverage."""
        if self.years is not None and (self.years.step != 1 or len(self.years) == 0):
            raise ValidationError(f"{self.name}: years must be a non-empty range with step 1")
        for holiday in self.holidays:
            if isinstance(holiday, datetime) or not isinstance(holiday, date):
                raise ValidationError(f"{self.name}: holidays must be datetime.date objects")
            if self.years is not None and holiday.year not in self.years:
                raise ValidationError(
                    f"{self.name}: holiday {holiday} is outside the covered years "
                    f"{_span(self.years)}"
                )

    def is_business_day(self, day: date) -> bool:
        """Return whether ``day`` is a business day (a datetime is reduced to its date)."""
        day = _as_date(day)
        self._check_covered(day)
        return day.weekday() < 5 and day not in self.holidays

    def business_days(self, start: date, end: date) -> pd.DatetimeIndex:
        """Return business days from ``start`` to ``end``, both inclusive, in increasing order."""
        start, end = _as_date(start), _as_date(end)
        if start > end:
            raise ValidationError(f"{self.name}: start {start} is after end {end}")
        self._check_covered(start)
        self._check_covered(end)
        days = pd.bdate_range(start, end)
        if not self.holidays:
            return days
        closed = pd.DatetimeIndex(sorted(self.holidays))
        return days[~days.isin(closed)]

    def _check_covered(self, day: date) -> None:
        if self.years is not None and day.year not in self.years:
            raise ValidationError(f"{self.name}: calendar covers {_span(self.years)}, not {day}")


def weekday_calendar() -> BusinessCalendar:
    """Return a Monday-to-Friday calendar without holidays, valid for every year."""
    return BusinessCalendar(name="weekdays", holidays=frozenset(), years=None)


def target2_calendar(years: range) -> BusinessCalendar:
    """Return the TARGET2 (euro area payment system) calendar for the given years.

    Closing days: 1 January, Good Friday, Easter Monday, 1 May, 25 and 26 December. This set
    applies from 2002; earlier years had additional closing days and are rejected.

    Parameters
    ----------
    years
        Contiguous range of years, e.g. ``range(2002, 2031)``.
    """
    if years.step != 1 or len(years) == 0:
        raise ValidationError("years must be a non-empty range with step 1")
    if years.start < 2002:
        raise ValidationError("the TARGET2 closing-day set used here applies from 2002 onwards")
    holidays: set[date] = set()
    for year in years:
        easter = easter_sunday(year)
        holidays |= {
            date(year, 1, 1),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            date(year, 5, 1),
            date(year, 12, 25),
            date(year, 12, 26),
        }
    return BusinessCalendar(name="TARGET2", holidays=frozenset(holidays), years=years)


def _span(years: range) -> str:
    return f"{years.start}-{years.stop - 1}"


def _as_date(day: date) -> date:
    return day.date() if isinstance(day, datetime) else day
