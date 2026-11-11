"""Formatting of numbers, percentages, money, dates and text for reports.

Display rounding is half-up on the decimal representation of the value (``repr`` for floats),
so that 999.995 shows as 1,000.00 and never as 999.99 because of binary floating point. NaN and
infinity raise: a report never prints "nan". Rounded zero is shown without a sign.
"""

from __future__ import annotations

import html
import math
import numbers
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import SupportsFloat

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money

__all__ = [
    "EN",
    "IT",
    "Language",
    "NumberStyle",
    "escape",
    "format_date",
    "format_money",
    "format_number",
    "format_percent",
    "style_for",
]

MAX_DECIMALS = 12


class Language(Enum):
    """Language of a report's labels."""

    IT = "it"
    EN = "en"


@dataclass(frozen=True)
class NumberStyle:
    """Separators and layout of numbers.

    Attributes
    ----------
    decimal, thousands
        Decimal and thousands separators.
    percent_space
        Whether a space precedes the percent sign (Italian ``3,17 %``).
    currency_first
        Whether the currency code precedes the amount (English ``EUR 1,234.50``).
    """

    decimal: str
    thousands: str
    percent_space: bool
    currency_first: bool


IT = NumberStyle(decimal=",", thousands=".", percent_space=True, currency_first=False)
EN = NumberStyle(decimal=".", thousands=",", percent_space=False, currency_first=True)


def style_for(language: Language) -> NumberStyle:
    """Return the number style that matches a language."""
    return IT if language is Language.IT else EN


def format_number(value: SupportsFloat, decimals: int, *, style: NumberStyle) -> str:
    """Format ``value`` with ``decimals`` decimal places, grouping thousands."""
    if type(decimals) is not int or not 0 <= decimals <= MAX_DECIMALS:
        raise ValidationError(f"decimals must be an int in [0, {MAX_DECIMALS}], got {decimals!r}")
    number = _to_decimal(value)
    quantum = Decimal(1).scaleb(-decimals)
    rounded = number.quantize(quantum, rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    sign = "-" if rounded < 0 else ""
    integer, _, fraction = f"{abs(rounded):f}".partition(".")
    groups: list[str] = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    text = style.thousands.join(groups)
    if decimals:
        text += style.decimal + fraction
    return sign + text


def format_percent(value: SupportsFloat, decimals: int, *, style: NumberStyle) -> str:
    """Format a decimal fraction as a percentage (``0.0317`` -> ``3.17%`` or ``3,17 %``)."""
    number = format_number(_to_decimal(value) * 100, decimals, style=style)
    return number + (" %" if style.percent_space else "%")


def format_money(amount: Money, *, style: NumberStyle) -> str:
    """Format money with the currency's minor units and ISO code."""
    number = format_number(amount.amount, amount.currency.minor_units, style=style)
    code = amount.currency.code
    return f"{code} {number}" if style.currency_first else f"{number} {code}"


def format_date(day: date, *, language: Language) -> str:
    """Format a date: ``31/03/2026`` in Italian, ISO ``2026-03-31`` in English."""
    return day.strftime("%d/%m/%Y") if language is Language.IT else day.isoformat()


def escape(text: str) -> str:
    """Escape text for HTML element content and attribute values."""
    return html.escape(text, quote=True)


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError("booleans are not numbers")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, numbers.Integral):
        number = Decimal(int(value))
    elif isinstance(value, numbers.Real):
        # float() first: NumPy 2 scalars repr as "np.float64(...)", which Decimal cannot read.
        as_float = float(value)
        if not math.isfinite(as_float):
            raise ValidationError(f"cannot format a non-finite number ({as_float})")
        number = Decimal(repr(as_float))
    else:
        raise ValidationError(f"cannot format {type(value).__name__} as a number")
    if not number.is_finite():
        raise ValidationError(f"cannot format a non-finite number ({number})")
    return number
