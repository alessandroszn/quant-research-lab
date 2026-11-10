"""Valuation of a ledger in the base currency with explicit staleness limits.

Prices and FX rates may be carried forward from an earlier date only within an explicit
maximum age; every carried-forward value is recorded, and anything older raises. Valuation
uses *price* or *NAV* series: total-return series are refused, because dividends are booked
as cash in the ledger and would otherwise be counted twice.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from itertools import pairwise

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.core.series import NanPolicy, validate_series
from qrlab.data.errors import DataNotFoundError
from qrlab.data.provenance import Dataset, Unit
from qrlab.data.user_csv import PriceData, PriceType
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.ledger import LedgerHistory, ToBase

__all__ = ["EcbConverter", "PriceSeries", "Valuation", "value_portfolio"]

_EUR = Currency("EUR")


@dataclass(frozen=True)
class PriceSeries:
    """Prices of one instrument in one currency (NaN = no price that day).

    Total-return series are refused: see the module docstring.
    """

    prices: pd.Series
    currency: Currency
    price_type: PriceType

    def __post_init__(self) -> None:
        """Validate the series and refuse total-return prices."""
        if self.price_type is PriceType.TOTAL_RETURN:
            raise ValidationError(
                "total-return series cannot value a ledger (dividends are already booked as cash)"
            )
        object.__setattr__(
            self, "prices", validate_series(self.prices, nan_policy=NanPolicy.KEEP, name="prices")
        )

    @classmethod
    def from_price_data(cls, data: PriceData, column: str) -> PriceSeries:
        """Take one instrument column from a parsed user price file."""
        if column not in data.dataset.data.columns:
            raise DataNotFoundError(f"no column {column!r} in {data.dataset.provenance.dataset}")
        currency = data.dataset.currency
        if currency is None:  # pragma: no cover - PriceData always carries a currency
            raise ValidationError("price data without a currency")
        return cls(data.dataset.data[column], currency, data.price_types[column])

    def price_on(self, day: date, max_age_days: int) -> tuple[Decimal, date]:
        """Latest non-missing price on or before ``day`` within ``max_age_days``."""
        return _latest(self.prices, day, max_age_days, label="price")


class EcbConverter:
    """Convert amounts to a base currency with ECB reference rates (``ToBase`` protocol).

    Rates are units of currency per 1 EUR. A non-EUR base uses the explicit cross rate via
    EUR. Rates may be carried forward up to ``max_age_days``; every carried-forward use is
    recorded in :attr:`stale_uses`.

    Parameters
    ----------
    fx
        ECB FX dataset (``Unit.FX_RATE``, currency EUR), e.g. from ``qrlab.data.parse_ecb_fx``.
    base
        Target currency.
    max_age_days
        Oldest acceptable rate, in calendar days before the conversion date.
    """

    def __init__(self, fx: Dataset, *, base: Currency, max_age_days: int) -> None:
        if fx.unit is not Unit.FX_RATE or fx.currency != _EUR:
            raise ValidationError("EcbConverter needs an FX dataset quoted per 1 EUR")
        _check_age(max_age_days, "max_age_days")
        self._fx = fx.data
        self._base = base
        self._max_age = max_age_days
        self._stale: list[tuple[Currency, date, date]] = []

    @property
    def stale_uses(self) -> tuple[tuple[Currency, date, date], ...]:
        """(currency, requested date, date of the rate used) for every carried-forward rate."""
        return tuple(self._stale)

    def __call__(self, amount: Money, on: date) -> Money:
        """Convert ``amount`` to the base currency at the rate of ``on``."""
        in_eur = amount.amount / self._rate(amount.currency, on)
        return Money(in_eur * self._rate(self._base, on), self._base)

    def _rate(self, currency: Currency, on: date) -> Decimal:
        if currency == _EUR:
            return Decimal(1)
        if currency.code not in self._fx.columns:
            raise DataNotFoundError(f"no ECB rate for {currency.code}")
        rate, used = _latest(self._fx[currency.code], on, self._max_age, label=f"{currency} rate")
        if used != on:
            self._stale.append((currency, on, used))
        return rate


@dataclass(frozen=True)
class Valuation:
    """Portfolio values in the base currency on each valuation date (exact ``Decimal``)."""

    base: Currency
    totals: Mapping[date, Decimal]
    positions: Mapping[date, Mapping[tuple[str, Isin], Decimal]]
    cash: Mapping[date, Decimal]
    stale_prices: tuple[tuple[Isin, date, date], ...] = field(default_factory=tuple)

    def series(self) -> pd.Series:
        """Total value as a float series indexed by date (for analytics)."""
        index = pd.DatetimeIndex([pd.Timestamp(d) for d in self.totals])
        return pd.Series([float(v) for v in self.totals.values()], index=index, name="value")


def value_portfolio(
    history: LedgerHistory,
    prices: Mapping[Isin, PriceSeries],
    to_base: ToBase,
    *,
    dates: Sequence[date],
    max_price_age_days: int,
) -> Valuation:
    """Value the ledger on each date: units x price plus cash, converted to the base currency.

    Parameters
    ----------
    history
        Result of :func:`qrlab.portfolio.ledger.replay`.
    prices
        Price series per instrument; the currency must match the position's currency.
    to_base
        Converter to ``history.base`` (e.g. :class:`EcbConverter`).
    dates
        Strictly increasing valuation dates.
    max_price_age_days
        Oldest acceptable price, in calendar days before the valuation date.
    """
    _check_age(max_price_age_days, "max_price_age_days")
    if any(b <= a for a, b in pairwise(dates)):
        raise ValidationError("valuation dates must be strictly increasing")
    totals: dict[date, Decimal] = {}
    positions: dict[date, dict[tuple[str, Isin], Decimal]] = {}
    cash: dict[date, Decimal] = {}
    stale: list[tuple[Isin, date, date]] = []
    for day in dates:
        state = history.state_on(day)
        values: dict[tuple[str, Isin], Decimal] = {}
        for key, position in state.positions.items():
            isin = key[1]
            if isin not in prices:
                raise DataNotFoundError(f"no price series for {isin.code}")
            series = prices[isin]
            if series.currency != position.currency:
                raise ValidationError(
                    f"{isin.code}: price currency {series.currency} differs from "
                    f"position currency {position.currency}"
                )
            price, used = series.price_on(day, max_price_age_days)
            if used != day:
                stale.append((isin, day, used))
            local = Money(position.quantity * price, position.currency)
            values[key] = _base(to_base(local, day), history.base)
        cash_total = sum(
            (
                _base(to_base(Money(balance, ccy), day), history.base)
                for (_, ccy), balance in state.cash.items()
            ),
            Decimal(0),
        )
        positions[day] = values
        cash[day] = cash_total
        totals[day] = cash_total + sum(values.values(), Decimal(0))
    return Valuation(history.base, totals, positions, cash, tuple(stale))


def _latest(series: pd.Series, day: date, max_age_days: int, *, label: str) -> tuple[Decimal, date]:
    available = series.loc[: pd.Timestamp(day)].dropna()
    if available.empty:
        raise DataNotFoundError(f"no {label} on or before {day}")
    used = pd.Timestamp(available.index[-1]).date()
    age = (day - used).days
    if age > max_age_days:
        raise DataNotFoundError(
            f"latest {label} for {day} is from {used}, older than {max_age_days} days"
        )
    value = float(available.to_numpy()[-1])
    if not np.isfinite(value) or value <= 0:  # pragma: no cover - validated upstream
        raise ValidationError(f"invalid {label} {value} on {used}")
    # repr() gives the shortest decimal string that round-trips: the published digits.
    return Decimal(repr(value)), used


def _base(amount: object, base: Currency) -> Decimal:
    if not isinstance(amount, Money) or amount.currency != base:
        raise ValidationError(f"converter must return Money in the base currency {base}")
    return amount.amount


def _check_age(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValidationError(f"{name} must be a non-negative int, got {value!r}")
