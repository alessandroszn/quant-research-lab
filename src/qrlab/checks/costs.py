"""Cost checks: weighted TER, trading-cost drag and estimated total cost of ownership.

- Weighted TER is over the total value including cash (cash and non-fund holdings have no TER).
  Unknown TERs are **excluded**, never counted as zero; the excluded weight is reported.
- Trading-cost drag: purchase and sale charges (base currency) from the first valuation date to
  ``as_of``, divided by the average portfolio value on the valuation dates, annualised by
  365 / days.
- Total cost of ownership: weighted TER + trading-cost drag (both annual rates).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import (
    Direction,
    Measurement,
    MeasureUnit,
    NotApplicable,
    spec,
)
from qrlab.instruments.master import FUND_TYPES

__all__ = ["CHECKS", "trading_drag_value", "weighted_ter_value"]


def weighted_ter_value(ctx: CheckContext) -> tuple[float, float] | None:
    """Return (weighted TER, weight excluded for unknown TER), or ``None`` if nothing is known."""
    known = False
    ter = 0.0
    excluded = 0.0
    for isin, weight in ctx.position_weights().items():
        instrument = ctx.instruments.get(isin)
        if instrument is None or (
            instrument.instrument_type in FUND_TYPES and instrument.ter is None
        ):
            excluded += weight
            continue
        known = True
        if instrument.ter is not None:
            ter += weight * float(instrument.ter)
    return (ter, excluded) if known else None


def trading_drag_value(ctx: CheckContext) -> float | None:
    """Annualised trade charges over the average value, or ``None`` for a zero-length period."""
    dates = [d for d in ctx.valuation.totals if d <= ctx.as_of]
    start = dates[0]
    days = (ctx.as_of - start).days
    if days == 0:
        return None
    charges = sum(
        (c.amount_base for c in ctx.history.trade_charges if start <= c.trade_date <= ctx.as_of),
        Decimal(0),
    )
    average = sum((ctx.valuation.totals[d] for d in dates), Decimal(0)) / len(dates)
    return float(charges / average) * 365.0 / days


def weighted_ter(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Weighted TER of the portfolio."""
    value = weighted_ter_value(ctx)
    if value is None:
        return NotApplicable("no TER known for any position")
    ter, excluded = value
    return [Measurement("portfolio", ter, {"excluded_weight": f"{excluded:.6f}"})]


def trading_drag(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Trading-cost drag, annualised."""
    value = trading_drag_value(ctx)
    if value is None:
        return NotApplicable("the period has zero length")
    return [Measurement("portfolio", value)]


def total_cost(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Weighted TER plus trading-cost drag."""
    ter = weighted_ter_value(ctx)
    drag = trading_drag_value(ctx)
    if ter is None or drag is None:
        return NotApplicable("needs both a known TER and a non-zero period")
    return [
        Measurement("portfolio", ter[0] + drag, {"ter": f"{ter[0]:.6f}", "drag": f"{drag:.6f}"})
    ]


CHECKS = (
    spec("costs.weighted_ter", Direction.ABOVE, MeasureUnit.FRACTION, weighted_ter),
    spec("costs.trading_drag", Direction.ABOVE, MeasureUnit.FRACTION, trading_drag),
    spec("costs.total_cost", Direction.ABOVE, MeasureUnit.FRACTION, total_cost),
)
