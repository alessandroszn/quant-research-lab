"""Shared synthetic fixtures for portfolio tests (no real data)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.transactions import Transaction, TransactionKind

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
