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

import numpy as np
import pandas as pd

from qrlab.core.calendar import CONVENTIONAL_PERIODS_PER_YEAR, Frequency, infer_frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.provenance import Dataset
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._frames import covariance_spec, estimate_covariance
from qrlab.experiments.kinds._params import choice, number, whole
from qrlab.experiments.registry import Tagged
from qrlab.instruments.identifiers import Isin
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var
from qrlab.portfolio.valuation import PriceSeries
from qrlab.risk.decomposition import volatility_contributions
from qrlab.risk.var_backtest import VarBacktest, var_backtest, var_forecasts
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

__all__ = [
    "BACKTEST_MODELS",
    "BacktestSpec",
    "RiskOutputs",
    "RiskSpec",
    "compute_risk",
    "parse_risk",
    "unit_values",
]

_FREQUENCIES = {"weekly": Frequency.WEEKLY, "monthly": Frequency.MONTHLY}
# Price-file frequencies fine enough for each risk frequency.
_FINE_ENOUGH = {
    Frequency.WEEKLY: {Frequency.DAILY, Frequency.WEEKLY},
    Frequency.MONTHLY: {Frequency.DAILY, Frequency.WEEKLY, Frequency.MONTHLY},
}
_PERIOD = {Frequency.WEEKLY: "W-FRI", Frequency.MONTHLY: "M"}
_EUR = Currency("EUR")


BACKTEST_MODELS = ("historical", "normal", "cornish_fisher")


@dataclass(frozen=True)
class BacktestSpec:
    """``[parameters.risk.backtest]``: returns per forecast and the VaR model (11.4)."""

    window: int
    model: str


@dataclass(frozen=True)
class RiskSpec:
    """``[parameters.risk]``: frequency, window, confidence and covariance estimator.

    Optional (design note 11.4): ``backtest`` and ``proxies`` (ISIN -> factor -> beta).
    """

    name: str
    frequency: Frequency
    window: int
    confidence: float
    covariance: Mapping[str, object]
    backtest: BacktestSpec | None = None
    proxies: Mapping[Isin, Mapping[str, float]] | None = None


@dataclass(frozen=True)
class RiskOutputs:
    """What the kind adds to its outputs and passes to the report."""

    summary: RiskSummary
    tables: Mapping[str, Tagged]
    scalars: Mapping[str, Tagged]


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
        optional={"backtest", "proxies"},
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
        backtest=_parse_backtest(spec),
        proxies=_parse_proxies(spec),
    )


def _parse_backtest(spec: Mapping[str, object]) -> BacktestSpec | None:
    if "backtest" not in spec:
        return None
    table = spec["backtest"]
    if not isinstance(table, dict):
        raise ValidationError("[parameters.risk.backtest] must be a table with window and model")
    require_keys(
        table, required={"window", "model"}, optional=set(), where="[parameters.risk.backtest]"
    )
    return BacktestSpec(
        window=whole(table, "window", minimum=2), model=choice(table, "model", set(BACKTEST_MODELS))
    )


def _parse_proxies(spec: Mapping[str, object]) -> dict[Isin, dict[str, float]] | None:
    if "proxies" not in spec:
        return None
    table = spec["proxies"]
    if not isinstance(table, dict) or not table:
        raise ValidationError(
            "[parameters.risk.proxies] must hold, per ISIN, a table of factor = beta"
        )
    out: dict[Isin, dict[str, float]] = {}
    for code, betas in table.items():
        where = f"[parameters.risk.proxies.{code}]"
        if not isinstance(betas, dict) or not betas:
            raise ValidationError(f"{where} must be a non-empty table of factor = beta")
        out[Isin(code)] = {str(factor): number(betas, factor) for factor in betas}
    return out


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
    position_weights: Mapping[Isin, float],
    cash_weights: Mapping[Currency, float],
    exposure_currencies: Mapping[Isin, Currency],
    fx: Dataset | None,
    scenarios: Sequence[Scenario],
    levels: Mapping[Isin, pd.Series] | None = None,
    factors: pd.DataFrame | None = None,
) -> RiskOutputs:
    """Build the risk summary of today's portfolio from its price files.

    ``levels`` gives, by ISIN, the series whose returns a position uses in place of its prices
    (design note 11.1: a total-return series, or the prices adjusted for distributions), in
    the price file's currency. ``factors`` gives factor returns (columns are factor names) for
    the proxies of ``spec`` (design note 11.4).
    """
    held = sorted((i for i, w in position_weights.items() if w != 0.0), key=lambda i: i.code)
    foreign = sorted(
        (c for c, w in cash_weights.items() if c != base and w != 0.0), key=lambda c: c.code
    )
    units = unit_values(fx, base, {prices[i].currency for i in held} | set(foreign))
    rule = spec.frequency.value
    periodic: dict[str, pd.Series] = {}
    local: dict[Isin, pd.Series] = {}
    for isin in held:
        series = (
            levels[isin]
            if levels is not None and isin in levels
            else prices[isin].prices.dropna().astype("float64")
        )
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
    frame = pd.DataFrame(periodic)
    returns = _window(frame, spec, as_of)
    weights = pd.Series(
        {i.code: position_weights[i] for i in held}
        | {f"cash {c.code}": cash_weights[c] for c in foreign}
    )
    volatility = volatility_contributions(estimate_covariance(returns, spec.covariance), weights)
    portfolio = (returns * weights).sum(axis=1).rename("portfolio")
    var_es, notes = _var_es(portfolio, spec.confidence)
    betas = _betas(spec, held, factors)
    market = MarketData(
        positions={i: PositionSeries(local[i], prices[i].currency) for i in held},
        factors=pd.DataFrame(index=pd.DatetimeIndex([], name="date"))
        if factors is None
        else factors,
        betas=betas,
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
    backtest = _backtest(spec, frame, weights, as_of)
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
        backtest=None if backtest is None else backtest[0],
        backtest_window=0 if spec.backtest is None else spec.backtest.window,
        backtest_model="" if spec.backtest is None else spec.backtest.model,
        proxies=None
        if spec.proxies is None
        else {i.code: dict(betas) for i, betas in spec.proxies.items()},
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
    if backtest is not None:
        test, path = backtest
        tables["var_backtest"] = Tagged(path, "out_of_sample")
        scalars |= {
            "backtest_exceedances": Tagged(float(test.exceedances), "out_of_sample"),
            "backtest_expected": Tagged(test.expected, "out_of_sample"),
            "kupiec_pvalue": Tagged(test.kupiec_pvalue, "out_of_sample"),
            "independence_pvalue": Tagged(test.independence_pvalue, "out_of_sample"),
            "conditional_coverage_pvalue": Tagged(
                test.conditional_coverage_pvalue, "out_of_sample"
            ),
        }
    if "historical" not in notes:
        scalars["var_historical"] = Tagged(var_es["historical"][0], "descriptive")
        scalars["es_historical"] = Tagged(var_es["historical"][1], "descriptive")
    return RiskOutputs(summary, tables, scalars)


def _betas(
    spec: RiskSpec, held: Sequence[Isin], factors: pd.DataFrame | None
) -> pd.DataFrame | None:
    """Return the proxies' betas, positions by factors (a factor not listed has beta 0)."""
    if spec.proxies is None:
        return None
    assert factors is not None  # the kind requires a factors input with proxies
    not_held = sorted(i.code for i in spec.proxies if i not in held)
    if not_held:
        raise ValidationError(f"[parameters.risk.proxies]: {not_held} are not held")
    names = sorted({f for betas in spec.proxies.values() for f in betas})
    absent = sorted(set(names) - {str(c) for c in factors.columns})
    if absent:
        raise ValidationError(f"[parameters.risk.proxies]: no factor returns for {absent}")
    return pd.DataFrame(
        [[spec.proxies[i].get(f, 0.0) for f in names] for i in spec.proxies],
        index=pd.Index([i.code for i in spec.proxies]),
        columns=pd.Index(names),
        dtype="float64",
    )


def _backtest(
    spec: RiskSpec, frame: pd.DataFrame, weights: pd.Series, as_of: date
) -> tuple[VarBacktest, pd.DataFrame] | None:
    """Backtest the VaR model on today's weights over the common history (design note 11.4).

    The history is the last run of periods, up to the period of ``as_of``, in which every
    holding has a return; rows are never joined across a gap.
    """
    if spec.backtest is None:
        return None
    end = pd.Timestamp(as_of).to_period(_PERIOD[spec.frequency]).end_time.normalize()
    history = frame.loc[frame.index <= end, list(weights.index)]
    complete = history.notna().all(axis=1).to_numpy()
    trailing = np.cumprod(complete[::-1])[::-1].astype(bool)  # the last run of complete rows
    history = history.loc[trailing]
    portfolio = (history * weights).sum(axis=1).rename("portfolio")
    window, model = spec.backtest.window, _var_model(spec.backtest.model, spec.confidence)
    where = "[parameters.risk.backtest]"
    if len(portfolio) < window + 2:
        raise ValidationError(
            f"{where}: {len(portfolio)} {spec.name} returns at today's weights give fewer than "
            f"2 forecasts after a window of {window}; give longer price files or a shorter window"
        )
    forecasts = var_forecasts(portfolio, window=window, model=model)
    realised = portfolio.loc[forecasts.index]
    test = var_backtest(realised, forecasts, confidence=spec.confidence)
    path = pd.DataFrame(
        {"return": realised, "var": forecasts, "exceedance": realised < -forecasts}
    ).rename_axis("period")
    return test, path


def _var_model(name: str, confidence: float) -> Callable[[pd.Series], float]:
    if name == "historical":
        return lambda r: historical_var(r, confidence=confidence)
    if name == "normal":
        return lambda r: parametric_var(r, confidence=confidence)
    return lambda r: cornish_fisher(r, confidence=confidence).var


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
