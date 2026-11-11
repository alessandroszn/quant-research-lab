"""Shared synthetic fixtures for portfolio tests (no real data)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd

from qrlab.core.calendar import Frequency
from qrlab.core.money import Currency, Money
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.user_csv import PriceType
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.ledger import LedgerHistory, replay
from qrlab.portfolio.transactions import Transaction, TransactionKind
from qrlab.portfolio.valuation import EcbConverter, PriceSeries, Valuation, value_portfolio

EUR, USD = Currency("EUR"), Currency("USD")
X = Isin("IE0000000012")  # made-up ISIN, valid check digit
Y = Isin("US0000000044")  # made-up ISIN, valid check digit

D0, D1, D2, D3 = date(2026, 1, 2), date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31)


def money(amount: str | int, currency: str = "EUR") -> Money:
    """Build Money from a string or int amount."""
    return Money.of(amount, currency)


def tx(
    id: str,
    day: date,
    kind: TransactionKind,
    *,
    isin: Isin | None = None,
    quantity: str | None = None,
    price: Money | None = None,
    amount: Money | None = None,
    fees: Money | None = None,
    taxes: Money | None = None,
    fx_counter: Money | None = None,
    account: str = "main",
) -> Transaction:
    """Build a transaction with zero fees and taxes in EUR unless given."""
    return Transaction(
        id=id,
        trade_date=day,
        kind=kind,
        account=account,
        isin=isin,
        quantity=None if quantity is None else Decimal(quantity),
        price=price,
        amount=amount,
        fees=fees if fees is not None else money(0),
        taxes=taxes if taxes is not None else money(0),
        fx_counter=fx_counter,
        note="",
    )


def toy_transactions() -> list[Transaction]:
    """Return the hand-reconciled toy portfolio of the 2.1 design note (EUR only)."""
    k = TransactionKind
    return [
        tx("t1", D0, k.DEPOSIT, amount=money(10000)),
        tx("t2", D0, k.BUY, isin=X, quantity="100", price=money(50), fees=money(10)),
        tx("t3", D1, k.DEPOSIT, amount=money(5000)),
        tx("t4", D2, k.DIVIDEND, isin=X, amount=money(100)),
        tx("t5", D3, k.SELL, isin=X, quantity="50", price=money(54), fees=money(10)),
    ]


class FixedRates:
    """Converter to EUR with EUR/USD rates per date (1 EUR = rate USD), carried forward.

    Used only in tests; production conversion uses dated ECB rates with staleness limits.
    """

    def __init__(self, eurusd: Mapping[date, str]) -> None:
        self._rates = sorted((d, Decimal(r)) for d, r in eurusd.items())

    def __call__(self, amount: Money, on: date) -> Money:
        """Convert ``amount`` to EUR at the latest rate on or before ``on``."""
        if amount.currency == EUR:
            return amount
        rate = [r for d, r in self._rates if d <= on][-1]
        return Money(amount.amount / rate, EUR)


def eur_only(amount: Money, on: date) -> Money:
    """Convert EUR to EUR (identity) for EUR-only portfolios; anything else is a test error."""
    assert amount.currency == EUR, amount
    return amount


# --------------------------------------------------------------------------- valuation helpers
def price_series(values: Mapping[date, float], currency: Currency = EUR) -> PriceSeries:
    """Build a price series (price type ``PRICE``) from dated values."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in values])
    return PriceSeries(pd.Series(list(values.values()), index=index), currency, PriceType.PRICE)


def synthetic_fx(rows: Mapping[date, Mapping[str, float]]) -> Dataset:
    """Build an ECB-style FX dataset (rates per 1 EUR) from dated rows."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in rows])
    return Dataset(
        data=pd.DataFrame([dict(r) for r in rows.values()], index=index),
        provenance=Provenance(
            source="test",
            dataset="eurofxref-hist",
            url="file:fx.csv",
            retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
            sha256=hashlib.sha256(b"fx").hexdigest(),
            size_bytes=2,
            terms="synthetic",
        ),
        frequency=Frequency.DAILY,
        unit=Unit.FX_RATE,
        return_kind=None,
        currency=EUR,
        availability="synthetic",
        notes=(),
    )


def toy_setup() -> tuple[LedgerHistory, Valuation]:
    """Return the toy portfolio's ledger history and its valuation on D0..D3."""
    history = replay(toy_transactions(), base=EUR, to_base=eur_only)
    prices = {X: price_series({D0: 50.0, D1: 55.0, D2: 52.0, D3: 54.0})}
    valuation = value_portfolio(
        history, prices, eur_only, dates=[D0, D1, D2, D3], max_price_age_days=0
    )
    return history, valuation


def multi_currency_setup() -> tuple[LedgerHistory, Valuation, EcbConverter]:
    """Return a EUR-base portfolio with USD cash and a USD position, valued on D0 and D3.

    EUR 10,000 deposited; EUR 5,000 -> USD 6,250 at 1.25; 100 Y @ USD 50. On D3 EUR/USD is
    1.60 and Y trades at USD 60.
    """
    convert = EcbConverter(
        synthetic_fx({D0: {"USD": 1.25}, D3: {"USD": 1.6}}), base=EUR, max_age_days=0
    )
    k = TransactionKind
    transactions = [
        tx("a", D0, k.DEPOSIT, amount=money(10000)),
        tx("b", D0, k.FX_CONVERSION, amount=money(5000), fx_counter=money(6250, "USD")),
        tx("c", D0, k.BUY, isin=Y, quantity="100", price=money(50, "USD")),
    ]
    history = replay(transactions, base=EUR, to_base=convert)
    prices = {Y: price_series({D0: 50.0, D3: 60.0}, currency=USD)}
    valuation = value_portfolio(history, prices, convert, dates=[D0, D3], max_price_age_days=0)
    return history, valuation, convert
