"""How values look on screen in the chosen language (display only; files never change).

- Floats: six significant figures with the language's separators; NaN is ``—``, infinities
  are ``∞`` and ``-∞``.
- Integers: as they are, without grouping (counts, windows and years).
- Text, including dates inside output tables: exactly as recorded; no guessing.
- Dates and timestamps the app itself shows: the language's date format.
"""

from __future__ import annotations

import math
import numbers
from datetime import UTC, date, datetime

from qrlab.reporting.formatting import Language, format_date, format_significant, style_for

__all__ = ["MISSING", "SIGNIFICANT_DIGITS", "cell_text", "date_text", "timestamp_text"]

SIGNIFICANT_DIGITS = 6
MISSING = "—"


def _language(language: str) -> Language:
    return Language(language)


def cell_text(value: object, language: str) -> str:
    """Return the text of one table or scalar value in ``language``."""
    if value is None:
        return ""
    if isinstance(value, bool) or type(value).__name__ == "bool":  # Python or NumPy booleans
        return str(value)
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            return MISSING
        if math.isinf(number):
            return "∞" if number > 0 else "-∞"
        style = style_for(_language(language))
        return format_significant(number, SIGNIFICANT_DIGITS, style=style)
    return str(value)


def date_text(day: date, language: str) -> str:
    """Return a date in the language's format (``12/11/2026`` or ``2026-11-12``)."""
    return format_date(day, language=_language(language))


def timestamp_text(value: str, language: str) -> str:
    """Return a recorded ISO timestamp as date and ``HH:MM UTC``; other text is unchanged."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        return value
    utc = moment.astimezone(UTC)
    return f"{date_text(utc.date(), language)} {utc:%H:%M} UTC"
