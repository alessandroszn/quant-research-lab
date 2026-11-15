"""The synthetic account of the 9.3 tests (all data made up, EUR)."""

from __future__ import annotations

from datetime import date

from qrlab.core.money import Money
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.transactions import Transaction, TransactionKind
from support.portfolio import tx

K = TransactionKind
X, Y = Isin("IE0000000012"), Isin("US0000000044")


def eur(amount: str | int) -> Money:
    """Return an amount in EUR."""
    return Money.of(amount, "EUR")


TRANSACTIONS: list[Transaction] = [
    tx("d", date(2025, 1, 2), K.DEPOSIT, amount=eur(20000)),
    tx("bx", date(2025, 1, 2), K.BUY, isin=X, quantity="100", price=eur(100)),
    tx("sx1", date(2025, 6, 2), K.SELL, isin=X, quantity="50", price=eur(80)),
    tx("by", date(2026, 1, 5), K.BUY, isin=Y, quantity="100", price=eur(50)),
    tx("sx2", date(2026, 2, 1), K.SELL, isin=X, quantity="50", price=eur(150)),
    tx("v", date(2026, 2, 15), K.DIVIDEND, isin=Y, amount=eur(400), taxes=eur(60)),
    tx("sy", date(2026, 3, 1), K.SELL, isin=Y, quantity="100", price=eur(80)),
]
"""The account described in ``tests/unit/tax/test_custom.py``."""
