r"""Brinson-Fachler attribution by segment, one period and linked over several (Carino 1999).

With benchmark total :math:`R_b=\sum_s w_{b,s}r_{b,s}` in each period:

- allocation :math:`A_s=(w_{p,s}-w_{b,s})(r_{b,s}-R_b)`;
- selection :math:`S_s=w_{b,s}(r_{p,s}-r_{b,s})` (``interaction="separate"``) or
  :math:`w_{p,s}(r_{p,s}-r_{b,s})` (``"in_selection"``, interaction then 0);
- interaction :math:`I_s=(w_{p,s}-w_{b,s})(r_{p,s}-r_{b,s})`.

They sum to :math:`R_p-R_b` in every period (checked to 1e-12). Over several periods,
``linking="carino"`` scales each period by :math:`k_t/K` with
:math:`k_t=[\ln(1+R_{p,t})-\ln(1+R_{b,t})]/(R_{p,t}-R_{b,t})` (limit :math:`1/(1+R_{p,t})`) and
:math:`K` the same on total returns, so the linked effects sum exactly to
:math:`\prod(1+R_{p,t})-\prod(1+R_{b,t})`. ``linking="none"`` sums the effects and reports the
residual against that compounded active return.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_frame

__all__ = ["EFFECTS", "Attribution", "brinson_fachler"]

EFFECTS = ("allocation", "selection", "interaction")
IDENTITY_TOLERANCE = 1e-12


@dataclass(frozen=True)
class Attribution:
    r"""Brinson-Fachler effects with the active return they explain.

    Attributes
    ----------
    by_period
        Effects per period, columns are a MultiIndex (effect, segment); unscaled.
    totals
        Total effect per segment (rows) and effect (columns), linked as ``linking`` says.
    portfolio_return, benchmark_return
        Compounded total returns over all periods.
    active_return
        :math:`\prod(1+R_{p,t}) - \prod(1+R_{b,t})`.
    residual
        ``active_return`` minus the sum of ``totals`` (0 with Carino linking).
    linking, interaction
        The conventions used.
    """

    by_period: pd.DataFrame
    totals: pd.DataFrame
    portfolio_return: float
    benchmark_return: float
    active_return: float
    residual: float
    linking: str
    interaction: str

    def effect_totals(self) -> pd.Series:
        """Return the total of each effect across segments."""
        return self.totals.sum(axis=0)


def brinson_fachler(
    portfolio_weights: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    benchmark_weights: pd.DataFrame,
    benchmark_returns: pd.DataFrame,
    *,
    interaction: str,
    linking: str,
) -> Attribution:
    """Attribute the active return by segment (periods x segments inputs)."""
    if interaction not in ("separate", "in_selection"):
        raise ValidationError('interaction must be "separate" or "in_selection"')
    if linking not in ("carino", "none"):
        raise ValidationError('linking must be "carino" or "none"')
    wp, rp, wb, rb = (
        validate_frame(f, nan_policy=NanPolicy.RAISE, name=n)
        for f, n in (
            (portfolio_weights, "portfolio_weights"),
            (portfolio_returns, "portfolio_returns"),
            (benchmark_weights, "benchmark_weights"),
            (benchmark_returns, "benchmark_returns"),
        )
    )
    require_same_index(wp, rp, wb, rb)
    segments = list(wp.columns)
    for frame, name in (
        (rp, "portfolio_returns"),
        (wb, "benchmark_weights"),
        (rb, "benchmark_returns"),
    ):
        if list(frame.columns) != segments:
            raise ValidationError(f"{name} must have the segments {segments} in the same order")
    for frame, name in ((wp, "portfolio"), (wb, "benchmark")):
        sums = frame.sum(axis=1).to_numpy()
        if np.any(np.abs(sums - 1.0) > 1e-9):
            raise ValidationError(f"{name} weights must sum to 1 in every period")
    if len(wp) == 0:
        raise ValidationError("attribution needs at least one period")
    total_p = (wp * rp).sum(axis=1)
    total_b = (wb * rb).sum(axis=1)
    allocation = (wp - wb).mul(rb.sub(total_b, axis=0))
    if interaction == "separate":
        selection = wb * (rp - rb)
        inter = (wp - wb) * (rp - rb)
    else:
        selection = wp * (rp - rb)
        inter = selection * 0.0
    period_effects = allocation + selection + inter
    gap = (period_effects.sum(axis=1) - (total_p - total_b)).abs().max()
    if gap > IDENTITY_TOLERANCE:  # pragma: no cover - an algebraic identity
        raise ValidationError(f"effects do not add up to the active return (gap {gap})")
    by_period = pd.concat(
        {"allocation": allocation, "selection": selection, "interaction": inter}, axis=1
    )
    compounded_p = float(np.prod(1.0 + total_p.to_numpy())) - 1.0
    compounded_b = float(np.prod(1.0 + total_b.to_numpy())) - 1.0
    if min(compounded_p, compounded_b, float(total_p.min()), float(total_b.min())) <= -1.0:
        raise ValidationError("returns of -100 % or below cannot be linked")
    active = compounded_p - compounded_b
    if linking == "carino":
        scale = _carino(total_p.to_numpy(), total_b.to_numpy(), compounded_p, compounded_b)
    else:
        scale = np.ones(len(wp))
    totals = pd.DataFrame(
        {
            name: (frame.mul(scale, axis=0)).sum(axis=0)
            for name, frame in (
                ("allocation", allocation),
                ("selection", selection),
                ("interaction", inter),
            )
        }
    )
    residual = active - float(totals.to_numpy().sum())
    if linking == "carino" and abs(residual) > IDENTITY_TOLERANCE:  # pragma: no cover
        raise ValidationError(f"linked effects do not add up (residual {residual})")
    return Attribution(
        by_period=by_period,
        totals=totals.loc[segments, list(EFFECTS)],
        portfolio_return=compounded_p,
        benchmark_return=compounded_b,
        active_return=active,
        residual=residual if linking == "none" else 0.0,
        linking=linking,
        interaction=interaction,
    )


def _log_ratio(p: float, b: float) -> float:
    """Return (ln(1+p) - ln(1+b)) / (p - b), with the limit 1/(1+p) when p == b."""
    if math.isclose(p, b, rel_tol=0.0, abs_tol=1e-15):
        return 1.0 / (1.0 + p)
    return (math.log1p(p) - math.log1p(b)) / (p - b)


def _carino(rp: np.ndarray, rb: np.ndarray, total_p: float, total_b: float) -> np.ndarray:
    k = np.array([_log_ratio(float(p), float(b)) for p, b in zip(rp, rb, strict=True)])
    return k / _log_ratio(total_p, total_b)
