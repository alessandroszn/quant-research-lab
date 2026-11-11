r"""Distributions, goal and depletion probabilities, sequence risk and sensitivity.

- **Fan chart:** chosen percentiles of wealth per period, nominal and real.
- **Monte Carlo error:** probabilities carry :math:`\sqrt{p(1-p)/N}` and means :math:`s/\sqrt N`.
- **Sequence-of-returns risk:** paths are ranked by the compounded return of the target-weight
  portfolio over their first ``early_periods``; the median real terminal wealth of the worst and
  best deciles shows how much the order of returns matters when there are flows.
- **Sensitivity:** the plan is re-run under one-at-a-time changes with common random numbers
  (the caller's ``simulate`` uses one fixed seed), so differences come from the assumptions.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.simulation.engines import LogMoments, SimulatedReturns
from qrlab.simulation.plan import Plan, Projection, project

__all__ = [
    "ProjectionResult",
    "ProjectionSummary",
    "SensitivityRow",
    "sensitivity",
    "shifted_moments",
    "summarize",
]

_MONTHS_PER_PERIOD = {1: 12, 2: 6, 4: 3, 12: 1}


@dataclass(frozen=True)
class ProjectionSummary:
    """What a projection says, with its Monte Carlo error.

    Attributes
    ----------
    dates
        Date of each column of the fan chart (start, then the end of each period).
    percentiles
        Percentiles shown, e.g. ``(5, 25, 50, 75, 95)``.
    fan_nominal, fan_real
        Wealth at each percentile (rows) and date (columns).
    terminal_mean_real, terminal_mean_real_se
        Mean real terminal wealth and its standard error.
    terminal_real, terminal_nominal, terminal_after_tax
        Terminal percentiles: real, nominal, and nominal after the liquidation tax.
    goal_real, p_goal, p_goal_se
        Goal in today's money and the probability of reaching it (with standard error).
    p_depleted, p_depleted_se
        Probability that withdrawals exhaust the wealth.
    median_depletion_period
        Median depletion period among depleted paths, or ``None``.
    early_periods, sequence_worst, sequence_best
        Median real terminal wealth of the worst and best deciles of early returns.
    n_paths, engine, plan
        Simulation size, engine and the plan projected.
    """

    dates: tuple[date, ...]
    percentiles: tuple[float, ...]
    fan_nominal: np.ndarray
    fan_real: np.ndarray
    terminal_mean_real: float
    terminal_mean_real_se: float
    terminal_real: tuple[float, ...]
    terminal_nominal: tuple[float, ...]
    terminal_after_tax: tuple[float, ...]
    goal_real: float
    p_goal: float
    p_goal_se: float
    p_depleted: float
    p_depleted_se: float
    median_depletion_period: float | None
    early_periods: int
    sequence_worst: float
    sequence_best: float
    n_paths: int
    engine: str
    plan: Plan


@dataclass(frozen=True)
class SensitivityRow:
    """Goal probability and median real terminal wealth under one change of assumption.

    ``key`` is a stable identifier (e.g. ``"mean_down"``); ``label`` describes the change.
    """

    key: str
    label: str
    p_goal: float
    p_goal_se: float
    median_terminal_real: float


@dataclass(frozen=True)
class ProjectionResult:
    """A projection summary with its sensitivity table, ready for the report."""

    summary: ProjectionSummary
    sensitivity: tuple[SensitivityRow, ...]


def summarize(
    projection: Projection,
    returns: SimulatedReturns,
    *,
    start: date,
    goal_real: float,
    percentiles: Sequence[float],
    early_periods: int,
) -> ProjectionSummary:
    """Summarise a projection of ``returns`` starting on ``start``."""
    plan = projection.plan
    paths, columns = projection.nominal.shape
    if returns.n_paths != paths or returns.n_periods != columns - 1:
        raise ValidationError("returns do not match the projection")
    if plan.periods_per_year not in _MONTHS_PER_PERIOD:
        raise ValidationError("dates need periods_per_year of 1, 2, 4 or 12")
    levels = tuple(float(p) for p in percentiles)
    if not levels or any(not 0.0 <= p <= 100.0 for p in levels) or list(levels) != sorted(levels):
        raise ValidationError("percentiles must be increasing values in [0, 100]")
    if not math.isfinite(goal_real) or goal_real < 0:
        raise ValidationError("goal_real must be a finite number >= 0")
    if type(early_periods) is not int or not 1 <= early_periods <= returns.n_periods:
        raise ValidationError("early_periods must be an int between 1 and the horizon")
    if paths < 10:
        raise ValidationError("a summary needs at least 10 paths (deciles)")
    step = _MONTHS_PER_PERIOD[plan.periods_per_year]
    dates = tuple(
        (pd.Timestamp(start) + pd.DateOffset(months=step * t)).date() for t in range(columns)
    )
    terminal_real = projection.real[:, -1]
    reached = terminal_real >= goal_real
    depleted = projection.depleted_period >= 0
    weights = plan.weights.to_numpy(dtype=np.float64)
    early = np.prod(1.0 + returns.returns[:, :early_periods, :] @ weights, axis=1)
    order = np.argsort(early, kind="stable")
    decile = max(paths // 10, 1)
    return ProjectionSummary(
        dates=dates,
        percentiles=levels,
        fan_nominal=np.percentile(projection.nominal, levels, axis=0),
        fan_real=np.percentile(projection.real, levels, axis=0),
        terminal_mean_real=float(terminal_real.mean()),
        terminal_mean_real_se=float(terminal_real.std(ddof=1) / math.sqrt(paths)),
        terminal_real=_pct(terminal_real, levels),
        terminal_nominal=_pct(projection.nominal[:, -1], levels),
        terminal_after_tax=_pct(projection.liquidation_value, levels),
        goal_real=float(goal_real),
        p_goal=float(reached.mean()),
        p_goal_se=_se(float(reached.mean()), paths),
        p_depleted=float(depleted.mean()),
        p_depleted_se=_se(float(depleted.mean()), paths),
        median_depletion_period=(
            float(np.median(projection.depleted_period[depleted])) if depleted.any() else None
        ),
        early_periods=early_periods,
        sequence_worst=float(np.median(terminal_real[order[:decile]])),
        sequence_best=float(np.median(terminal_real[order[-decile:]])),
        n_paths=paths,
        engine=projection.engine,
        plan=plan,
    )


def shifted_moments(
    moments: LogMoments, *, annual_mean_shift: float, vol_scale: float, periods_per_year: int
) -> LogMoments:
    """Return moments with the mean shifted by an annual amount and volatilities scaled."""
    if not vol_scale > 0:
        raise ValidationError("vol_scale must be positive")
    return LogMoments(
        mean=moments.mean + annual_mean_shift / periods_per_year,
        covariance=moments.covariance * vol_scale**2,
        n_obs=moments.n_obs,
    )


def sensitivity(
    plan: Plan,
    simulate: Callable[[float, float], SimulatedReturns],
    *,
    goal_real: float,
) -> tuple[SensitivityRow, ...]:
    """Re-run ``plan`` under one-at-a-time changes.

    ``simulate(annual_mean_shift, vol_scale)`` must use the same seed on every call (common
    random numbers). Changes: mean return +-1 point a year, volatility x0.8 and x1.2, inflation
    +-1 point, costs +-0.5 point (a cost below zero is skipped).
    """
    cost, inflation = plan.annual_cost, plan.inflation
    variants: list[tuple[str, str, float, float, Plan]] = [
        ("base", "base", 0.0, 1.0, plan),
        ("mean_down", "mean return -1 pp", -0.01, 1.0, plan),
        ("mean_up", "mean return +1 pp", 0.01, 1.0, plan),
        ("vol_down", "volatility x0.8", 0.0, 0.8, plan),
        ("vol_up", "volatility x1.2", 0.0, 1.2, plan),
        ("inflation_down", "inflation -1 pp", 0.0, 1.0, replace(plan, inflation=inflation - 0.01)),
        ("inflation_up", "inflation +1 pp", 0.0, 1.0, replace(plan, inflation=inflation + 0.01)),
        ("costs_up", "costs +0.5 pp", 0.0, 1.0, replace(plan, annual_cost=cost + 0.005)),
    ]
    if cost >= 0.005:
        variants.append(
            ("costs_down", "costs -0.5 pp", 0.0, 1.0, replace(plan, annual_cost=cost - 0.005))
        )
    rows = []
    for key, label, shift, scale, variant in variants:
        result = project(variant, simulate(shift, scale))
        terminal = result.real[:, -1]
        p = float((terminal >= goal_real).mean())
        rows.append(
            SensitivityRow(key, label, p, _se(p, len(terminal)), float(np.median(terminal)))
        )
    return tuple(rows)


def _pct(values: np.ndarray, levels: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(float(v) for v in np.percentile(values, levels))


def _se(p: float, n: int) -> float:
    return math.sqrt(p * (1.0 - p) / n)
