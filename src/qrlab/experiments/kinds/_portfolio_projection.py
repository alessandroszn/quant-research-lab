"""The projection of the ``portfolio_report`` kind: today's portfolio plus a plan (design 8.4).

The starting point is the report's own: value, weights, date and base currency. The return
assumptions are stated in the config, one table per held position and one for cash, and never
estimated from the history. Correlations are declared for every pair of assets with a positive
volatility; none defaults. The sensitivity table is always computed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.experiments.config import require_keys
from qrlab.experiments.kinds._params import choice, loss_rules, number, table, whole
from qrlab.experiments.kinds.projection import PlanRun, parse_engine, parse_flows, run_plan
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import Instrument, InstrumentType
from qrlab.simulation.engines import LogMoments
from qrlab.simulation.losses import LossRules
from qrlab.simulation.plan import Flow, Plan, TaxModel

__all__ = ["CASH", "ProjectionSpec", "parse_projection", "project_portfolio"]

CASH = "cash"
_KEYS = {
    "seed", "engine", "paths", "periods", "periods_per_year", "goal_real", "percentiles",
    "early_periods", "rebalance_every", "flow_timing", "annual_cost", "inflation",
    "capital_gains_tax", "wealth_tax", "flows", "assets",
}  # fmt: skip


@dataclass(frozen=True)
class ProjectionSpec:
    """``[parameters.projection]`` as parsed; checked against the portfolio when it runs."""

    seed: int
    engine: str
    dof: float | None
    paths: int
    periods: int
    periods_per_year: int
    goal: float
    percentiles: tuple[float, ...]
    early: int
    rebalance_every: int | None
    flow_timing: str
    annual_cost: float | None  # None: the TERs of the instruments file, weighted
    inflation: float
    capital_gains_tax: float
    wealth_tax: float
    income_tax: tuple[float, float] | None  # (income_tax_rate, taxable_yield), phase 9.2
    loss_carry_years: int | None  # [parameters.projection.losses], phase 11.5
    flows: tuple[Flow, ...]
    assets: Mapping[str, tuple[float, float]]  # ISIN code or "cash" -> (mean, volatility)
    correlations: Mapping[frozenset[str], float]


def parse_projection(parameters: Mapping[str, object]) -> ProjectionSpec | None:
    """Read ``[parameters.projection]``, or ``None`` when it is absent."""
    if "projection" not in parameters:
        return None
    spec = parameters["projection"]
    if not isinstance(spec, dict):
        raise ValidationError("[parameters.projection] must be a table")
    require_keys(
        spec,
        required=_KEYS,
        optional={"cash", "correlations", "income_tax_rate", "taxable_yield", "losses"},
        where="[parameters.projection]",
    )
    engine, dof = parse_engine(spec)
    seed = spec["seed"]
    if type(seed) is not int or seed < 0:
        raise ValidationError("[parameters.projection] seed must be an int >= 0")
    cost = spec["annual_cost"]
    if cost != "ter" and type(cost) not in (int, float):
        raise ValidationError("[parameters.projection] annual_cost must be a number or 'ter'")
    levels = spec["percentiles"]
    if not isinstance(levels, list) or not levels:
        raise ValidationError("[parameters.projection] percentiles must be a list of numbers")
    assets_table = spec["assets"]
    if not isinstance(assets_table, dict) or not assets_table:
        raise ValidationError("[parameters.projection.assets] needs one table per held position")
    assets = {str(Isin(code).code): _moments(assets_table, code) for code in assets_table}
    if "cash" in spec:
        assets[CASH] = _moments(spec, "cash")
    rebalance = whole(spec, "rebalance_every", minimum=0)
    income_keys = {"income_tax_rate", "taxable_yield"} & set(spec)
    if len(income_keys) == 1:
        raise ValidationError(
            "[parameters.projection] income_tax_rate and taxable_yield go together (phase 9.2)"
        )
    return ProjectionSpec(
        seed=seed,
        engine=engine,
        dof=dof,
        paths=whole(spec, "paths", minimum=10),
        periods=whole(spec, "periods", minimum=1),
        periods_per_year=whole(spec, "periods_per_year", minimum=1),
        goal=number(spec, "goal_real"),
        percentiles=tuple(float(x) for x in levels),
        early=whole(spec, "early_periods", minimum=1),
        rebalance_every=rebalance or None,
        flow_timing=choice(spec, "flow_timing", {"start", "end"}),
        annual_cost=None if cost == "ter" else float(cost),
        inflation=number(spec, "inflation"),
        capital_gains_tax=number(spec, "capital_gains_tax"),
        wealth_tax=number(spec, "wealth_tax"),
        loss_carry_years=None
        if (losses := loss_rules(spec, where="[parameters.projection]", fund_assets=False)) is None
        else losses[0],
        income_tax=(number(spec, "income_tax_rate"), number(spec, "taxable_yield"))
        if income_keys
        else None,
        flows=parse_flows(spec["flows"]),
        assets=assets,
        correlations=_correlations(spec.get("correlations", {})),
    )


def _moments(parent: Mapping[str, object], key: str) -> tuple[float, float]:
    values = table(parent, key, required={"mean", "volatility"}, optional=set())
    volatility = number(values, "volatility")
    if volatility < 0:
        raise ValidationError(f"{key}: volatility must be >= 0")
    return number(values, "mean"), volatility


def _correlations(value: object) -> dict[frozenset[str], float]:
    if not isinstance(value, dict):
        raise ValidationError("[parameters.projection.correlations] must be a table")
    out: dict[frozenset[str], float] = {}
    for key, rho in value.items():
        pair = frozenset(str(key).split())
        if len(pair) != 2 or len(str(key).split()) != 2:
            raise ValidationError(f"correlation key {key!r} must name two different assets")
        if type(rho) not in (int, float) or not -1.0 <= float(rho) <= 1.0:
            raise ValidationError(f"correlation {key!r} must be a number in [-1, 1]")
        if pair in out:
            raise ValidationError(f"correlation {key!r} is given twice")
        out[pair] = float(rho)
    return out


def project_portfolio(
    spec: ProjectionSpec,
    *,
    start: date,
    value: float,
    base: Currency,
    position_weights: Mapping[Isin, float],
    cash_weight: float,
    instruments: Mapping[Isin, Instrument],
) -> tuple[PlanRun, float]:
    """Project today's portfolio under the stated assumptions; return the run and the cost."""
    held = sorted(i.code for i, w in position_weights.items() if w != 0.0)
    given = sorted(k for k in spec.assets if k != CASH)
    if held != given:
        raise ValidationError(
            "[parameters.projection.assets] must be exactly the held positions: missing "
            f"{sorted(set(held) - set(given))}, not held {sorted(set(given) - set(held))}"
        )
    names = list(held)
    weights = {code: position_weights[Isin(code)] for code in held}
    if cash_weight != 0.0:
        if CASH not in spec.assets:
            raise ValidationError(
                "the portfolio holds cash: give its return in [parameters.projection.cash]"
            )
        names.append(CASH)
        weights[CASH] = cash_weight
    mean = pd.Series([spec.assets[n][0] for n in names], index=names)
    vol = np.array([spec.assets[n][1] for n in names])
    corr = np.eye(len(names))
    risky = [n for n in names if spec.assets[n][1] > 0]
    needed = {frozenset((a, b)) for i, a in enumerate(risky) for b in risky[i + 1 :]}
    if set(spec.correlations) != needed:
        missing = sorted(" ".join(sorted(p)) for p in needed - set(spec.correlations))
        extra = sorted(" ".join(sorted(p)) for p in set(spec.correlations) - needed)
        raise ValidationError(
            "[parameters.projection.correlations] must give every pair of assets with a "
            f"positive volatility: missing {missing}, not needed {extra}"
        )
    for pair, rho in spec.correlations.items():
        a, b = sorted(pair)
        i, j = names.index(a), names.index(b)
        corr[i, j] = corr[j, i] = rho
    covariance = pd.DataFrame(corr * np.outer(vol, vol), index=names, columns=names)
    cost = spec.annual_cost
    if cost is None:
        cost = _weighted_ter(weights, instruments)
    plan = Plan(
        initial_wealth=value,
        currency=base,
        weights=pd.Series(weights).reindex(names),
        periods_per_year=spec.periods_per_year,
        flows=spec.flows,
        flow_timing=spec.flow_timing,
        rebalance_every=spec.rebalance_every,
        annual_cost=cost,
        inflation=spec.inflation,
        taxes=TaxModel(
            spec.capital_gains_tax,
            spec.wealth_tax,
            losses=None
            if spec.loss_carry_years is None
            else LossRules(spec.loss_carry_years, _fund_assets(names, instruments)),
            income_tax_rate=0.0 if spec.income_tax is None else spec.income_tax[0],
            taxable_yield=0.0 if spec.income_tax is None else spec.income_tax[1],
        ),
    )
    run = run_plan(
        moments=LogMoments(mean, covariance, 0),
        engine=spec.engine,
        dof=spec.dof,
        plan=plan,
        paths=spec.paths,
        periods=spec.periods,
        start=start,
        goal=spec.goal,
        percentiles=spec.percentiles,
        early=spec.early,
        seed=spec.seed,
        with_sensitivity=True,
    )
    return run, cost


def _fund_assets(names: list[str], instruments: Mapping[Isin, Instrument]) -> frozenset[str]:
    """Return the held ETFs and funds: their gains are capital income (the rule of 8.6)."""
    funds = {InstrumentType.ETF, InstrumentType.FUND}
    return frozenset(
        code
        for code in names
        if code != CASH
        and (instrument := instruments.get(Isin(code))) is not None
        and instrument.instrument_type in funds
    )


def _weighted_ter(weights: Mapping[str, float], instruments: Mapping[Isin, Instrument]) -> float:
    """Return the TER of each position weighted by today's weights (cash costs 0)."""
    total = 0.0
    for code, weight in weights.items():
        if code == CASH:
            continue
        instrument = instruments.get(Isin(code))
        if instrument is None or instrument.ter is None:
            raise ValidationError(
                f"annual_cost = 'ter' needs the TER of {code} in the instruments file"
            )
        total += weight * float(instrument.ter)
    return total
