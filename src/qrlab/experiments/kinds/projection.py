"""Experiment kind ``projection``: a savings or withdrawal plan projected by Monte Carlo.

No input files: the return assumptions are stated in the config, as per-period log-return means
and volatilities per asset plus a correlation matrix (``[parameters.assets]``,
``[parameters.correlation]``). The plan follows phase 3.3. Results are descriptive: scenarios
from assumptions, not forecasts.

Optional in ``[parameters.plan]`` (phase 11.5): ``income_tax_rate`` and ``taxable_yield`` (both
or neither, a yearly tax of their product on value, as in the report since 9.2), and
``losses`` (``carry_years`` and ``fund_assets``, :class:`qrlab.simulation.LossRules`).
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
from qrlab.experiments.kinds._params import (
    boolean,
    choice,
    day,
    loss_rules,
    number,
    table,
    text,
    whole,
)
from qrlab.experiments.registry import ExperimentKind, ExperimentOutput, RunContext, Tagged
from qrlab.reporting.figures import AxisFormat, line_figure
from qrlab.reporting.formatting import Language, style_for
from qrlab.simulation.engines import (
    MAX_CELLS,
    LogMoments,
    SimulatedReturns,
    normal_returns,
    student_t_returns,
)
from qrlab.simulation.losses import LossRules
from qrlab.simulation.outcomes import (
    ProjectionResult,
    SensitivityRow,
    sensitivity,
    shifted_moments,
    summarize,
)
from qrlab.simulation.plan import Flow, Plan, TaxModel, project

SCENARIOS = (
    "Scenarios from the stated assumptions, not a forecast. Outcomes are a distribution; no "
    "single path is expected."
)
NO_SENSITIVITY = "No sensitivity analysis was run for this projection."
ADVICE = "Research analytics, not investment advice."

__all__ = ["KIND", "PlanRun", "parse_engine", "parse_flows", "run_plan"]

_PARAMETERS = (
    "assets",
    "correlation",
    "engine",
    "plan",
    "flows",
    "paths",
    "periods",
    "start",
    "goal_real",
    "percentiles",
    "early_periods",
    "sensitivity",
)


@dataclass(frozen=True)
class _Parameters:
    moments: LogMoments
    engine: str
    dof: float | None
    plan: Plan
    paths: int
    periods: int
    start: date
    goal: float
    percentiles: tuple[float, ...]
    early: int
    sensitivity: bool


def _parse(parameters: Mapping[str, object]) -> _Parameters:
    require_keys(parameters, required=set(_PARAMETERS), optional=set(), where="[parameters]")
    assets_table = parameters["assets"]
    if not isinstance(assets_table, dict) or not assets_table:
        raise ValidationError("assets must be a table of {mean, volatility, weight}")
    names = list(assets_table)
    rows = [
        table(assets_table, a, required={"mean", "volatility", "weight"}, optional=set())
        for a in names
    ]
    corr = (
        np.array(parameters["correlation"], dtype=np.float64)
        if isinstance(parameters["correlation"], list)
        else None
    )
    if corr is None or corr.shape != (len(names), len(names)):
        raise ValidationError("correlation must be a square list of lists, one row per asset")
    vol = np.array([number(r, "volatility") for r in rows])
    covariance = pd.DataFrame(corr * np.outer(vol, vol), index=names, columns=names)
    moments = LogMoments(pd.Series([number(r, "mean") for r in rows], index=names), covariance, 0)
    engine, dof = parse_engine(parameters)
    plan_table = table(
        parameters,
        "plan",
        required={
            "initial_wealth",
            "currency",
            "periods_per_year",
            "flow_timing",
            "rebalance_every",
            "annual_cost",
            "inflation",
            "capital_gains_tax",
            "wealth_tax",
        },
        optional={"income_tax_rate", "taxable_yield", "losses"},
    )
    income = {"income_tax_rate", "taxable_yield"} & set(plan_table)
    if len(income) == 1:
        raise ValidationError(
            "[parameters.plan] income_tax_rate and taxable_yield go together (phase 9.2)"
        )
    losses = loss_rules(plan_table, where="[parameters.plan]", fund_assets=True)
    rebalance = whole(plan_table, "rebalance_every", minimum=0)
    plan = Plan(
        initial_wealth=number(plan_table, "initial_wealth"),
        currency=Currency(text(plan_table, "currency")),
        weights=pd.Series([number(r, "weight") for r in rows], index=names),
        periods_per_year=whole(plan_table, "periods_per_year", minimum=1),
        flows=parse_flows(parameters["flows"]),
        flow_timing=choice(plan_table, "flow_timing", {"start", "end"}),
        rebalance_every=rebalance or None,
        annual_cost=number(plan_table, "annual_cost"),
        inflation=number(plan_table, "inflation"),
        taxes=TaxModel(
            number(plan_table, "capital_gains_tax"),
            number(plan_table, "wealth_tax"),
            losses=None if losses is None else LossRules(*losses),
            income_tax_rate=number(plan_table, "income_tax_rate") if income else 0.0,
            taxable_yield=number(plan_table, "taxable_yield") if income else 0.0,
        ),
    )
    levels = parameters["percentiles"]
    if not isinstance(levels, list):
        raise ValidationError("percentiles must be a list of numbers")
    return _Parameters(
        moments=moments,
        engine=engine,
        dof=dof,
        plan=plan,
        paths=whole(parameters, "paths", minimum=10),
        periods=whole(parameters, "periods", minimum=1),
        start=day(parameters, "start"),
        goal=number(parameters, "goal_real"),
        percentiles=tuple(float(x) for x in levels),
        early=whole(parameters, "early_periods", minimum=1),
        sensitivity=boolean(parameters, "sensitivity"),
    )


def parse_engine(parameters: Mapping[str, object]) -> tuple[str, float | None]:
    """Read ``engine = { name = "normal" }`` or ``{ name = "student_t", dof = ... }``."""
    engine_table = parameters["engine"]
    if not isinstance(engine_table, dict):
        raise ValidationError("engine must be a table")
    engine = choice(engine_table, "name", {"normal", "student_t"})
    require_keys(
        engine_table,
        required={"name"} | ({"dof"} if engine == "student_t" else set()),
        optional=set(),
        where="engine",
    )
    return engine, number(engine_table, "dof") if engine == "student_t" else None


def parse_flows(value: object) -> tuple[Flow, ...]:
    """Read an array of ``{kind, amount, first, last, indexed}`` flow tables (may be empty)."""
    if not isinstance(value, list):
        raise ValidationError("flows must be an array of tables (empty for none)")
    flows = []
    for item in value:
        if not isinstance(item, dict):
            raise ValidationError("each flow must be a table")
        require_keys(
            item,
            required={"kind", "amount", "first", "last", "indexed"},
            optional=set(),
            where="flow",
        )
        flows.append(
            Flow(
                choice(item, "kind", {"contribution", "withdrawal"}),
                number(item, "amount"),
                whole(item, "first", minimum=0),
                whole(item, "last", minimum=0),
                boolean(item, "indexed"),
            )
        )
    return tuple(flows)


@dataclass(frozen=True)
class PlanRun:
    """A projected plan: the report's result, the output tables and the fan chart."""

    result: ProjectionResult
    tables: dict[str, Tagged]
    figure: bytes


def run_plan(
    *,
    moments: LogMoments,
    engine: str,
    dof: float | None,
    plan: Plan,
    paths: int,
    periods: int,
    start: date,
    goal: float,
    percentiles: tuple[float, ...],
    early: int,
    seed: int,
    with_sensitivity: bool,
) -> PlanRun:
    """Simulate, project and summarise a plan; the sensitivity reuses the same seed."""

    def simulate(shift: float, scale: float) -> SimulatedReturns:
        shifted = shifted_moments(
            moments,
            annual_mean_shift=shift,
            vol_scale=scale,
            periods_per_year=plan.periods_per_year,
        )
        rng = np.random.default_rng(seed)
        if engine == "student_t":
            return student_t_returns(
                shifted,
                dof=float(dof or 0),
                n_paths=paths,
                n_periods=periods,
                rng=rng,
                max_cells=MAX_CELLS,
            )
        return normal_returns(
            shifted, n_paths=paths, n_periods=periods, rng=rng, max_cells=MAX_CELLS
        )

    returns = simulate(0.0, 1.0)
    summary = summarize(
        project(plan, returns),
        returns,
        start=start,
        goal_real=goal,
        percentiles=percentiles,
        early_periods=early,
    )
    labels = [f"P{x:g}" for x in summary.percentiles]
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in summary.dates], name="date")
    fan = pd.DataFrame(summary.fan_real.T, index=index, columns=labels)
    terminal = pd.DataFrame(
        {
            "real": summary.terminal_real,
            "nominal": summary.terminal_nominal,
            "after_tax": summary.terminal_after_tax,
        },
        index=labels,
    )
    tables = {"fan_real": Tagged(fan, "descriptive"), "terminal": Tagged(terminal, "descriptive")}
    rows: tuple[SensitivityRow, ...] = ()
    if with_sensitivity:
        rows = sensitivity(plan, simulate, goal_real=goal)
        tables["sensitivity"] = Tagged(
            pd.DataFrame(
                [(r.key, r.label, r.p_goal, r.p_goal_se, r.median_terminal_real) for r in rows],
                columns=["key", "change", "p_goal", "p_goal_se", "median_real"],
            ),
            "descriptive",
        )
    figure = line_figure(
        [(c, fan[c]) for c in fan.columns],
        title="Projected real wealth",
        y_label=plan.currency.code,
        axis=AxisFormat.NUMBER,
        style=style_for(Language.EN),
        note="Scenarios from stated assumptions, not a forecast.",
    )
    return PlanRun(ProjectionResult(summary, rows), tables, figure)


def _run(context: RunContext) -> ExperimentOutput:
    p: _Parameters = context.parameters  # type: ignore[assignment]
    run = run_plan(
        moments=p.moments,
        engine=p.engine,
        dof=p.dof,
        plan=p.plan,
        paths=p.paths,
        periods=p.periods,
        start=p.start,
        goal=p.goal,
        percentiles=p.percentiles,
        early=p.early,
        seed=int(context.seed),  # type: ignore[arg-type]
        with_sensitivity=p.sensitivity,
    )
    summary = run.result.summary
    caveats = [SCENARIOS] if p.sensitivity else [SCENARIOS, NO_SENSITIVITY]
    notice = " ".join([*caveats, ADVICE])
    return ExperimentOutput(
        tables=run.tables,
        scalars={
            "p_goal": Tagged(summary.p_goal, "descriptive"),
            "p_goal_se": Tagged(summary.p_goal_se, "descriptive"),
            "p_depleted": Tagged(summary.p_depleted, "descriptive"),
            "terminal_mean_real": Tagged(summary.terminal_mean_real, "descriptive"),
        },
        figures={"fan_real": run.figure},
        notice=notice,
    )


KIND = ExperimentKind(
    name="projection",
    description="Monte Carlo projection of a savings or withdrawal plan (descriptive)",
    inputs=(),
    needs_seed=True,
    parameters=_PARAMETERS,
    parse=_parse,
    run=_run,
)
