r"""Portfolio constraints, a feasibility check and the constrained solver.

Weights always sum to 1 (cash, if wanted, is an explicit asset). Optional constraints:

- ``long_only``: :math:`w_i \ge 0`;
- bounds per asset, :math:`l_i \le w_i \le u_i`;
- groups, :math:`L_g \le \sum_{i\in g} w_i \le U_g`;
- turnover from current weights, :math:`\sum_i |w_i - w_{0,i}| \le \tau`, made smooth with
  auxiliary variables :math:`u_i \ge |w_i - w_{0,i}|`.

Feasibility is checked with a linear program before solving. The solver is SciPy SLSQP; after
solving, every constraint is checked within ``TOLERANCE`` and a failure raises with the
solver's message.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import optimize

from qrlab.core.errors import ValidationError

__all__ = ["TOLERANCE", "Constraints", "SolverOutcome", "solve"]

TOLERANCE = 1e-8


@dataclass(frozen=True)
class Constraints:
    r"""Explicit constraints; every field is required (use empty mappings and ``None``).

    Parameters
    ----------
    long_only
        Forbid negative weights.
    bounds
        ``asset -> (min, max)``; assets not listed are bounded only by ``long_only``.
    groups
        ``name -> (assets, min, max)`` on the sum of the group's weights.
    turnover
        Maximum :math:`\sum|w-w_0|`, or ``None``.
    current
        Current weights :math:`w_0` (required with ``turnover``), summing to 1.
    """

    long_only: bool
    bounds: Mapping[str, tuple[float, float]]
    groups: Mapping[str, tuple[tuple[str, ...], float, float]]
    turnover: float | None
    current: pd.Series | None

    def __post_init__(self) -> None:
        """Validate the constraint values (feasibility is checked against the assets later)."""
        if not isinstance(self.long_only, bool):
            raise ValidationError("long_only must be True or False")
        for asset, (low, high) in self.bounds.items():
            if not (math.isfinite(low) and math.isfinite(high)) or low > high:
                raise ValidationError(f"bounds of {asset} must be finite with min <= max")
        for name, (members, low, high) in self.groups.items():
            if not members or low > high:
                raise ValidationError(f"group {name} needs assets and min <= max")
        if (self.turnover is None) != (self.current is None):
            raise ValidationError("turnover and current weights go together")
        if self.turnover is not None and not (math.isfinite(self.turnover) and self.turnover >= 0):
            raise ValidationError("turnover must be a finite number >= 0")
        if self.current is not None and abs(float(self.current.sum()) - 1.0) > TOLERANCE:
            raise ValidationError("current weights must sum to 1")

    def describe(self) -> str:
        """Return a one-line description for reports."""
        parts = ["long-only" if self.long_only else "long-short", "fully invested"]
        if self.bounds:
            parts.append(f"{len(self.bounds)} asset bounds")
        if self.groups:
            parts.append(f"{len(self.groups)} groups")
        if self.turnover is not None:
            parts.append(f"turnover <= {self.turnover:.2%}")
        return ", ".join(parts)


@dataclass(frozen=True)
class SolverOutcome:
    """Weights found by the solver, with diagnostics."""

    weights: np.ndarray
    objective: float
    iterations: int
    active: tuple[str, ...]


def solve(
    assets: list[str],
    objective: Callable[[np.ndarray], float],
    gradient: Callable[[np.ndarray], np.ndarray],
    constraints: Constraints,
    *,
    equalities: tuple[tuple[np.ndarray, float], ...] = (),
) -> SolverOutcome:
    """Minimise ``objective(w)`` subject to ``constraints`` and extra ``a'w = b`` equalities."""
    n = len(assets)
    lower, upper = _bounds(assets, constraints)
    groups = _groups(assets, constraints)
    w0 = _current(assets, constraints)
    start = _feasible_point(n, lower, upper, groups, w0, constraints.turnover, equalities)
    extra = n if w0 is not None else 0

    def f(x: np.ndarray) -> float:
        return objective(x[:n])

    def g(x: np.ndarray) -> np.ndarray:
        return np.concatenate([gradient(x[:n]), np.zeros(extra)])

    cons: list[Any] = [
        {
            "type": "eq",
            "fun": lambda x: np.sum(x[:n]) - 1.0,
            "jac": lambda x: _pad(np.ones(n), extra),
        }
    ]
    for a, b in equalities:
        cons.append(
            {
                "type": "eq",
                "fun": lambda x, a=a, b=b: a @ x[:n] - b,
                "jac": lambda x, a=a: _pad(a, extra),
            }
        )
    for mask, low, high in groups:
        cons.append(
            {
                "type": "ineq",
                "fun": lambda x, m=mask, lo=low: m @ x[:n] - lo,
                "jac": lambda x, m=mask: _pad(m, extra),
            }
        )
        cons.append(
            {
                "type": "ineq",
                "fun": lambda x, m=mask, hi=high: hi - m @ x[:n],
                "jac": lambda x, m=mask: _pad(-m, extra),
            }
        )
    if w0 is not None:
        eye = np.eye(n)
        cons.append(
            {
                "type": "ineq",
                "fun": lambda x: x[n:] - (x[:n] - w0),
                "jac": lambda x: np.hstack([-eye, eye]),
            }
        )
        cons.append(
            {
                "type": "ineq",
                "fun": lambda x: x[n:] + (x[:n] - w0),
                "jac": lambda x: np.hstack([eye, eye]),
            }
        )
        tau = float(constraints.turnover or 0.0)
        cons.append(
            {
                "type": "ineq",
                "fun": lambda x: tau - np.sum(x[n:]),
                "jac": lambda x: np.concatenate([np.zeros(n), -np.ones(n)]),
            }
        )
    box = [
        (lo if math.isfinite(lo) else None, hi if math.isfinite(hi) else None)
        for lo, hi in zip(lower, upper, strict=True)
    ] + [(0.0, None)] * extra
    result = optimize.minimize(
        f,
        start,
        jac=g,
        method="SLSQP",
        bounds=box,
        constraints=cons,
        options={"ftol": 1e-15, "maxiter": 2000},
    )
    w = np.asarray(result.x[:n], dtype=np.float64)
    problems = _violations(w, lower, upper, groups, w0, constraints.turnover, equalities)
    if not result.success or problems:
        raise ValidationError(
            f"optimisation failed: {result.message}; {problems or 'no violations'}"
        )
    active = tuple(
        a
        for a, wi, lo, hi in zip(assets, w, lower, upper, strict=True)
        if abs(wi - lo) <= 1e-7 or abs(wi - hi) <= 1e-7
    )
    return SolverOutcome(w, float(objective(w)), int(result.nit), active)


def _pad(row: np.ndarray, extra: int) -> np.ndarray:
    return np.concatenate([row, np.zeros(extra)])


def _bounds(assets: list[str], c: Constraints) -> tuple[np.ndarray, np.ndarray]:
    unknown = sorted(set(c.bounds) - set(assets))
    if unknown:
        raise ValidationError(f"bounds for unknown assets {unknown}")
    floor = 0.0 if c.long_only else -math.inf
    lower = np.array([max(floor, c.bounds.get(a, (floor, math.inf))[0]) for a in assets])
    upper = np.array([c.bounds.get(a, (floor, math.inf))[1] for a in assets])
    if (lower > upper).any():
        raise ValidationError("bounds conflict with long_only")
    return lower, upper


def _groups(assets: list[str], c: Constraints) -> list[tuple[np.ndarray, float, float]]:
    out = []
    for name, (members, low, high) in c.groups.items():
        unknown = sorted(set(members) - set(assets))
        if unknown:
            raise ValidationError(f"group {name} names unknown assets {unknown}")
        out.append((np.array([1.0 if a in members else 0.0 for a in assets]), low, high))
    return out


def _current(assets: list[str], c: Constraints) -> np.ndarray | None:
    if c.current is None:
        return None
    if set(c.current.index) != set(assets):
        raise ValidationError("current weights must cover exactly the assets")
    return c.current.reindex(assets).to_numpy(dtype=np.float64)


def _feasible_point(
    n: int,
    lower: np.ndarray,
    upper: np.ndarray,
    groups: list[tuple[np.ndarray, float, float]],
    w0: np.ndarray | None,
    turnover: float | None,
    equalities: tuple[tuple[np.ndarray, float], ...],
) -> np.ndarray:
    """Solve a linear feasibility problem; raise if the constraints cannot all hold."""
    extra = n if w0 is not None else 0
    a_eq = [_pad(np.ones(n), extra)] + [_pad(a, extra) for a, _ in equalities]
    b_eq = [1.0] + [b for _, b in equalities]
    a_ub: list[np.ndarray] = []
    b_ub: list[float] = []
    for mask, low, high in groups:
        a_ub += [_pad(-mask, extra), _pad(mask, extra)]
        b_ub += [-low, high]
    if w0 is not None:
        eye = np.eye(n)
        a_ub += list(np.hstack([eye, -eye])) + list(np.hstack([-eye, -eye]))
        b_ub += list(w0) + list(-w0)
        a_ub.append(np.concatenate([np.zeros(n), np.ones(n)]))
        b_ub.append(float(turnover or 0.0))
    box = [
        (lo if math.isfinite(lo) else None, hi if math.isfinite(hi) else None)
        for lo, hi in zip(lower, upper, strict=True)
    ] + [(0.0, None)] * extra
    lp = optimize.linprog(
        np.zeros(n + extra),
        A_ub=np.array(a_ub) if a_ub else None,
        b_ub=np.array(b_ub) if b_ub else None,
        A_eq=np.array(a_eq),
        b_eq=np.array(b_eq),
        bounds=box,
        method="highs",
    )
    if lp.status != 0:
        raise ValidationError(f"constraints are infeasible: {lp.message}")
    return np.asarray(lp.x, dtype=np.float64)


def _violations(
    w: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    groups: list[tuple[np.ndarray, float, float]],
    w0: np.ndarray | None,
    turnover: float | None,
    equalities: tuple[tuple[np.ndarray, float], ...],
) -> list[str]:
    problems = []
    if abs(w.sum() - 1.0) > TOLERANCE:
        problems.append(f"weights sum to {w.sum()}")
    if (w < lower - TOLERANCE).any() or (w > upper + TOLERANCE).any():
        problems.append("bounds")
    for mask, low, high in groups:
        total = float(mask @ w)
        if total < low - TOLERANCE or total > high + TOLERANCE:
            problems.append("group bounds")
    if w0 is not None and float(np.abs(w - w0).sum()) > float(turnover or 0.0) + TOLERANCE:
        problems.append("turnover")
    for a, b in equalities:
        if abs(float(a @ w) - b) > TOLERANCE:
            problems.append("target")
    return problems
