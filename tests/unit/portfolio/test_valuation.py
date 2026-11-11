"""Valuation in the base currency with explicit staleness limits. All data synthetic.

Toy portfolio prices 50, 55, 52, 54 on D0..D3 give values 9,990; 15,490; 15,290; 15,480
(cash plus units x price), exactly as in the design note.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.errors import DataNotFoundError
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.user_csv import PriceData, PriceType
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import TransactionKind
from qrlab.portfolio.valuation import EcbConverter, PriceSeries, value_portfolio
from support.portfolio import D0, D1, D2, D3, EUR, USD, X, Y, eur_only, money, toy_transactions, tx

K = TransactionKind
GBP = Currency("GBP")


def _prov(name: str = "prices") -> Provenance:
    return Provenance(
        source="test",
        dataset=name,
        url="file:synthetic.csv",
        retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        size_bytes=1,
        terms="synthetic",
    )


def _series(values: dict[date, float], currency: Currency = EUR) -> PriceSeries:
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in values])
    return PriceSeries(pd.Series(list(values.values()), index=index), currency, PriceType.PRICE)


def _fx(rows: dict[date, dict[str, float]]) -> Dataset:
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in rows])
    frame = pd.DataFrame(list(rows.values()), index=index)
    return Dataset(
        data=frame,
        provenance=_prov("eurofxref-hist"),
        frequency=Frequency.DAILY,
        unit=Unit.FX_RATE,
        return_kind=None,
        currency=EUR,
        availability="synthetic",
        notes=(),
    )


TOY_PRICES = {X: _series({D0: 50.0, D1: 55.0, D2: 52.0, D3: 54.0})}


# --------------------------------------------------------------------------- toy portfolio
def test_toy_valuation_hand_values() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    valuation = value_portfolio(
        history, TOY_PRICES, eur_only, dates=[D0, D1, D2, D3], max_price_age_days=0
    )
    assert valuation.totals == {
        D0: Decimal(9990),
        D1: Decimal(15490),
        D2: Decimal(15290),
        D3: Decimal(15480),
    }
    assert valuation.cash[D3] == Decimal(12780)
    assert valuation.positions[D3] == {("main", X): Decimal(2700)}
    assert valuation.stale_prices == ()
    series = valuation.series()
    assert series.name == "value"
    assert series.tolist() == [9990.0, 15490.0, 15290.0, 15480.0]


def test_price_carried_forward_within_limit_is_recorded() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    later = date(2026, 1, 5)  # no price on 5 January: the 2 January price is 3 days old
    valuation = value_portfolio(history, TOY_PRICES, eur_only, dates=[later], max_price_age_days=3)
    assert valuation.totals[later] == Decimal(9990)
    ((isin, requested, used),) = valuation.stale_prices
    assert (isin, requested, used) == (X, later, D0)


def test_price_older_than_limit_raises() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    with pytest.raises(DataNotFoundError, match="older than 2 days"):
        value_portfolio(
            history, TOY_PRICES, eur_only, dates=[date(2026, 1, 5)], max_price_age_days=2
        )


def test_nan_price_is_skipped_not_used() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    prices = {X: _series({D0: 50.0, D1: float("nan")})}
    with pytest.raises(DataNotFoundError):
        value_portfolio(history, prices, eur_only, dates=[D1], max_price_age_days=7)


def test_missing_price_series_raises() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    with pytest.raises(DataNotFoundError, match=X.code):
        value_portfolio(history, {}, eur_only, dates=[D0], max_price_age_days=0)


def test_price_currency_must_match_position() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    prices = {X: _series({D0: 50.0}, currency=USD)}
    with pytest.raises(ValidationError, match="currency"):
        value_portfolio(history, prices, eur_only, dates=[D0], max_price_age_days=0)


def test_dates_must_be_increasing() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    with pytest.raises(ValidationError, match="increasing"):
        value_portfolio(history, TOY_PRICES, eur_only, dates=[D1, D0], max_price_age_days=0)


# --------------------------------------------------------------------------- price series
def test_total_return_prices_are_refused_for_valuation() -> None:
    with pytest.raises(ValidationError, match="total-return"):
        PriceSeries(pd.Series([1.0], index=pd.DatetimeIndex([D0])), EUR, PriceType.TOTAL_RETURN)


def test_price_series_from_price_data() -> None:
    frame = pd.DataFrame({"X": [50.0, 55.0]}, index=pd.DatetimeIndex([D0, D1]))
    data = PriceData(
        dataset=Dataset(
            data=frame,
            provenance=_prov(),
            frequency=Frequency.DAILY,
            unit=Unit.PRICE,
            return_kind=None,
            currency=EUR,
            availability="synthetic",
            notes=(),
        ),
        price_types={"X": PriceType.NAV},
    )
    series = PriceSeries.from_price_data(data, "X")
    assert series.currency == EUR
    assert series.price_type is PriceType.NAV
    assert series.prices.tolist() == [50.0, 55.0]
    with pytest.raises(DataNotFoundError, match="Z"):
        PriceSeries.from_price_data(data, "Z")


# --------------------------------------------------------------------------- ECB converter
FX = _fx({D0: {"USD": 1.25, "GBP": 0.8}, D3: {"USD": 1.6, "GBP": np.nan}})


def test_converter_to_eur() -> None:
    convert = EcbConverter(FX, base=EUR, max_age_days=0)
    assert convert(Money.of(125, "USD"), D0) == Money.of(100, "EUR")
    assert convert(Money.of(160, "USD"), D3) == Money.of(100, "EUR")
    assert convert(Money.of(7, "EUR"), D0) == Money.of(7, "EUR")


def test_converter_cross_rate_to_non_eur_base() -> None:
    convert = EcbConverter(FX, base=GBP, max_age_days=0)
    # USD 125 -> EUR 100 -> GBP 80; EUR 10 -> GBP 8
    assert convert(Money.of(125, "USD"), D0) == Money.of(80, "GBP")
    assert convert(Money.of(10, "EUR"), D0) == Money.of(8, "GBP")


def test_converter_staleness_and_missing_values() -> None:
    convert = EcbConverter(FX, base=EUR, max_age_days=3)
    later = date(2026, 1, 5)
    assert convert(Money.of(125, "USD"), later) == Money.of(100, "EUR")
    assert convert.stale_uses == ((USD, later, D0),)
    strict = EcbConverter(FX, base=EUR, max_age_days=0)
    with pytest.raises(DataNotFoundError, match="older than 0 days"):
        strict(Money.of(1, "USD"), later)
    with pytest.raises(DataNotFoundError, match="GBP"):
        EcbConverter(FX, base=EUR, max_age_days=10)(Money.of(1, "GBP"), D3)  # NaN on D3, D0 too old
    with pytest.raises(DataNotFoundError, match="JPY"):
        strict(Money.of(1, "JPY"), D0)


def test_converter_requires_an_fx_dataset() -> None:
    not_fx = Dataset(
        data=pd.DataFrame({"X": [1.0]}, index=pd.DatetimeIndex([D0])),
        provenance=_prov(),
        frequency=Frequency.DAILY,
        unit=Unit.PRICE,
        return_kind=None,
        currency=EUR,
        availability="synthetic",
        notes=(),
    )
    with pytest.raises(ValidationError, match="FX"):
        EcbConverter(not_fx, base=EUR, max_age_days=0)


@pytest.mark.parametrize("bad", [-1, 1.5, True])
def test_age_limits_must_be_non_negative_ints(bad: object) -> None:
    with pytest.raises(ValidationError, match="max_age_days"):
        EcbConverter(FX, base=EUR, max_age_days=bad)  # type: ignore[arg-type]
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    with pytest.raises(ValidationError, match="max_price_age_days"):
        value_portfolio(history, TOY_PRICES, eur_only, dates=[D0], max_price_age_days=bad)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- multi-currency
def test_multi_currency_valuation_with_ecb_converter() -> None:
    convert = EcbConverter(FX, base=EUR, max_age_days=0)
    transactions = [
        tx("a", D0, K.DEPOSIT, amount=money(10000)),
        tx("b", D0, K.FX_CONVERSION, amount=money(4000), fx_counter=money(5000, "USD")),
        tx("c", D0, K.BUY, isin=Y, quantity="100", price=money(50, "USD")),
    ]
    history = replay(transactions, base=EUR, to_base=convert)
    prices = {Y: _series({D0: 50.0, D3: 60.0}, currency=USD)}
    valuation = value_portfolio(history, prices, convert, dates=[D0, D3], max_price_age_days=0)
    # D0: EUR 6,000 + USD 5,000 / 1.25 = 10,000. D3: 6,000 + USD 6,000 / 1.6 = 9,750
    assert valuation.totals == {D0: Decimal(10000), D3: Decimal(9750)}
    assert valuation.positions[D3] == {("main", Y): Decimal(3750)}


def test_no_price_before_the_date_raises() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    prices = {X: _series({D1: 55.0})}
    with pytest.raises(DataNotFoundError, match="on or before"):
        value_portfolio(history, prices, eur_only, dates=[D0], max_price_age_days=30)


def test_converter_must_return_base_currency() -> None:
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)

    def wrong(amount: Money, on: date) -> Money:
        return Money(amount.amount, USD)

    with pytest.raises(ValidationError, match="base currency"):
        value_portfolio(history, TOY_PRICES, wrong, dates=[D0], max_price_age_days=0)
