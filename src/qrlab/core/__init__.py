"""Shared primitives with no dependencies on other ``qrlab`` subpackages.

Modules:

- ``errors``: exception hierarchy (:class:`QrlabError` and subclasses).
- ``series``: validation of time-indexed pandas objects with an explicit :class:`NanPolicy`.
- ``calendar``: frequencies (periods per year are explicit, never inferred silently) and
  business-day calendars such as TARGET2.
- ``returns``: simple vs. log returns, price to returns, excess returns, compounding and
  aggregation across frequencies.
- ``money``: currency-aware amounts (:class:`Money`) and dated FX rates; mixing currencies
  raises.
"""

from qrlab.core.calendar import (
    CONVENTIONAL_PERIODS_PER_YEAR,
    BusinessCalendar,
    Frequency,
    easter_sunday,
    infer_frequency,
    require_periods_per_year,
    target2_calendar,
    weekday_calendar,
)
from qrlab.core.errors import (
    AlignmentError,
    CurrencyError,
    CurrencyMismatchError,
    QrlabError,
    ValidationError,
)
from qrlab.core.money import MINOR_UNITS, Currency, FxRate, Money, convert
from qrlab.core.rates import overnight_returns
from qrlab.core.returns import (
    AggregatedReturns,
    ReturnKind,
    aggregate_returns,
    compound,
    convert_return_currency,
    excess_returns,
    log_to_simple,
    prices_to_returns,
    simple_to_log,
    wealth_index,
)
from qrlab.core.series import NanPolicy, require_same_index, validate_frame, validate_series

__all__ = [
    "CONVENTIONAL_PERIODS_PER_YEAR",
    "MINOR_UNITS",
    "AggregatedReturns",
    "AlignmentError",
    "BusinessCalendar",
    "Currency",
    "CurrencyError",
    "CurrencyMismatchError",
    "Frequency",
    "FxRate",
    "Money",
    "NanPolicy",
    "QrlabError",
    "ReturnKind",
    "ValidationError",
    "aggregate_returns",
    "compound",
    "convert",
    "convert_return_currency",
    "easter_sunday",
    "excess_returns",
    "infer_frequency",
    "log_to_simple",
    "overnight_returns",
    "prices_to_returns",
    "require_periods_per_year",
    "require_same_index",
    "simple_to_log",
    "target2_calendar",
    "validate_frame",
    "validate_series",
    "wealth_index",
    "weekday_calendar",
]
