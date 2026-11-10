"""Instrument master data and explicit reports of missing or stale information.

Unknown values are ``None``, never a default: ``ter=None`` means *unknown*, not zero. Records
are validated on construction (impossible values raise); incomplete or stale records are valid
but produce :class:`Issue` findings through :func:`master_data_issues`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.instruments.identifiers import Isin, validate_country

__all__ = [
    "FUND_TYPES",
    "MAX_TER",
    "AssetClass",
    "Distribution",
    "Instrument",
    "InstrumentType",
    "Issue",
    "IssueKind",
    "Replication",
    "master_data_issues",
]

MAX_TER = Decimal("0.03")
"""Upper bound for a TER expressed as a fraction (3 %). Larger values are almost certainly a
percentage typed as a fraction (e.g. ``0.2`` meaning 0.20 %) and are rejected."""


class InstrumentType(Enum):
    """Legal or product type of an instrument."""

    ETF = "etf"
    ETC = "etc"
    STOCK = "stock"
    BOND = "bond"
    FUND = "fund"
    CASH = "cash"


FUND_TYPES = frozenset({InstrumentType.ETF, InstrumentType.ETC, InstrumentType.FUND})
"""Types for which replication, distribution policy and TER are meaningful."""


class AssetClass(Enum):
    """Broad asset class."""

    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    MONEY_MARKET = "money_market"
    COMMODITY = "commodity"
    REAL_ESTATE = "real_estate"
    MULTI_ASSET = "multi_asset"
    CASH = "cash"
    OTHER = "other"


class Replication(Enum):
    """How a fund tracks its benchmark."""

    PHYSICAL_FULL = "physical_full"
    PHYSICAL_SAMPLING = "physical_sampling"
    SYNTHETIC = "synthetic"


class Distribution(Enum):
    """What a fund does with income."""

    ACCUMULATING = "accumulating"
    DISTRIBUTING = "distributing"


@dataclass(frozen=True)
class Instrument:
    """Master data of one instrument.

    Parameters
    ----------
    isin
        Identifier.
    name
        Non-empty name without leading or trailing spaces.
    instrument_type, asset_class
        Classification.
    currency
        Base (NAV) currency of a fund, or the currency of the instrument.
    as_of
        Date the record was last verified against its source.
    domicile
        ISO 3166-1 alpha-2 country of domicile, or ``None`` if unknown.
    replication, distribution, ter
        Fund-only fields (``FUND_TYPES``); ``None`` if unknown, and always ``None`` for other
        types. ``ter`` is an annual fraction (``Decimal("0.0020")`` = 0.20 %) in [0, 0.03].
    benchmark
        Name of the tracked index, or ``None``.
    hedged_to
        Currency a hedged share class is hedged to; ``None`` for unhedged instruments.
    inception
        Launch date, or ``None`` if unknown.
    source
        Where the record comes from, e.g. ``"KID 2026-03"``.
    """

    isin: Isin
    name: str
    instrument_type: InstrumentType
    asset_class: AssetClass
    currency: Currency
    as_of: date
    domicile: str | None
    replication: Replication | None
    distribution: Distribution | None
    ter: Decimal | None
    benchmark: str | None
    hedged_to: Currency | None
    inception: date | None
    source: str

    def __post_init__(self) -> None:
        """Validate types, ranges and consistency between fields."""
        _require_type(self.isin, Isin, "isin")
        _require_text(self.name, "name")
        _require_type(self.instrument_type, InstrumentType, "instrument_type")
        _require_type(self.asset_class, AssetClass, "asset_class")
        _require_type(self.currency, Currency, "currency")
        _require_date(self.as_of, "as_of")
        _require_text(self.source, "source")
        if self.domicile is not None:
            validate_country(self.domicile)
        if self.replication is not None:
            _require_type(self.replication, Replication, "replication")
        if self.distribution is not None:
            _require_type(self.distribution, Distribution, "distribution")
        if self.benchmark is not None:
            _require_text(self.benchmark, "benchmark")
        if self.ter is not None:
            _check_ter(self.ter)
        if self.hedged_to is not None:
            _require_type(self.hedged_to, Currency, "hedged_to")
            if self.hedged_to == self.currency:
                raise ValidationError("hedged_to must differ from the base currency")
        if self.inception is not None:
            _require_date(self.inception, "inception")
            if self.as_of < self.inception:
                raise ValidationError("as_of is before the inception date")
        if self.instrument_type not in FUND_TYPES:
            for field in ("replication", "distribution", "ter"):
                if getattr(self, field) is not None:
                    raise ValidationError(
                        f"{field} applies to fund types only, not {self.instrument_type.value}"
                    )

    @property
    def is_fund(self) -> bool:
        """Whether fund-only fields apply."""
        return self.instrument_type in FUND_TYPES

    @property
    def ter_percent(self) -> Decimal | None:
        """TER in percent for display (``0.0020`` -> ``0.20``), or ``None`` if unknown."""
        return None if self.ter is None else self.ter * 100


class IssueKind(Enum):
    """Category of a data-quality finding."""

    MISSING = "missing"
    STALE = "stale"
    FUTURE = "future"
    DUPLICATE = "duplicate"
    WEIGHTS = "weights"
    UNKNOWN_SHARE = "unknown_share"


@dataclass(frozen=True)
class Issue:
    """A data-quality finding to be shown in reports; it never alters the data."""

    subject: str
    field: str
    kind: IssueKind
    detail: str


def master_data_issues(
    instruments: Iterable[Instrument], *, on: date, max_age_days: int
) -> list[Issue]:
    """Report missing, stale, future-dated and duplicated master data.

    Parameters
    ----------
    instruments
        Records to check.
    on
        Date of the analysis.
    max_age_days
        Records verified more than this many days before ``on`` are reported as stale. The
        threshold is the caller's explicit choice.

    Returns
    -------
    list of Issue
        In input order; empty when everything is complete and current.
    """
    _require_non_negative_int(max_age_days, "max_age_days")
    records = list(instruments)
    issues: list[Issue] = []
    counts = Counter(record.isin for record in records)
    reported: set[Isin] = set()
    for record in records:
        subject = record.isin.code
        if counts[record.isin] > 1 and record.isin not in reported:
            reported.add(record.isin)
            issues.append(
                Issue(subject, "isin", IssueKind.DUPLICATE, f"{counts[record.isin]} records")
            )
        required = ["domicile"]
        if record.is_fund:
            required += ["replication", "distribution", "ter", "benchmark"]
        issues.extend(
            Issue(subject, field, IssueKind.MISSING, f"{field} is unknown")
            for field in required
            if getattr(record, field) is None
        )
        age = (on - record.as_of).days
        if age < 0:
            issues.append(
                Issue(subject, "as_of", IssueKind.FUTURE, f"as_of {record.as_of} is after {on}")
            )
        elif age > max_age_days:
            issues.append(
                Issue(
                    subject,
                    "as_of",
                    IssueKind.STALE,
                    f"verified {age} days before {on} (limit {max_age_days})",
                )
            )
    return issues


# --------------------------------------------------------------------------- helpers
def _check_ter(ter: object) -> None:
    if not isinstance(ter, Decimal):
        raise ValidationError(f"ter must be a Decimal fraction, got {type(ter).__name__}")
    if not ter.is_finite() or not Decimal(0) <= ter <= MAX_TER:
        raise ValidationError(
            f"TER {ter} is outside [0, {MAX_TER}]; it must be a fraction (0.0020 = 0.20 %)"
        )


def _require_type(value: object, expected: type, name: str) -> None:
    if not isinstance(value, expected):
        raise ValidationError(f"{name} must be a {expected.__name__}, got {value!r}")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError(f"{name} must be non-empty text without surrounding spaces")


def _require_date(value: object, name: str) -> None:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValidationError(f"{name} must be a datetime.date, not {type(value).__name__}")


def _require_non_negative_int(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValidationError(f"{name} must be a non-negative int, got {value!r}")
