"""Diversification checks on position returns (effective number of bets: phase 3.1).

Position returns are simple returns of each held instrument's price series up to ``as_of``,
on the dates where every held instrument has a price (rows with a missing price are dropped),
over the last ``window`` returns. Fewer returns than ``window`` makes the check not
applicable; it is never estimated on a shorter sample.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import Direction, Measurement, MeasureUnit, NotApplicable, spec
from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind, prices_to_returns

__all__ = ["CHECKS", "position_returns"]


def position_returns(ctx: CheckContext, window: object) -> pd.DataFrame | NotApplicable:
    """Aligned returns of the held positions over the last ``window`` dates, or N/A."""
    if type(window) is not int or window < 2:
        raise ValidationError(f"window must be an int >= 2, got {window!r}")
    held = sorted(ctx.position_weights(), key=lambda i: i.code)
    if len(held) < 2:
        return NotApplicable("needs at least two positions")
    missing = [i.code for i in held if i not in ctx.prices]
    if missing:
        return NotApplicable(f"no price series for {missing}")
    columns = {}
    for isin in held:
        prices = ctx.prices[isin].prices.loc[: pd.Timestamp(ctx.as_of)]
        columns[isin.code] = prices_to_returns(prices, kind=ReturnKind.SIMPLE)
    returns = pd.concat(columns, axis=1, join="inner").dropna()
    if len(returns) < window:
        return NotApplicable(f"{len(returns)} common returns, fewer than the window of {window}")
    tail = returns.iloc[-window:]
    if (tail.std(ddof=1) == 0).any():
        return NotApplicable("a position has zero return variance over the window")
    return tail


def average_correlation(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Average pairwise correlation of position returns."""
    returns = position_returns(ctx, params["window"])
    if isinstance(returns, NotApplicable):
        return returns
    corr = np.corrcoef(returns.to_numpy(), rowvar=False)
    upper = corr[np.triu_indices_from(corr, k=1)]
    return [Measurement("portfolio", float(np.mean(upper)), {"pairs": str(len(upper))})]


def diversification_ratio(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Weighted average volatility over portfolio volatility (weights renormalised to positions)."""
    returns = position_returns(ctx, params["window"])
    if isinstance(returns, NotApplicable):
        return returns
    weights = ctx.position_weights()
    w = np.array([weights[next(i for i in weights if i.code == c)] for c in returns.columns])
    w = w / w.sum()
    cov = np.cov(returns.to_numpy(), rowvar=False, ddof=1)
    sigma = np.sqrt(np.diag(cov))
    ratio = float(w @ sigma / np.sqrt(w @ cov @ w))
    return [Measurement("portfolio", ratio, {"window": str(len(returns))})]


CHECKS = (
    spec(
        "diversification.average_correlation",
        Direction.ABOVE,
        MeasureUnit.RATIO,
        average_correlation,
        "window",
    ),
    spec(
        "diversification.ratio", Direction.BELOW, MeasureUnit.RATIO, diversification_ratio, "window"
    ),
)
