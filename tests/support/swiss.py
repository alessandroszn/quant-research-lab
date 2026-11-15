"""The synthetic Swiss account of the 9.2 tests (all data made up, CHF)."""

from __future__ import annotations

from datetime import date

from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.transactions import Transaction, TransactionKind
from support.portfolio import tx

K = TransactionKind
CHF = Currency("CHF")
A, B = Isin("IE0000000012"), Isin("CH0000000023")  # A Irish accumulating, B Swiss distributing


def chf(amount: str | int) -> Money:
    """Return an amount in CHF."""
    return Money.of(amount, "CHF")


def trade(id: str, day: date, kind: TransactionKind, **fields: object) -> Transaction:
    """Return a CHF transaction, with zero fees and taxes unless given."""
    return tx(id, day, kind, **{"fees": chf(0), "taxes": chf(0)} | fields)  # type: ignore[arg-type]


TRANSACTIONS = [
    trade("d1", date(2025, 12, 1), K.DEPOSIT, amount=chf(100000)),
    trade("a1", date(2025, 12, 1), K.BUY, isin=A, quantity="400", price=chf(100)),
    trade("b1", date(2025, 12, 1), K.BUY, isin=B, quantity="500", price=chf(100)),
    trade("d2", date(2026, 2, 1), K.DEPOSIT, amount=chf(100000)),
    trade("b2", date(2026, 2, 1), K.BUY, isin=B, quantity="1000", price=chf(100)),
    trade("v1", date(2026, 3, 15), K.DIVIDEND, isin=B, amount=chf(1200), taxes=chf(420)),
    trade("s1", date(2026, 6, 1), K.SELL, isin=B, quantity="1000", price=chf(130)),
    trade("a2", date(2026, 7, 1), K.BUY, isin=A, quantity="1000", price=chf(100)),
    trade("s2", date(2026, 9, 1), K.SELL, isin=A, quantity="200", price=chf(100)),
    trade("s3", date(2027, 2, 1), K.SELL, isin=A, quantity="100", price=chf(110)),
]  # fmt: skip
"""The account described in ``tests/unit/tax/test_switzerland.py``."""
