r"""Returns from an overnight rate (e.g. €STR), period by period.

An overnight rate :math:`R_b` is quoted per year for business day :math:`b` and applies until
the next business day. The return over a period :math:`(t_{k-1}, t_k]` is

.. math::

    r_k = \prod_b \left(1 + R_b \frac{n_b}{D}\right) - 1,

over the business days :math:`b` whose interest falls in :math:`[t_{k-1}, t_k)`. Here
:math:`n_b` is the number of calendar days the fixing applies to within the period and
:math:`D` the day count (360 for €STR, ACT/360). This is the convention of the ECB's compounded
€STR averages: simple interest over a weekend or holiday, compounding from one business day to
the next. A calendar day before the period's first business day (a period starting on a
Saturday) uses the last fixing before it.

The rate for day :math:`T` is published on the next business day, so a return over a past
period uses only rates published by one business day after its end: a realised risk-free return
for a historical Sharpe ratio involves no look-ahead.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from datetime import date, timedelta

import numpy as np
import pandas as pd

from qrlab.core.calendar import BusinessCalendar
from qrlab.core.errors import ValidationError

__all__ = ["overnight_returns"]


def overnight_returns(
    rates: pd.Series,
    boundaries: Sequence[date] | pd.DatetimeIndex,
    *,
    day_count: int,
    calendar: BusinessCalendar,
) -> pd.Series:
    """Return the compounded overnight return of each period between ``boundaries``.

    Parameters
    ----------
    rates
        Annual rates in decimals, indexed by business day. A business day used by a period
        must have a finite rate: nothing is filled.
    boundaries
        Strictly increasing dates; each consecutive pair is one period ``(start, end]``.
    day_count
        360 (ACT/360, e.g. €STR) or 365 (ACT/365).
    calendar
        The business days of the rate (TARGET for €STR); it must cover the periods.

    Returns
    -------
    pandas.Series
        One simple return per period, indexed by the period end, named ``"risk_free"``.
    """
    if day_count not in (360, 365):
        raise ValidationError(f"day_count must be 360 or 365, got {day_count!r}")
    ends = [pd.Timestamp(d).normalize() for d in boundaries]
    if len(ends) < 2:
        raise ValidationError("give at least two boundaries (one period)")
    if any(b <= a for a, b in itertools.pairwise(ends)):
        raise ValidationError("boundaries must be strictly increasing")
    fixings = rates.copy()
    fixings.index = pd.DatetimeIndex(fixings.index).normalize()
    business = calendar.business_days(ends[0].date() - timedelta(days=14), ends[-1].date())
    values = []
    for start, end in itertools.pairwise(ends):
        days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
        positions = business.searchsorted(days, side="right") - 1
        fixing_days, counts = np.unique(business[positions].to_numpy(), return_counts=True)
        growth = 1.0
        for raw_day, count in zip(fixing_days, counts, strict=True):
            fixing_day = pd.Timestamp(raw_day)
            rate = fixings.get(fixing_day)
            if rate is None or not pd.notna(rate):
                raise ValidationError(f"no rate for business day {fixing_day.date()}")
            growth *= 1.0 + float(rate) * int(count) / day_count
        values.append(growth - 1.0)
    return pd.Series(values, index=pd.DatetimeIndex(ends[1:]), name="risk_free")
