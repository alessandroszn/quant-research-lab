"""Tracking difference and tracking error of a fund against its index.

Conventions (design note 2.5):

- the fund series is NAV or total return, and the index series is total return (net
  dividends). A price-only series leaves dividends out and is refused;
- fund and index are in the same currency with the same hedging. Otherwise a currency effect
  would be read as tracking, so the calculation raises;
- both series share exactly the same dates (no silent alignment) and have no missing values;
- the tracking difference over the period is the fund return minus the index return. When the
  period is at least 365 days, it is also given annualised: the difference of the
  geometrically annualised returns, with exponent ``365 / days``. It is never annualised from
  less than a year;
- calendar-year differences cover only complete years: from the last observation of year
  ``y - 1`` to the last observation of year ``y``, which must fall in December;
- tracking error is the annualised sample standard deviation of the periodic return
  differences (:func:`qrlab.metrics.relative.tracking_error`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.core.returns import ReturnKind, prices_to_returns
from qrlab.core.series import NanPolicy, require_same_index, validate_series
from qrlab.data.user_csv import PriceType
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.relative import tracking_error as _tracking_error

__all__ = [
    "ONE_YEAR_DAYS",
    "TrackingDifference",
    "TrackingSeries",
    "td_vs_ter",
    "tracking_difference",
    "tracking_error",
]

ONE_YEAR_DAYS = 365
_FUND_TYPES = frozenset({PriceType.NAV, PriceType.TOTAL_RETURN})


@dataclass(frozen=True)
class TrackingSeries:
    """Levels of a fund or an index, with what they measure.

    Parameters
    ----------
    levels
        Positive levels (NAV, total-return price or index level) on a validated date index,
        without missing values.
    price_type
        What the levels measure.
    currency
        Currency of the levels.
    hedged_to
        Hedge currency of a hedged share class or a hedged index, else ``None``.
    """

    levels: pd.Series
    price_type: PriceType
    currency: Currency
    hedged_to: Currency | None

    def __post_init__(self) -> None:
        """Validate the levels."""
        levels = validate_series(self.levels, nan_policy=NanPolicy.RAISE, name="levels")
        if not (levels > 0).all():
            raise ValidationError("levels must be positive")
        object.__setattr__(self, "levels", levels)


@dataclass(frozen=True)
class TrackingDifference:
    """Fund return minus index return over the common period."""

    start: date
    end: date
    fund_return: float
    index_return: float
    difference: float
    annualised: float | None  # None when the period is shorter than a year
    by_year: Mapping[int, float]


def tracking_difference(fund: TrackingSeries, index: TrackingSeries) -> TrackingDifference:
    """Return the tracking difference of ``fund`` against ``index``."""
    _require_comparable(fund, index)
    f, i = fund.levels, index.levels
    if len(f) < 2:
        raise UndefinedMetricError("tracking difference needs at least two dates")
    start, end = f.index[0].date(), f.index[-1].date()
    fund_return = float(f.iloc[-1] / f.iloc[0]) - 1.0
    index_return = float(i.iloc[-1] / i.iloc[0]) - 1.0
    days = (end - start).days
    annualised = None
    if days >= ONE_YEAR_DAYS:
        exponent = ONE_YEAR_DAYS / days
        annualised = (1.0 + fund_return) ** exponent - (1.0 + index_return) ** exponent
    return TrackingDifference(
        start=start,
        end=end,
        fund_return=fund_return,
        index_return=index_return,
        difference=fund_return - index_return,
        annualised=annualised,
        by_year=_by_year(f, i),
    )


def tracking_error(
    fund: TrackingSeries, index: TrackingSeries, *, periods_per_year: float
) -> float:
    """Annualised tracking error of periodic simple returns (``periods_per_year`` explicit)."""
    _require_comparable(fund, index)
    fund_returns = prices_to_returns(fund.levels, kind=ReturnKind.SIMPLE).iloc[1:]
    index_returns = prices_to_returns(index.levels, kind=ReturnKind.SIMPLE).iloc[1:]
    return _tracking_error(fund_returns, index_returns, periods_per_year=periods_per_year)


def td_vs_ter(annualised_difference: float, ter: Decimal) -> float:
    """Return TD + TER: 0 if the fund lost exactly its TER, negative for hidden costs."""
    return annualised_difference + float(ter)


def _require_comparable(fund: TrackingSeries, index: TrackingSeries) -> None:
    if fund.price_type not in _FUND_TYPES:
        raise ValidationError("the fund series must be NAV or total return (dividends included)")
    if index.price_type is not PriceType.TOTAL_RETURN:
        raise ValidationError("the index series must be total return")
    if (fund.currency, fund.hedged_to) != (index.currency, index.hedged_to):
        raise ValidationError(
            f"fund in {fund.currency.code} (hedged to {_code(fund.hedged_to)}) and index in "
            f"{index.currency.code} (hedged to {_code(index.hedged_to)}): a currency effect "
            "would be read as tracking"
        )
    require_same_index(fund.levels, index.levels)


def _code(currency: Currency | None) -> str:
    return "none" if currency is None else currency.code


def _by_year(fund: pd.Series, index: pd.Series) -> dict[int, float]:
    last: dict[int, pd.Timestamp] = {}
    for stamp in fund.index:
        last[stamp.year] = stamp  # the index is sorted, so the last write is the year's last date
    result: dict[int, float] = {}
    for year, end in last.items():
        if year - 1 not in last or end.month != 12:
            continue
        start = last[year - 1]
        fund_year = float(fund[end] / fund[start]) - 1.0
        index_year = float(index[end] / index[start]) - 1.0
        result[year] = fund_year - index_year
    return result
