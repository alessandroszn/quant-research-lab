"""Portfolio transactions.

Every monetary value is :class:`~qrlab.core.money.Money` and every quantity a ``Decimal``.
Each :class:`TransactionKind` has a fixed set of required and forbidden fields, enforced on
construction, so an impossible transaction cannot exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.instruments.identifiers import Isin

__all__ = ["Transaction", "TransactionKind"]


class TransactionKind(Enum):
    """What a transaction does. ``is_external_flow`` marks money entering or leaving."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    TAX = "tax"
    FX_CONVERSION = "fx_conversion"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    SPLIT = "split"

    @property
    def is_external_flow(self) -> bool:
        """Whether the transaction is an external flow for performance measurement."""
        return self in _EXTERNAL


_EXTERNAL = frozenset(
    {
        TransactionKind.DEPOSIT,
        TransactionKind.WITHDRAWAL,
        TransactionKind.TRANSFER_IN,
        TransactionKind.TRANSFER_OUT,
    }
)

# Fields that must be present (True) or absent (False) per kind; others are not checked.
_FIELDS = ("isin", "quantity", "price", "amount", "fx_counter")
_CASH_ONLY = {"isin": False, "quantity": False, "price": False, "amount": True, "fx_counter": False}
_TRADE = {"isin": True, "quantity": True, "price": True, "amount": False, "fx_counter": False}
_RULES: dict[TransactionKind, dict[str, bool]] = {
    TransactionKind.DEPOSIT: _CASH_ONLY,
    TransactionKind.WITHDRAWAL: _CASH_ONLY,
    TransactionKind.INTEREST: _CASH_ONLY,
    TransactionKind.FEE: _CASH_ONLY,
    TransactionKind.TAX: _CASH_ONLY,
    TransactionKind.BUY: _TRADE,
    TransactionKind.SELL: _TRADE,
    TransactionKind.TRANSFER_IN: _TRADE,
    TransactionKind.TRANSFER_OUT: _TRADE,
    TransactionKind.DIVIDEND: {
        "isin": True, "quantity": False, "price": False, "amount": True, "fx_counter": False,
    },
    TransactionKind.FX_CONVERSION: {
        "isin": False, "quantity": False, "price": False, "amount": True, "fx_counter": True,
    },
    TransactionKind.SPLIT: {
        "isin": True, "quantity": True, "price": False, "amount": False, "fx_counter": False,
    },
}  # fmt: skip


@dataclass(frozen=True)
class Transaction:
    """One booked transaction.

    Parameters
    ----------
    id
        Unique, stable identifier (e.g. the broker's reference).
    trade_date
        Trade date (a ``date``, not a ``datetime``).
    kind
        What the transaction does; decides which fields are required.
    account
        Account the transaction belongs to.
    isin
        Instrument, for trades, transfers, dividends and splits.
    quantity
        Units (> 0) for trades and transfers; the ratio new/old units for a split.
    price
        Price per unit in the instrument's currency (trades); market value per unit (transfers).
    amount
        Cash amount (> 0) for deposits, withdrawals, income, fees, taxes and the sold side of an
        FX conversion.
    fees, taxes
        Charges attached to the transaction (>= 0, explicit zero when none).
    fx_counter
        FX conversion only: the amount received, in a different currency.
    note
        Free text.
    """

    id: str
    trade_date: date
    kind: TransactionKind
    account: str
    isin: Isin | None
    quantity: Decimal | None
    price: Money | None
    amount: Money | None
    fees: Money
    taxes: Money
    fx_counter: Money | None
    note: str

    def __post_init__(self) -> None:
        """Enforce the field rules of the transaction kind."""
        _require_text(self.id, "id")
        _require_text(self.account, "account")
        if isinstance(self.trade_date, datetime) or not isinstance(self.trade_date, date):
            raise ValidationError(f"{self.id}: trade_date must be a datetime.date")
        if not isinstance(self.kind, TransactionKind):
            raise ValidationError(f"{self.id}: kind must be a TransactionKind")
        for name in ("fees", "taxes"):
            charge = getattr(self, name)
            if not isinstance(charge, Money) or charge.amount < 0:
                raise ValidationError(f"{self.id}: {name} must be Money >= 0")
        for name, required in _RULES[self.kind].items():
            present = getattr(self, name) is not None
            if present != required:
                verb = "requires" if required else "must not have"
                raise ValidationError(f"{self.id}: {self.kind.value} {verb} {name}")
        if self.quantity is not None and not _positive_decimal(self.quantity):
            raise ValidationError(f"{self.id}: quantity must be a positive Decimal")
        for name in ("price", "amount", "fx_counter"):
            value = getattr(self, name)
            if value is not None and not (isinstance(value, Money) and value.amount > 0):
                raise ValidationError(f"{self.id}: {name} must be positive Money")
        if _same_currency(self.fx_counter, self.amount):
            raise ValidationError(f"{self.id}: FX conversion currencies must differ")


def _positive_decimal(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def _same_currency(a: Money | None, b: Money | None) -> bool:
    return a is not None and b is not None and a.currency == b.currency


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"transaction {name} must be non-empty text, got {value!r}")
