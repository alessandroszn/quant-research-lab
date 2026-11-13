"""Experiment kind ``optimisation``: portfolio weights from an asset-returns CSV.

Input ``returns``: simple returns, one column per asset (``[parameters.returns_format]``).

``[parameters.method]`` has a ``name`` and its own keys:

- ``equal_weights``, ``minimum_variance``: within ``[parameters.bounds]``;
- ``mean_variance``: ``risk_aversion``, expected returns = sample means, within the bounds;
- ``maximum_sharpe``: ``risk_free_per_period`` subtracted from the sample means (long-only);
- ``risk_parity`` (equal risk contributions), ``maximum_diversification``, ``hrp`` (long-only).

``[parameters.bounds]`` gives ``min`` and ``max`` for every asset (long-only when ``min`` >= 0).
The weights are fitted on the whole file: in sample, a description of what the method does with
these estimates, not a forecast and not advice.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from qrlab.core.calendar import require_periods_per_year
from qrlab.core.errors import ValidationError
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._frames import (
    covariance_spec,
    estimate_covariance,
    read_returns,
    returns_format,
)
from qrlab.experiments.kinds._params import choice, number, table, whole
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.optimization.constraints import Constraints
from qrlab.optimization.mean_variance import (
    OptimizationResult,
    equal_weights,
    maximum_sharpe,
    mean_variance,
    minimum_variance,
)
from qrlab.optimization.risk_based import (
    hierarchical_risk_parity,
    maximum_diversification,
    risk_budgeting,
)
from qrlab.risk.covariance import CovarianceEstimate
from qrlab.risk.decomposition import effective_number_of_bets, volatility_contributions

__all__ = ["KIND", "METHODS"]

METHODS: Mapping[str, set[str]] = {
    "equal_weights": set(),
    "minimum_variance": set(),
    "mean_variance": {"risk_aversion"},
    "maximum_sharpe": {"risk_free_per_period"},
    "risk_parity": set(),
    "maximum_diversification": set(),
    "hrp": set(),
}
"""Method -> its extra keys."""

_PARAMETERS = ("returns_format", "method", "covariance", "bounds", "periods_per_year")


@dataclass(frozen=True)
class _Parameters:
    returns_format: Mapping[str, str]
    method: Mapping[str, object]
    covariance: Mapping[str, object]
    lower: float
    upper: float
    periods_per_year: int


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    method = parameters["method"]
    if not isinstance(method, dict):
        raise ValidationError("method must be a table")
    name = choice(method, "name", set(METHODS))
    require_keys(method, required={"name", *METHODS[name]}, optional=set(), where="method")
    for key in METHODS[name]:
        number(method, key)
    bounds = table(parameters, "bounds", required={"min", "max"}, optional=set())
    lower, upper = number(bounds, "min"), number(bounds, "max")
    if lower > upper or upper <= 0:
        raise ValidationError("bounds need min <= max and max > 0")
    return _Parameters(
        returns_format=returns_format(parameters),
        method=method,
        covariance=covariance_spec(parameters),
        lower=lower,
        upper=upper,
        periods_per_year=whole(parameters, "periods_per_year", minimum=1),
    )


def _optimise(
    p: _Parameters, returns: pd.DataFrame, cov: CovarianceEstimate, assets: list[str]
) -> OptimizationResult:
    name = str(p.method["name"])
    constraints = Constraints(
        long_only=p.lower >= 0,
        bounds=dict.fromkeys(assets, (p.lower, p.upper)),
        groups={},
        turnover=None,
        current=None,
    )
    if name == "equal_weights":
        return equal_weights(cov, constraints)
    if name == "minimum_variance":
        return minimum_variance(cov, constraints)
    if name == "mean_variance":
        risk_aversion = float(p.method["risk_aversion"])  # type: ignore[arg-type]
        return mean_variance(returns.mean(), cov, constraints, risk_aversion=risk_aversion)
    if name == "maximum_sharpe":
        rf = float(p.method["risk_free_per_period"])  # type: ignore[arg-type]
        return maximum_sharpe(returns.mean() - rf, cov)
    if name == "risk_parity":
        return risk_budgeting(cov, pd.Series(1.0 / len(assets), index=assets))
    if name == "maximum_diversification":
        return maximum_diversification(cov)
    return hierarchical_risk_parity(cov)


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    returns = read_returns(context.inputs["returns"].read_bytes(), p.returns_format)
    require_periods_per_year(p.periods_per_year, returns.index)
    assets = [str(c) for c in returns.columns]
    cov = estimate_covariance(returns, p.covariance)
    result = _optimise(p, returns, cov, assets)
    w = result.weights.reindex(assets)
    vol = volatility_contributions(cov, w)
    mean = float(returns.mean().to_numpy() @ w.to_numpy())
    table_out = pd.DataFrame(
        {
            "weight": w,
            "volatility_share": vol.share,
            "mean_return": returns.mean(),
            "volatility": cov.volatilities(),
        }
    )
    table_out.index.name = "asset"
    root = math.sqrt(p.periods_per_year)
    scalars = {
        "method": Tagged(result.method, "in_sample"),
        "volatility_annual": Tagged(vol.total * root, "in_sample"),
        "mean_return_annual": Tagged(mean * p.periods_per_year, "in_sample"),
        "effective_number_of_bets": Tagged(effective_number_of_bets(cov, w), "in_sample"),
        "active_constraints": Tagged(", ".join(result.active) or "none", "in_sample"),
    }
    return ExperimentOutput(tables={"weights": Tagged(table_out, "in_sample")}, scalars=scalars)


KIND = ExperimentKind(
    name="optimisation",
    description="Portfolio weights by a construction method, in sample (not a forecast)",
    inputs=("returns",),
    needs_seed=False,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
