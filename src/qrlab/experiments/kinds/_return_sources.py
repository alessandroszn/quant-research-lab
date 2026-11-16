"""Which series each position's returns use, for risk and the checks (design note 11.1).

The report values the portfolio from market prices; its risk section and its diversification
checks read returns. A price excludes the income a fund pays out, so for those two the kind
can use, per held position:

- a total-return series (the optional ``total_returns`` input and its mapping);
- the price adjusted for the distributions in ``[parameters.distributions]``
  (:func:`qrlab.core.returns.distribution_adjusted`);
- otherwise the price, which includes the income when the price file says ``total_return``,
  for an accumulating fund (the income stays in the fund) and for an ETC (it pays none).

:func:`return_source` is the rule; :func:`return_levels` applies it and builds the series.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.core.returns import distribution_adjusted
from qrlab.data.user_csv import PriceData, PriceType
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import day, number, text
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import FUND_TYPES, Distribution, Instrument, InstrumentType
from qrlab.portfolio.valuation import PriceSeries
from qrlab.reporting.portfolio_report import ReturnSource

__all__ = [
    "INCOME_EXCLUDED",
    "Payment",
    "ReturnLevels",
    "excluded_note",
    "parse_distributions",
    "return_levels",
    "return_source",
]

INCOME_EXCLUDED = (
    "Returns for risk and the diversification checks are computed from prices for {names}: "
    "they exclude the income paid out, so return levels are understated; volatilities and "
    "correlations change little."
)
_REASONS = {
    ReturnSource.DISTRIBUTING: "distributing",
    ReturnSource.POLICY_UNKNOWN: "distribution policy unknown",
    ReturnSource.STOCK: "a stock",
    ReturnSource.BOND: "a bond",
    ReturnSource.OTHER: "no income series",
}


@dataclass(frozen=True)
class Payment:
    """One distribution: its ex-date and gross amount per unit."""

    ex_date: date
    per_unit: float
    currency: Currency


@dataclass(frozen=True)
class ReturnLevels:
    """The series each held position's returns use, and where each came from."""

    levels: Mapping[Isin, pd.Series]
    sources: Mapping[Isin, ReturnSource]


def parse_distributions(parameters: Mapping[str, object]) -> dict[Isin, tuple[Payment, ...]]:
    """Read ``[parameters.distributions]``: ISIN = list of ``{ ex_date, per_unit, currency }``."""
    if "distributions" not in parameters:
        return {}
    value = parameters["distributions"]
    if not isinstance(value, dict) or not value:
        raise ValidationError(
            "[parameters.distributions] must hold, per fund ISIN, a list of "
            "{ ex_date, per_unit, currency }"
        )
    out: dict[Isin, tuple[Payment, ...]] = {}
    for code, entries in value.items():
        where = f"[parameters.distributions] {code}"
        if not isinstance(entries, list) or not entries:
            raise ValidationError(f"{where}: must be a non-empty list of tables")
        payments = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValidationError(f"{where}: every entry must be a table")
            require_keys(
                entry, required={"ex_date", "per_unit", "currency"}, optional=set(), where=where
            )
            per_unit = number(entry, "per_unit")
            if per_unit <= 0:
                raise ValidationError(f"{where}: per_unit must be positive, got {per_unit}")
            payments.append(
                Payment(day(entry, "ex_date"), per_unit, Currency(text(entry, "currency")))
            )
        dates = [p.ex_date for p in payments]
        twice = sorted({d for d in dates if dates.count(d) > 1})
        if twice:
            raise ValidationError(
                f"{where}: two distributions on {twice[0]}; write their sum as one entry"
            )
        out[Isin(code)] = tuple(sorted(payments, key=lambda p: p.ex_date))
    return out


def return_source(
    instrument: Instrument | None,
    price_type: PriceType,
    *,
    total_return_file: bool,
    distributions: bool,
) -> ReturnSource:
    """Apply the rule of design note 11.1: the first that applies wins."""
    if total_return_file:
        return ReturnSource.TOTAL_RETURN_FILE
    if distributions:
        return ReturnSource.DISTRIBUTIONS
    if price_type is PriceType.TOTAL_RETURN:
        return ReturnSource.TOTAL_RETURN_PRICES
    if instrument is None:
        return ReturnSource.POLICY_UNKNOWN
    kind = instrument.instrument_type
    if kind is InstrumentType.ETC:
        return ReturnSource.NO_INCOME
    if kind in FUND_TYPES:
        if instrument.distribution is Distribution.ACCUMULATING:
            return ReturnSource.ACCUMULATING
        if instrument.distribution is Distribution.DISTRIBUTING:
            return ReturnSource.DISTRIBUTING
        return ReturnSource.POLICY_UNKNOWN
    if kind is InstrumentType.STOCK:
        return ReturnSource.STOCK
    if kind is InstrumentType.BOND:
        return ReturnSource.BOND
    return ReturnSource.OTHER


def return_levels(
    held: list[Isin],
    *,
    prices: Mapping[Isin, PriceSeries],
    instruments: Mapping[Isin, Instrument],
    total_returns: PriceData | None,
    distributions: Mapping[Isin, tuple[Payment, ...]],
) -> ReturnLevels:
    """Build the series of every held position, after checking both optional inputs."""
    files = {} if total_returns is None else _total_return_columns(total_returns, prices)
    for isin in [*files, *distributions]:
        if isin not in held:
            what = "total_returns" if isin in files else "[parameters.distributions]"
            raise ValidationError(f"{what}: {isin.code} is not held")
    both = sorted(i.code for i in files if i in distributions)
    if both:
        raise ValidationError(
            f"{both[0]} has both a total-return series and distributions: give one"
        )
    levels: dict[Isin, pd.Series] = {}
    sources: dict[Isin, ReturnSource] = {}
    for isin in held:
        series = prices[isin]
        sources[isin] = return_source(
            instruments.get(isin),
            series.price_type,
            total_return_file=isin in files,
            distributions=isin in distributions,
        )
        price = series.prices.dropna().astype("float64")
        if isin in files:
            levels[isin] = files[isin]
        elif isin in distributions:
            levels[isin] = _adjusted(isin, price, series.currency, distributions[isin])
        else:
            levels[isin] = price
    return ReturnLevels(levels, sources)


def excluded_note(sources: Mapping[Isin, ReturnSource], names: Mapping[Isin, str]) -> str | None:
    """Return the notice sentence naming each position whose returns exclude its income."""
    excluded = [
        f"{names.get(isin, isin.code)} ({_REASONS[source]})"
        for isin, source in sorted(sources.items(), key=lambda item: item[0].code)
        if not source.income_included
    ]
    return INCOME_EXCLUDED.format(names=", ".join(excluded)) if excluded else None


def _total_return_columns(
    data: PriceData, prices: Mapping[Isin, PriceSeries]
) -> dict[Isin, pd.Series]:
    currency = data.dataset.currency
    out = {}
    for column in data.dataset.data.columns:
        isin = Isin(str(column))
        if data.price_types[str(column)] is not PriceType.TOTAL_RETURN:
            raise ValidationError(
                f"total_returns: the column of {isin.code} must declare "
                f'price_type = "total_return", not "{data.price_types[str(column)].value}"'
            )
        if isin not in prices:
            raise ValidationError(f"total_returns: {isin.code} has no price file")
        if currency != prices[isin].currency:
            raise ValidationError(
                f"total_returns: {isin.code} must be in {prices[isin].currency.code}, the same "
                "currency as its price file"
            )
        out[isin] = data.dataset.data[column].dropna().astype("float64").rename(isin.code)
    return out


def _adjusted(
    isin: Isin, price: pd.Series, currency: Currency, payments: tuple[Payment, ...]
) -> pd.Series:
    wrong = [p for p in payments if p.currency != currency]
    if wrong:
        raise ValidationError(
            f"[parameters.distributions] {isin.code}: a distribution in "
            f"{wrong[0].currency.code}, its price file in {currency.code}; they must match"
        )
    paid = pd.Series(
        [p.per_unit for p in payments],
        index=pd.DatetimeIndex([pd.Timestamp(p.ex_date) for p in payments]),
        dtype="float64",
    )
    try:
        return distribution_adjusted(price, paid)
    except ValidationError as error:
        raise ValidationError(f"[parameters.distributions] {isin.code}: {error}") from error
