r"""Rebalancing policies and the cost of one rebalance.

A policy decides **when** to trade (:meth:`due`) and **to what** (:meth:`destination`); running
it over history with drift, costs and taxes is the backtest's job (phase 4.3).

- :class:`CalendarPolicy`: rebalance to target every ``every`` periods (periods 1, 2, ... after
  the start; never at period 0).
- :class:`ThresholdPolicy`: rebalance when any :math:`|w_i - w^*_i| >` ``band``; ``to="target"``
  goes back to target, ``to="band"`` only to the band edge (deviations clipped to the band). If
  clipping leaves the weights summing to less or more than 1, the residual goes to the assets
  inside the band in proportion to their targets (to all assets if every one was clipped).

:func:`trade` returns the trades in money, the turnover :math:`\sum|\Delta w|`, the amount
traded and the cost: an explicit proportional rate on the amount traded plus a fixed fee per
asset traded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError

__all__ = ["CalendarPolicy", "CostModel", "ThresholdPolicy", "Trade", "trade"]

_MIN_TRADE = 1e-12


@dataclass(frozen=True)
class CalendarPolicy:
    """Rebalance to target every ``every`` periods."""

    every: int

    def __post_init__(self) -> None:
        """Validate the period."""
        if type(self.every) is not int or self.every < 1:
            raise ValidationError("every must be a positive int")

    def due(self, period: int, current: pd.Series, target: pd.Series) -> bool:
        """Return whether to rebalance at ``period`` (0 is the start)."""
        return period > 0 and period % self.every == 0

    def destination(self, current: pd.Series, target: pd.Series) -> pd.Series:
        """Return the weights to trade to."""
        _check(current, target)
        return target.copy()


@dataclass(frozen=True)
class ThresholdPolicy:
    """Rebalance when a weight drifts more than ``band`` from target."""

    band: float
    to: str

    def __post_init__(self) -> None:
        """Validate the band and the destination rule."""
        if type(self.band) not in (int, float) or not (math.isfinite(self.band) and self.band > 0):
            raise ValidationError("band must be a positive number")
        if self.to not in ("target", "band"):
            raise ValidationError('to must be "target" or "band"')

    def due(self, period: int, current: pd.Series, target: pd.Series) -> bool:
        """Return whether any weight is outside the band."""
        _check(current, target)
        return bool((current - target).abs().max() > self.band)

    def destination(self, current: pd.Series, target: pd.Series) -> pd.Series:
        """Return the target, or the band edge with the residual redistributed."""
        _check(current, target)
        if self.to == "target":
            return target.copy()
        deviation = current - target
        clipped = deviation.clip(-self.band, self.band)
        weights = target + clipped
        residual = 1.0 - float(weights.sum())
        inside = deviation.abs() <= self.band
        receivers = target[inside] if inside.any() else target
        weights = weights.add(residual * receivers / float(receivers.sum()), fill_value=0.0)
        return weights.reindex(target.index)


@dataclass(frozen=True)
class CostModel:
    """Proportional cost on the amount traded plus a fixed fee per asset traded."""

    proportional: float
    fixed: float

    def __post_init__(self) -> None:
        """Validate the costs."""
        for name in ("proportional", "fixed"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not (math.isfinite(value) and value >= 0):
                raise ValidationError(f"{name} cost must be a finite number >= 0")


@dataclass(frozen=True)
class Trade:
    """One rebalance: amounts per asset (positive = buy), turnover, amount traded and cost."""

    amounts: pd.Series
    turnover: float
    traded: float
    cost: float
    trades: int


def trade(current: pd.Series, destination: pd.Series, value: float, costs: CostModel) -> Trade:
    """Return the trades that move a portfolio of ``value`` from ``current`` to ``destination``."""
    _check(current, destination)
    if not (math.isfinite(value) and value >= 0):
        raise ValidationError("value must be a finite number >= 0")
    delta = np.array(destination - current.reindex(destination.index), dtype=np.float64)
    delta[np.abs(delta) < _MIN_TRADE] = 0.0
    amounts = pd.Series(delta * value, index=destination.index)
    traded = float(np.abs(amounts).sum())
    count = int((np.abs(delta) > 0).sum())
    cost = costs.proportional * traded + costs.fixed * count
    return Trade(amounts, float(np.abs(delta).sum()), traded, cost, count)


def _check(current: pd.Series, target: pd.Series) -> None:
    if set(current.index) != set(target.index):
        raise ValidationError("current and target weights must cover the same assets")
    for name, weights in (("current", current), ("target", target)):
        values = weights.to_numpy(dtype=np.float64)
        if not np.all(np.isfinite(values)) or abs(float(values.sum()) - 1.0) > 1e-9:
            raise ValidationError(f"{name} weights must be finite and sum to 1")
