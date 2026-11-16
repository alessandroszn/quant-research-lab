"""The portfolio against a benchmark, in the ``portfolio_report`` kind (design note 11.2).

The benchmark is a total-return series in its own currency. On each valuation date its value in
the base currency is its last level, no older than ``max_price_age_days``, times the last ECB
rate, no older than ``fx_max_age_days``. Its period returns are compared with the TWR on the
periods between two valuation dates (a return on the first date, from a deposit to that day's
close, has no benchmark return and is left out, as for the Sharpe ratio of 8.5). The measures
come from :mod:`qrlab.metrics.relative`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data.provenance import Dataset
from qrlab.data.user_csv import PriceData, PriceType
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import text
from qrlab.experiments.kinds._portfolio_risk import unit_values
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.relative import CapmEstimate, capm_regression, information_ratio, tracking_error
from qrlab.reporting.portfolio_report import BenchmarkSummary

__all__ = ["BenchmarkOutputs", "BenchmarkSpec", "benchmark_series", "compare", "parse_benchmark"]

MONTHLY = 12.0
_T = TypeVar("_T")


@dataclass(frozen=True)
class BenchmarkSpec:
    """``[parameters.benchmark]``: the name shown in the report."""

    name: str


@dataclass(frozen=True)
class BenchmarkOutputs:
    """What the kind adds to its outputs, passes to the report and gives the checks."""

    summary: BenchmarkSummary
    table: pd.DataFrame
    scalars: Mapping[str, float]
    portfolio_returns: pd.Series
    benchmark_returns: pd.Series


def parse_benchmark(parameters: Mapping[str, object]) -> BenchmarkSpec | None:
    """Read ``[parameters.benchmark]``, or ``None`` when it is absent."""
    if "benchmark" not in parameters:
        return None
    spec = parameters["benchmark"]
    if not isinstance(spec, dict):
        raise ValidationError("[parameters.benchmark] must be a table with name")
    require_keys(spec, required={"name"}, optional=set(), where="[parameters.benchmark]")
    return BenchmarkSpec(text(spec, "name"))


def benchmark_series(data: PriceData) -> tuple[pd.Series, Currency]:
    """Return the one total-return column of the benchmark file and its currency."""
    columns = [str(c) for c in data.dataset.data.columns]
    if len(columns) != 1:
        raise ValidationError(f"the benchmark file needs exactly one column, got {columns}")
    kind = data.price_types[columns[0]]
    if kind is not PriceType.TOTAL_RETURN:
        raise ValidationError(
            f'the benchmark column must declare price_type = "total_return", not "{kind.value}": '
            "the portfolio's TWR includes the income received. An accumulating fund's price is "
            "a total-return series"
        )
    currency = data.dataset.currency
    assert currency is not None  # a price mapping always has a currency
    return data.dataset.data[columns[0]].dropna().astype("float64"), currency


def compare(
    spec: BenchmarkSpec,
    *,
    level: pd.Series,
    currency: Currency,
    base: Currency,
    fx: Dataset | None,
    fx_max_age_days: int | None,
    max_price_age_days: int,
    dates: Sequence[date],
    twr_returns: pd.Series,
    risk_free: pd.Series | None,
    monthly: bool,
) -> BenchmarkOutputs:
    """Compare the TWR with the benchmark over the periods between two valuation dates."""
    carried: list[tuple[str, date, date]] = []
    value = _levels_in_base(
        level, currency, base, fx, fx_max_age_days, max_price_age_days, dates, carried
    )
    twr = dict(
        zip(
            (stamp.date() for stamp in pd.DatetimeIndex(twr_returns.index)),
            twr_returns.to_numpy(dtype="float64"),
            strict=True,
        )
    )
    ends = [d for d in dates[1:] if d in twr]
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in ends], name="period_end")
    portfolio = pd.Series(
        [float(twr[d]) for d in ends], index=index, name="portfolio", dtype="float64"
    )
    previous_of = dict(zip(dates[1:], dates, strict=False))
    bench = pd.Series(
        [value[d] / value[previous_of[d]] - 1.0 for d in ends],
        index=index,
        name="benchmark",
        dtype="float64",
    )
    table = pd.DataFrame({"portfolio": portfolio, "benchmark": bench, "active": portfolio - bench})
    reasons: dict[str, str] = {}
    scalars: dict[str, float] = {}
    te = ir = None
    fit: CapmEstimate | None = None
    p_total: float | None = None
    b_total: float | None = None
    if ends:
        p_total = float(np.prod(1.0 + portfolio.to_numpy()) - 1.0)
        b_total = float(np.prod(1.0 + bench.to_numpy()) - 1.0)
        scalars |= {"benchmark_total": b_total, "active_total": p_total - b_total}
    x, y = bench, portfolio
    if risk_free is not None:
        rf = risk_free.reindex(index)
        if rf.isna().any():
            raise ValidationError("the risk-free series does not cover every benchmark period")
        table["risk_free"] = rf.to_numpy()
        x = (bench - rf).rename("excess_benchmark")
        y = (portfolio - rf).rename("excess_portfolio")
        table["excess_portfolio"] = y.to_numpy()
        table["excess_benchmark"] = x.to_numpy()
    if not monthly:
        reason = 'annualised measures need return_frequency = "monthly"'
        reasons = {"tracking_error": reason, "information_ratio": reason, "capm": reason}
    else:
        te = _measure(reasons, "tracking_error", lambda: tracking_error(
            portfolio, bench, periods_per_year=MONTHLY))  # fmt: skip
        ir = _measure(reasons, "information_ratio", lambda: information_ratio(
            portfolio, bench, periods_per_year=MONTHLY))  # fmt: skip
        fit = _measure(reasons, "capm", lambda: capm_regression(
            y, x, periods_per_year=MONTHLY))  # fmt: skip
    if te is not None:
        scalars["tracking_error"] = te
    if ir is not None:
        scalars["information_ratio"] = ir
    if fit is not None:
        scalars |= {
            "beta": fit.beta,
            "beta_se": fit.se_beta,
            "alpha_annual": fit.alpha_annualised,
            "alpha_annual_se": fit.se_alpha_annualised,
            "r_squared": fit.r_squared,
        }
    summary = BenchmarkSummary(
        name=spec.name,
        currency=currency,
        window_start=ends[0] if ends else None,
        window_end=ends[-1] if ends else None,
        n_periods=len(ends),
        portfolio_total=p_total,
        benchmark_total=b_total,
        tracking_error=te,
        information_ratio=ir,
        capm=fit,
        on_excess=risk_free is not None,
        reasons=reasons,
        carried=tuple(carried),
    )
    return BenchmarkOutputs(summary, table, scalars, portfolio, bench)


def _measure(reasons: dict[str, str], name: str, compute: Callable[[], _T]) -> _T | None:
    try:
        return compute()
    except UndefinedMetricError as error:
        reasons[name] = str(error)
        return None


def _levels_in_base(
    level: pd.Series,
    currency: Currency,
    base: Currency,
    fx: Dataset | None,
    fx_max_age_days: int | None,
    max_price_age_days: int,
    dates: Sequence[date],
    carried: list[tuple[str, date, date]],
) -> dict[date, float]:
    if currency != base and fx is None:
        raise ValidationError(
            f"the benchmark is in {currency.code}: a {base.code} report needs an fx input to "
            "convert it"
        )
    rates = None
    if currency != base:
        rates = unit_values(fx, base, {currency})[currency.code].dropna()
    out = {}
    for day in dates:
        amount, used = _last(level, day, max_price_age_days, "benchmark level")
        if used != day:
            carried.append(("level", day, used))
        if rates is not None:
            assert fx_max_age_days is not None  # required with an fx input
            rate, on = _last(rates, day, fx_max_age_days, f"{currency.code} rate")
            if on != day:
                carried.append((f"{currency.code} rate", day, on))
            amount *= rate
        out[day] = amount
    return out


def _last(series: pd.Series, day: date, max_age_days: int, what: str) -> tuple[float, date]:
    before = series.loc[: pd.Timestamp(day)]
    if before.empty:
        raise ValidationError(f"no {what} on or before {day}")
    used = pd.Timestamp(before.index[-1]).date()
    if (day - used).days > max_age_days:
        raise ValidationError(
            f"the {what} on {day} would come from {used}, older than {max_age_days} days"
        )
    return float(before.iloc[-1]), used
