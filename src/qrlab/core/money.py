"""Currency-aware amounts and dated FX conversion.

Every monetary value carries its currency. Amounts in different currencies cannot be added,
subtracted or compared; converting requires an explicit, dated :class:`FxRate`.

Amounts are :class:`decimal.Decimal`, not ``float``, so cash ledgers reconcile exactly
(``0.1 + 0.2 == 0.3``). Constructing an amount from a ``float`` raises, because the float has
already lost precision. Return and risk analytics stay in ``float64``; this module is the
boundary.

Rounding to a currency's minor units is explicit (:meth:`Money.rounded`) and never automatic.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from qrlab.core.errors import CurrencyError, CurrencyMismatchError

__all__ = ["MINOR_UNITS", "Currency", "FxRate", "Money", "convert"]

MINOR_UNITS = MappingProxyType(
    {
        "AED": 2, "AUD": 2, "BHD": 3, "BRL": 2, "CAD": 2, "CHF": 2, "CLP": 0, "CNY": 2,
        "CZK": 2, "DKK": 2, "EUR": 2, "GBP": 2, "HKD": 2, "HUF": 2, "IDR": 2, "ILS": 2,
        "INR": 2, "ISK": 0, "JPY": 0, "KRW": 0, "KWD": 3, "MXN": 2, "MYR": 2, "NOK": 2,
        "NZD": 2, "PHP": 2, "PLN": 2, "RON": 2, "SAR": 2, "SEK": 2, "SGD": 2, "THB": 2,
        "TRY": 2, "TWD": 2, "USD": 2, "ZAR": 2,
    }
)  # fmt: skip
"""Supported ISO 4217 codes and their minor units (decimal places). Extend as needed."""

_ROUNDING_MODES = frozenset(
    {
        decimal.ROUND_CEILING,
        decimal.ROUND_DOWN,
        decimal.ROUND_FLOOR,
        decimal.ROUND_HALF_DOWN,
        decimal.ROUND_HALF_EVEN,
        decimal.ROUND_HALF_UP,
        decimal.ROUND_UP,
        decimal.ROUND_05UP,
    }
)


@dataclass(frozen=True)
class Currency:
    """An ISO 4217 currency from :data:`MINOR_UNITS`.

    Parameters
    ----------
    code
        Upper-case three-letter code, e.g. ``"EUR"``. Unknown codes raise.
    """

    code: str

    def __post_init__(self) -> None:
        """Validate the code."""
        if not _is_known_code(self.code):
            raise CurrencyError(f"unsupported currency code {self.code!r}")

    @property
    def minor_units(self) -> int:
        """Number of decimal places of the currency's minor unit (EUR 2, JPY 0)."""
        return MINOR_UNITS[self.code]

    def __str__(self) -> str:
        """Return the ISO code."""
        return self.code


@dataclass(frozen=True)
class Money:
    """An exact amount in a currency.

    Parameters
    ----------
    amount
        Finite :class:`~decimal.Decimal`. Use :meth:`Money.of` to build from ``str`` or ``int``.
    currency
        The currency of the amount.

    Notes
    -----
    ``+``, ``-`` and ordering comparisons require the same currency and otherwise raise
    :class:`~qrlab.core.errors.CurrencyMismatchError`. Equality between different currencies
    is simply ``False``. Multiplication and division accept ``int`` or ``Decimal`` scalars only.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        """Validate amount and currency."""
        _require_decimal(self.amount, "amount")
        _require_currency(self.currency, "currency")

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: Currency | str) -> Money:
        """Build from a ``Decimal``, ``int`` or numeric string and a currency or ISO code."""
        return cls(_to_decimal(amount, "amount"), _to_currency(currency))

    def rounded(self, rounding: str) -> Money:
        """Round to the currency's minor units with an explicit :mod:`decimal` rounding mode."""
        if rounding not in _ROUNDING_MODES:
            raise CurrencyError(f"unknown rounding mode {rounding!r}")
        quantum = Decimal(1).scaleb(-self.currency.minor_units)
        return Money(self.amount.quantize(quantum, rounding=rounding), self.currency)

    # ---------------------------------------------------------------- arithmetic
    def __add__(self, other: Money) -> Money:
        """Add an amount in the same currency."""
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other, "add")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        """Subtract an amount in the same currency."""
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other, "subtract")
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        """Return the negated amount."""
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        """Return the absolute amount."""
        return Money(abs(self.amount), self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        """Scale by an ``int`` or ``Decimal``."""
        if not _is_exact_scalar(factor):
            return NotImplemented
        return Money(self.amount * factor, self.currency)

    __rmul__ = __mul__

    def __truediv__(self, divisor: int | Decimal) -> Money:
        """Divide by an ``int`` or ``Decimal`` (no implicit rounding)."""
        if not _is_exact_scalar(divisor):
            return NotImplemented
        return Money(self.amount / divisor, self.currency)

    # ---------------------------------------------------------------- ordering
    def __lt__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        return self._comparable(other) < other.amount

    def __le__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        return self._comparable(other) <= other.amount

    def __gt__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        return self._comparable(other) > other.amount

    def __ge__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        return self._comparable(other) >= other.amount

    def _comparable(self, other: Money) -> Decimal:
        if not isinstance(other, Money):
            raise TypeError(f"cannot compare Money with {type(other).__name__}")
        self._require_same_currency(other, "compare")
        return self.amount

    def _require_same_currency(self, other: Money, operation: str) -> None:
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                f"cannot {operation} {self.currency} and {other.currency}; convert explicitly"
            )


@dataclass(frozen=True)
class FxRate:
    """A dated exchange rate: one unit of ``base`` equals ``rate`` units of ``quote``.

    Example: ``FxRate(Currency("EUR"), Currency("USD"), Decimal("1.25"), date(2026, 1, 2))``
    means 1 EUR = 1.25 USD on 2 January 2026.

    Parameters
    ----------
    base, quote
        Different currencies.
    rate
        Positive finite ``Decimal``.
    as_of
        Date the rate refers to (a ``date``, not a ``datetime``).
    """

    base: Currency
    quote: Currency
    rate: Decimal
    as_of: date

    def __post_init__(self) -> None:
        """Validate currencies, rate and date."""
        _require_currency(self.base, "base")
        _require_currency(self.quote, "quote")
        if self.base == self.quote:
            raise CurrencyError(f"base and quote must differ, both are {self.base}")
        _require_decimal(self.rate, "rate")
        if self.rate <= 0:
            raise CurrencyError(f"rate must be positive, got {self.rate}")
        if isinstance(self.as_of, datetime) or not isinstance(self.as_of, date):
            raise CurrencyError("as_of must be a datetime.date (not a datetime)")

    def invert(self) -> FxRate:
        """Return the same rate quoted the other way round (``quote/base``)."""
        return FxRate(self.quote, self.base, Decimal(1) / self.rate, self.as_of)


def convert(amount: Money, rate: FxRate, *, to: Currency) -> Money:
    """Convert ``amount`` into ``to`` with an explicit dated rate.

    The rate's staleness relative to the valuation date is checked by the caller, which knows
    that date; the rate always carries its ``as_of`` date. The result is not rounded.

    Raises
    ------
    CurrencyMismatchError
        Unless ``amount`` is in one side of the rate and ``to`` is the other side.
    """
    if amount.currency == rate.base and to == rate.quote:
        return Money(amount.amount * rate.rate, to)
    if amount.currency == rate.quote and to == rate.base:
        return Money(amount.amount / rate.rate, to)
    raise CurrencyMismatchError(
        f"rate {rate.base}/{rate.quote} cannot convert {amount.currency} to {to}"
    )


# --------------------------------------------------------------------------- helpers
def _is_known_code(code: object) -> bool:
    return isinstance(code, str) and code in MINOR_UNITS


def _require_currency(value: object, name: str) -> None:
    if not isinstance(value, Currency):
        raise CurrencyError(f"{name} must be a Currency, got {value!r}")


def _require_decimal(value: object, name: str) -> None:
    if isinstance(value, float):
        raise CurrencyError(f"{name} must not be a float; pass a str, int or Decimal")
    if not isinstance(value, Decimal):
        raise CurrencyError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise CurrencyError(f"{name} must be finite, got {value}")


def _to_decimal(value: object, name: str) -> Decimal:
    if isinstance(value, float):
        raise CurrencyError(f"{name} must not be a float; pass a str, int or Decimal")
    if isinstance(value, bool):
        raise CurrencyError(f"{name} must not be a bool")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        try:
            return Decimal(value)
        except decimal.InvalidOperation as exc:
            raise CurrencyError(f"{name}: cannot parse {value!r}") from exc
    raise CurrencyError(f"{name}: unsupported type {type(value).__name__}")


def _to_currency(value: Currency | str) -> Currency:
    return value if isinstance(value, Currency) else Currency(value)


def _is_exact_scalar(value: object) -> bool:
    return isinstance(value, Decimal) or type(value) is int
