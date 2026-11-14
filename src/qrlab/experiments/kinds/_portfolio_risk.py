"""Risk and stress tests of the ``portfolio_report`` kind, from its own prices (design 8.3).

Position returns are built from the price files the report reads. Each price series and each
currency's ECB rate is resampled to its last value in each week or month; a position's value
in the base currency in a period is its last price times the last rate of that period. Foreign
cash returns its currency's return; base cash returns 0 and is left out. The risk is that of
**today's weights** applied to past returns, a "what if this portfolio had been held", not the
time-weighted return. Nothing is filled: a position that lacks the window raises.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from qrlab.core.calendar import CONVENTIONAL_PERIODS_PER_YEAR, Frequency, infer_frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.provenance import Dataset
from qrlab.data.user_csv import PriceType
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._frames import covariance_spec, estimate_covariance
from qrlab.experiments.kinds._params import choice, number, whole
from qrlab.experiments.registry import Tagged
from qrlab.instruments.identifiers import Isin
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var
from qrlab.portfolio.valuation import PriceSeries
from qrlab.risk.decomposition import volatility_contributions
from qrlab.risk.var_methods import cornish_fisher
from qrlab.scenarios.definitions import HistoricalScenario, Scenario
from qrlab.scenarios.engine import (
    MarketData,
    PositionSeries,
    ScenarioResult,
    StressPortfolio,
    run_scenario,
)
from qrlab.scenarios.summary import RiskSummary

__all__ = ["PRICE_ONLY", "RiskOutputs", "RiskSpec", "compute_risk", "parse_risk", "unit_values"]

_FREQUENCIES = {"weekly": Frequency.WEEKLY, "monthly": Frequency.MONTHLY}
# Price-file frequencies fine enough for each risk frequency.
_FINE_ENOUGH = {
    Frequency.WEEKLY: {Frequency.DAILY, Frequency.WEEKLY},
    Frequency.MONTHLY: {Frequency.DAILY, Frequency.WEEKLY, Frequency.MONTHLY},
}
_PERIOD = {Frequency.WEEKLY: "W-FRI", Frequency.MONTHLY: "M"}
_EUR = Currency("EUR")
PRICE_ONLY = (
    "Risk is computed from price returns for {names}: their return levels exclude dividends; "
    "volatilities and correlations are barely affected."
)


@dataclass(frozen=True)
class RiskSpec:
    """``[parameters.risk]``: frequency, window, confidence and covariance estimator."""

    name: str
    frequency: Frequency
    window: int
    confidence: float
    covariance: Mapping[str, object]


@dataclass(frozen=True)
class RiskOutputs:
    """What the kind adds to its outputs and passes to the report."""

    summary: RiskSummary
    tables: Mapping[str, Tagged]
    scalars: Mapping[str, Tagged]
    price_only: tuple[str, ...]  # positions whose risk uses price returns (no dividends)


def parse_risk(parameters: Mapping[str, object]) -> RiskSpec | None:
    """Read ``[parameters.risk]``, or ``None`` when it is absent."""
    if "risk" not in parameters:
        return None
    spec = parameters["risk"]
    if not isinstance(spec, dict):
        raise ValidationError("[parameters.risk] must be a table")
    require_keys(
        spec,
        required={"frequency", "window", "confidence", "covariance"},
        optional=set(),
        where="[parameters.risk]",
    )
    name = choice(spec, "frequency", set(_FREQUENCIES))
    confidence = number(spec, "confidence")
    if not 0.5 < confidence < 1.0:
        raise ValidationError("[parameters.risk] confidence must be in (0.5, 1), e.g. 0.95")
    return RiskSpec(
        name=name,
        frequency=_FREQUENCIES[name],
        window=whole(spec, "window", minimum=2),
        confidence=confidence,
        covariance=covariance_spec(spec),
    )


def unit_values(fx: Dataset | None, base: Currency, currencies: set[Currency]) -> pd.DataFrame:
    """Return the value of one unit of each foreign currency in ``base``, on the ECB dates."""
    needed = sorted(currencies - {base}, key=lambda c: c.code)
    if not needed:
        return pd.DataFrame()
    if fx is None:
        raise ValidationError(
            f"risk in {base.code} needs an fx input for {[c.code for c in needed]}"
        )
    rates = fx.data

    def per_eur(currency: Currency) -> pd.Series | float:
        if currency == _EUR:
            return 1.0
        if currency.code not in rates.columns:
            raise ValidationError(f"no ECB rate for {currency.code}")
        return rates[currency.code].astype("float64")

    base_rate = per_eur(base)
    return pd.DataFrame({c.code: base_rate / per_eur(c) for c in needed}, index=rates.index)


def compute_risk(
    spec: RiskSpec,
    *,
    as_of: date,
    value: float,
    base: Currency,
    prices: Mapping[Isin, PriceSeries],
    names: Mapping[Isin, str],
    position_weights: Mapping[Isin, float],
    cash_weights: Mapping[Currency, float],
    exposure_currencies: Mapping[Isin, Currency],
    fx: Dataset | None,
    scenarios: Sequence[Scenario],
) -> RiskOutputs:
    """Build the risk summary of today's portfolio from its price files."""
    held = sorted((i for i, w in position_weights.items() if w != 0.0), key=lambda i: i.code)
    foreign = sorted(
        (c for c, w in cash_weights.items() if c != base and w != 0.0), key=lambda c: c.code
    )
    units = unit_values(fx, base, {prices[i].currency for i in held} | set(foreign))
    rule = spec.frequency.value
    periodic: dict[str, pd.Series] = {}
    local: dict[Isin, pd.Series] = {}
    for isin in held:
        series = prices[isin].prices.dropna().astype("float64")
        found = infer_frequency(pd.DatetimeIndex(series.index))
        if found not in _FINE_ENOUGH[spec.frequency]:
            observed = found.name.lower() if found is not None else "irregular"
            raise ValidationError(
                f"{isin.code}: prices are {observed}, too coarse for {spec.name} risk returns"
            )
        local[isin] = series.pct_change(fill_method=None).iloc[1:]
        value_in_base = series.resample(rule).last()
        currency = prices[isin].currency
        if currency != base:
            value_in_base = value_in_base * units[currency.code].dropna().resample(rule).last()
        periodic[isin.code] = value_in_base.pct_change(fill_method=None)
    for currency in foreign:
        unit = units[currency.code].dropna().resample(rule).last()
        periodic[f"cash {currency.code}"] = unit.pct_change(fill_method=None)
    returns = _window(pd.DataFrame(periodic), spec, as_of)
    weights = pd.Series(
        {i.code: position_weights[i] for i in held}
        | {f"cash {c.code}": cash_weights[c] for c in foreign}
    )
    volatility = volatility_contributions(estimate_covariance(returns, spec.covariance), weights)
    portfolio = (returns * weights).sum(axis=1).rename("portfolio")
    var_es, notes = _var_es(portfolio, spec.confidence)
    market = MarketData(
        positions={i: PositionSeries(local[i], prices[i].currency) for i in held},
        factors=pd.DataFrame(index=pd.DatetimeIndex([], name="date")),
        betas=None,
        fx={
            Currency(str(code)): units[code].dropna().pct_change(fill_method=None).iloc[1:]
            for code in units.columns
        },
    )
    stress = StressPortfolio(
        as_of=as_of,
        value=Money.of(f"{value:.2f}", base.code),
        position_weights={i: position_weights[i] for i in held},
        cash_weights={c: w for c, w in cash_weights.items() if w != 0.0},
        exposure_currencies={i: exposure_currencies[i] for i in held},
    )
    results = tuple(run_scenario(s, stress, market) for s in scenarios)
    summary = RiskSummary(
        as_of=as_of,
        frequency=spec.name,
        window_start=returns.index[0].date(),
        window_end=min(returns.index[-1].date(), as_of),
        n_obs=len(returns),
        confidence=spec.confidence,
        volatility=volatility,
        var_es={m: v for m, v in var_es.items() if m not in notes},
        scenarios=results,
    )
    contributions = pd.DataFrame(
        {"weight": weights, "contribution": volatility.component, "share": volatility.share}
    ).rename_axis("holding")
    var_table = pd.DataFrame(
        {
            "var": [v for v, _ in var_es.values()],
            "es": [e for _, e in var_es.values()],
            "note": [notes.get(m, "") for m in var_es],
        },
        index=pd.Index(list(var_es), name="method"),
    )
    tables = {
        "risk_returns": Tagged(
            returns.assign(portfolio=portfolio).rename_axis("period"), "descriptive"
        ),
        "risk_contributions": Tagged(contributions, "descriptive"),
        "var_es": Tagged(var_table, "descriptive"),
    }
    if results:
        tables["scenarios"] = Tagged(_scenario_table(results), "descriptive")
    annual = math.sqrt(CONVENTIONAL_PERIODS_PER_YEAR[spec.frequency])
    scalars = {
        "volatility_period": Tagged(volatility.total, "descriptive"),
        "volatility_annual": Tagged(volatility.total * annual, "descriptive"),
    }
    if "historical" not in notes:
        scalars["var_historical"] = Tagged(var_es["historical"][0], "descriptive")
        scalars["es_historical"] = Tagged(var_es["historical"][1], "descriptive")
    price_only = tuple(
        names.get(i, i.code) for i in held if prices[i].price_type is PriceType.PRICE
    )
    return RiskOutputs(summary, tables, scalars, price_only)


def _window(periodic: pd.DataFrame, spec: RiskSpec, as_of: date) -> pd.DataFrame:
    """Return the last ``window`` returns up to the period of ``as_of``; a gap names the column."""
    end = pd.Timestamp(as_of).to_period(_PERIOD[spec.frequency]).end_time.normalize()
    window = periodic.loc[periodic.index <= end].iloc[-spec.window :]
    short = [c for c in window.columns if len(window) < spec.window or window[c].isna().any()]
    if short:
        details = []
        for column in short:
            valid = pd.DatetimeIndex(periodic[column].dropna().index)
            since = "no returns" if valid.empty else f"returns from {valid[0].date()}"
            details.append(f"{column} ({since})")
        raise ValidationError(
            f"a window of {spec.window} {spec.name} returns ending {end.date()} is not covered "
            f"by {', '.join(details)}: shorten the window or give longer price files"
        )
    return window


def _var_es(
    returns: pd.Series, confidence: float
) -> tuple[dict[str, tuple[float, float]], dict[str, str]]:
    """Return VaR and ES by method (positive losses), with the reason for any undefined one.

    A method is undefined, never forced, when its figures do not exist for these returns: too
    few observations for the tail of the historical method, or a Cornish-Fisher expansion that
    is not a quantile. It is then NaN with a note.
    """
    methods: dict[str, Callable[[], tuple[float, float]]] = {
        "historical": lambda: (
            historical_var(returns, confidence=confidence),
            historical_es(returns, confidence=confidence),
        ),
        "normal": lambda: (
            parametric_var(returns, confidence=confidence),
            parametric_es(returns, confidence=confidence),
        ),
        "Cornish-Fisher": lambda: _cornish_fisher(returns, confidence),
    }
    out: dict[str, tuple[float, float]] = {}
    notes: dict[str, str] = {}
    for name, method in methods.items():
        try:
            out[name] = method()
        except UndefinedMetricError as exc:  # reported, not run
            out[name] = (math.nan, math.nan)
            notes[name] = str(exc)
    return out, notes


def _cornish_fisher(returns: pd.Series, confidence: float) -> tuple[float, float]:
    result = cornish_fisher(returns, confidence=confidence)
    return result.var, result.es


def _scenario_table(results: Sequence[ScenarioResult]) -> pd.DataFrame:
    rows = [
        {
            "scenario": r.scenario.id,
            "description": r.scenario.description,
            "kind": "historical" if isinstance(r.scenario, HistoricalScenario) else "hypothetical",
            "portfolio_return": r.portfolio_return,
            "pnl": float(r.pnl.amount),
            "not_covered_weight": r.not_covered_weight,
        }
        for r in results
    ]
    return pd.DataFrame(rows).set_index("scenario")
