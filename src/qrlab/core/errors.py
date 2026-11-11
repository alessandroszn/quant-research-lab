"""Exception hierarchy shared by every ``qrlab`` subpackage.

Errors derive from :class:`ValueError` where the cause is a bad argument value, so generic
callers can still catch them, while ``qrlab`` callers can catch :class:`QrlabError` or a precise
subclass.
"""

from __future__ import annotations

__all__ = [
    "AlignmentError",
    "CurrencyError",
    "CurrencyMismatchError",
    "QrlabError",
    "ValidationError",
]


class QrlabError(Exception):
    """Base class for all errors raised deliberately by ``qrlab``."""


class ValidationError(QrlabError, ValueError):
    """An input does not satisfy a documented precondition."""


class AlignmentError(ValidationError):
    """Objects that must share the same index (and time zone) do not."""


class CurrencyError(QrlabError, ValueError):
    """An invalid currency, amount or FX rate."""


class CurrencyMismatchError(CurrencyError):
    """Amounts in different currencies were combined without an explicit FX conversion."""
