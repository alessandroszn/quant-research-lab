"""Currency and drift checks.

- Unhedged foreign exposure: weight of positions whose exposure currency (the hedge currency
  for hedged share classes, else the fund currency) differs from the base currency, plus
  foreign cash. Look-through currency exposure refines this in phase 2.5.
- Drift: deviation of current weights from ``CheckContext.target_weights`` (keys: ISIN codes and
  ``"cash"``); holdings missing from the targets have a target of 0.
"""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.checks.context import CASH, CheckContext
from qrlab.checks.framework import Direction, Measurement, MeasureUnit, NotApplicable, spec

__all__ = ["CHECKS", "current_weights"]


def unhedged_foreign(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Total weight exposed to currencies other than the base currency."""
    weight = sum(
        w for i, w in ctx.position_weights().items() if ctx.exposure_currency(i) != ctx.base
    )
    weight += sum(w for c, w in ctx.cash_weights().items() if c != ctx.base)
    return [Measurement("portfolio", weight)]


def current_weights(ctx: CheckContext) -> dict[str, float]:
    """Return current weights keyed like the targets: ISIN codes and ``"cash"``."""
    weights = {isin.code: w for isin, w in ctx.position_weights().items()}
    weights[CASH] = sum(ctx.cash_weights().values())
    return weights


def _deviations(ctx: CheckContext) -> dict[str, float] | NotApplicable:
    if ctx.target_weights is None:
        return NotApplicable("no target weights given")
    current = current_weights(ctx)
    keys = set(current) | set(ctx.target_weights)
    return {k: current.get(k, 0.0) - ctx.target_weights.get(k, 0.0) for k in sorted(keys)}


def max_deviation(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Largest absolute deviation from a target weight."""
    deviations = _deviations(ctx)
    if isinstance(deviations, NotApplicable):
        return deviations
    key, value = max(deviations.items(), key=lambda item: (abs(item[1]), item[0]))
    return [Measurement("portfolio", abs(value), {"holding": key, "deviation": f"{value:+.6f}"})]


def total_drift(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Half the sum of absolute deviations: the share of the portfolio to trade to rebalance."""
    deviations = _deviations(ctx)
    if isinstance(deviations, NotApplicable):
        return deviations
    return [Measurement("portfolio", 0.5 * sum(abs(v) for v in deviations.values()))]


CHECKS = (
    spec("currency.unhedged_foreign", Direction.ABOVE, MeasureUnit.FRACTION, unhedged_foreign),
    spec("drift.max_deviation", Direction.ABOVE, MeasureUnit.FRACTION, max_deviation),
    spec("drift.total", Direction.ABOVE, MeasureUnit.FRACTION, total_drift),
)  # fmt: skip
