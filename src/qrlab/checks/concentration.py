"""Concentration checks on position weights (look-through concentration comes in phase 2.5).

Weights are base-currency values over the total portfolio value **including cash**.
"""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import (
    Direction,
    Measurement,
    MeasureUnit,
    NotApplicable,
    spec,
)
from qrlab.core.money import Currency

__all__ = ["CHECKS"]


def largest_position(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Largest single position weight."""
    weights = ctx.position_weights()
    if not weights:
        return NotApplicable("no positions held")
    isin, weight = max(weights.items(), key=lambda item: (item[1], item[0].code))
    return [Measurement("portfolio", weight, {"isin": isin.code})]


def top5(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Sum of the five largest position weights."""
    weights = sorted(ctx.position_weights().values(), reverse=True)
    if not weights:
        return NotApplicable("no positions held")
    return [Measurement("portfolio", sum(weights[:5]), {"positions": str(len(weights))})]


def herfindahl(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Herfindahl index of position weights; details give the effective number of positions."""
    weights = ctx.position_weights().values()
    if not weights:
        return NotApplicable("no positions held")
    index = sum(w * w for w in weights)
    return [Measurement("portfolio", index, {"effective_positions": f"{1.0 / index:.4f}"})]


def foreign_currency(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Largest exposure to a single foreign currency (positions by exposure currency, and cash)."""
    exposure: dict[Currency, float] = {}
    for isin, weight in ctx.position_weights().items():
        currency = ctx.exposure_currency(isin)
        exposure[currency] = exposure.get(currency, 0.0) + weight
    for currency, weight in ctx.cash_weights().items():
        exposure[currency] = exposure.get(currency, 0.0) + weight
    foreign = {c: w for c, w in exposure.items() if c != ctx.base}
    if not foreign:
        return [Measurement("portfolio", 0.0, {"currency": ""})]
    currency, weight = max(foreign.items(), key=lambda item: (item[1], item[0].code))
    return [Measurement("portfolio", weight, {"currency": currency.code})]


CHECKS = (
    spec("concentration.largest_position", Direction.ABOVE, MeasureUnit.FRACTION, largest_position),
    spec("concentration.top5", Direction.ABOVE, MeasureUnit.FRACTION, top5),
    spec("concentration.herfindahl", Direction.ABOVE, MeasureUnit.RATIO, herfindahl),
    spec("concentration.foreign_currency", Direction.ABOVE, MeasureUnit.FRACTION, foreign_currency),
)
