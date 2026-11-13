"""Experiment kind ``risk_report``: portfolio risk from an asset-returns CSV and fixed weights.

Input ``returns``: simple returns, one column per asset (``[parameters.returns_format]``).

- **Covariance** (``[parameters.covariance]``: sample, EWMA or Ledoit-Wolf) and the effective
  number of bets.
- **Contributions** of each asset to volatility, historical ES and normal ES; each sums to the
  portfolio figure.
- **VaR and ES** of the portfolio's returns, per period, at ``confidence``: historical, normal,
  Cornish-Fisher and filtered historical simulation (EWMA filter, ``[parameters.filtered]``).
  Cornish-Fisher is left empty, with the reason, when its expansion is not a quantile.
- **VaR backtest** (``[parameters.backtest]``): one-step forecasts from the ``window`` returns
  before each date with the chosen ``model``, then Kupiec and Christoffersen tests.

Risk measured on the whole history is descriptive; the VaR backtest uses only past data for
each forecast and is tagged ``out_of_sample``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import pandas as pd

from qrlab.core.calendar import require_periods_per_year
from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._frames import (
    covariance_spec,
    estimate_covariance,
    read_returns,
    returns_format,
    weights,
)
from qrlab.experiments.kinds._params import choice, number, table, whole
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var
from qrlab.risk.decomposition import (
    effective_number_of_bets,
    historical_es_contributions,
    normal_es_contributions,
    volatility_contributions,
)
from qrlab.risk.var_backtest import var_backtest, var_forecasts
from qrlab.risk.var_methods import cornish_fisher, filtered_historical

__all__ = ["BACKTEST_MODELS", "KIND"]

BACKTEST_MODELS = ("historical", "normal", "cornish_fisher")

_PARAMETERS = (
    "returns_format",
    "weights",
    "covariance",
    "confidence",
    "periods_per_year",
    "filtered",
    "backtest",
)


@dataclass(frozen=True)
class _Parameters:
    returns_format: Mapping[str, str]
    weights: Mapping[str, object]
    covariance: Mapping[str, object]
    confidence: float
    periods_per_year: int
    filtered_decay: float
    filtered_warmup: int
    window: int
    model: str


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    confidence = number(parameters, "confidence")
    if not 0.5 < confidence < 1.0:
        raise ValidationError("confidence must be in (0.5, 1), e.g. 0.99")
    filtered = table(parameters, "filtered", required={"decay", "warmup"}, optional=set())
    backtest = table(parameters, "backtest", required={"window", "model"}, optional=set())
    weights_value = parameters["weights"]
    if not isinstance(weights_value, dict) or not weights_value:
        raise ValidationError("weights must be a non-empty table of asset = weight")
    return _Parameters(
        returns_format=returns_format(parameters),
        weights=weights_value,
        covariance=covariance_spec(parameters),
        confidence=confidence,
        periods_per_year=whole(parameters, "periods_per_year", minimum=1),
        filtered_decay=number(filtered, "decay"),
        filtered_warmup=whole(filtered, "warmup", minimum=1),
        window=whole(backtest, "window", minimum=2),
        model=choice(backtest, "model", set(BACKTEST_MODELS)),
    )


def _var_model(name: str, confidence: float) -> Callable[[pd.Series], float]:
    if name == "historical":
        return lambda r: historical_var(r, confidence=confidence)
    if name == "normal":
        return lambda r: parametric_var(r, confidence=confidence)
    return lambda r: cornish_fisher(r, confidence=confidence).var


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    returns = read_returns(context.inputs["returns"].read_bytes(), p.returns_format)
    require_periods_per_year(p.periods_per_year, returns.index)
    assets = [str(c) for c in returns.columns]
    w = weights(p.weights, assets)
    portfolio = (returns * w).sum(axis=1).rename("portfolio")
    cov = estimate_covariance(returns, p.covariance)
    common = {"confidence": p.confidence, "kind": ReturnKind.SIMPLE, "missing": NanPolicy.RAISE}
    vol = volatility_contributions(cov, w)
    hist = historical_es_contributions(returns, w, **common)  # type: ignore[arg-type]
    normal = normal_es_contributions(returns, w, **common)  # type: ignore[arg-type]
    contributions = pd.DataFrame(
        {
            "weight": w,
            "volatility": vol.component,
            "volatility_share": vol.share,
            "marginal_volatility": vol.marginal,
            "historical_es": hist.component,
            "historical_es_share": hist.share,
            "normal_es": normal.component,
            "normal_es_share": normal.share,
        }
    )
    contributions.index.name = "asset"
    try:
        cf = cornish_fisher(portfolio, confidence=p.confidence)
        cf_values, cf_note = (cf.var, cf.es), ""
    except UndefinedMetricError as exc:  # not a quantile for these moments: reported, not run
        cf_values, cf_note = (math.nan, math.nan), str(exc)
    fhs = filtered_historical(
        portfolio, confidence=p.confidence, decay=p.filtered_decay, warmup=p.filtered_warmup
    )
    var_es = pd.DataFrame(
        {
            "var": [
                historical_var(portfolio, confidence=p.confidence),
                parametric_var(portfolio, confidence=p.confidence),
                cf_values[0],
                fhs.var,
            ],
            "es": [
                historical_es(portfolio, confidence=p.confidence),
                parametric_es(portfolio, confidence=p.confidence),
                cf_values[1],
                fhs.es,
            ],
            "note": ["", "", cf_note, ""],
        },
        index=pd.Index(
            ["historical", "normal", "cornish_fisher", "filtered_historical"], name="method"
        ),
    )
    forecasts = var_forecasts(portfolio, window=p.window, model=_var_model(p.model, p.confidence))
    test = var_backtest(portfolio.loc[forecasts.index], forecasts, confidence=p.confidence)
    path = pd.DataFrame(
        {
            "return": portfolio.loc[forecasts.index],
            "var": forecasts,
            "exceedance": portfolio.loc[forecasts.index] < -forecasts,
        }
    )
    scalars = {
        "volatility_annual": Tagged(vol.total * math.sqrt(p.periods_per_year), "descriptive"),
        "effective_number_of_bets": Tagged(effective_number_of_bets(cov, w), "descriptive"),
        "backtest_exceedances": Tagged(float(test.exceedances), "out_of_sample"),
        "backtest_expected": Tagged(test.expected, "out_of_sample"),
        "kupiec_pvalue": Tagged(test.kupiec_pvalue, "out_of_sample"),
        "independence_pvalue": Tagged(test.independence_pvalue, "out_of_sample"),
        "conditional_coverage_pvalue": Tagged(test.conditional_coverage_pvalue, "out_of_sample"),
    }
    return ExperimentOutput(
        tables={
            "covariance": Tagged(cov.matrix, "descriptive"),
            "contributions": Tagged(contributions, "descriptive"),
            "var_es": Tagged(var_es, "descriptive"),
            "var_backtest": Tagged(path, "out_of_sample"),
        },
        scalars=scalars,
    )


KIND = ExperimentKind(
    name="risk_report",
    description="Portfolio risk: covariance, contributions, VaR/ES and a VaR backtest",
    inputs=("returns",),
    needs_seed=False,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
