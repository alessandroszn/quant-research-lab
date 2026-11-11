r"""Portfolio performance: time-weighted and money-weighted returns, P&L and currency effects.

- **TWR** (time-weighted return) measures the investments: daily returns chain-linked between
  valuation dates, neutralising external flows. Flow timing is an explicit choice.
- **MWR** (money-weighted return, XIRR) measures the investor's experience: the annual rate that
  sets the net present value of the investor's flows and the final value to zero (ACT/365).

The two are different quantities, always labelled, and never placed in the same column.

External flows are deposits, withdrawals and transfers of securities in or out (at market
value). Dividends, interest, fees and taxes are internal: they are part of the return.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from itertools import pairwise

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.instruments.identifiers import Isin
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.portfolio.ledger import LedgerHistory, ToBase
from qrlab.portfolio.valuation import Valuation

__all__ = [
    "CurrencyEffect",
    "FlowTiming",
    "PnlBreakdown",
    "TwrResult",
    "XirrResult",
    "contribution_by_position",
    "currency_effect",
    "external_flows_by_date",
    "money_weighted_return",
    "pnl_breakdown",
    "time_weighted_returns",
    "xirr",
]


class FlowTiming(Enum):
    """When external flows enter the portfolio within their day."""

    START_OF_DAY = "start_of_day"  # r_t = V_t / (V_{t-1} + F_t) - 1
    END_OF_DAY = "end_of_day"  # r_t = (V_t - F_t) / V_{t-1} - 1


@dataclass(frozen=True)
class TwrResult:
    """Time-weighted returns between valuation dates.

    Attributes
    ----------
    returns
        Period returns (simple, decimals) indexed by the period's end date, named ``"TWR"``.
    total
        Chain-linked total return over all periods.
    skipped
        Dates without a return because the starting capital was zero.
    flow_timing
        Convention used.
    """

    returns: pd.Series
    total: float
    skipped: tuple[date, ...]
    flow_timing: FlowTiming


@dataclass(frozen=True)
class XirrResult:
    """Money-weighted return.

    Attributes
    ----------
    rate
        Annual rate (ACT/365) setting the net present value of the flows to zero.
    sign_changes
        Sign changes in the date-ordered flows. With more than one, other roots may exist.
    candidates
        Every root found on a dense grid from -99.9999 % to 1e8 %; ``rate`` is the one closest
        to zero. More than one candidate means the MWR is not uniquely defined.
    label
        Always ``"MWR (XIRR, ACT/365)"``.
    """

    rate: float
    sign_changes: int
    candidates: tuple[float, ...]
    label: str = "MWR (XIRR, ACT/365)"

    @property
    def unique_root_guaranteed(self) -> bool:
        """Whether Descartes' rule of signs guarantees a single root (one sign change)."""
        return self.sign_changes == 1


@dataclass(frozen=True)
class PnlBreakdown:
    """Profit and loss over a period in the base currency, exactly decomposed.

    ``total = realised + unrealised_change + income - costs + cash_fx + residual``, where
    ``total`` is the change in value minus net external flows. ``residual`` is zero for a single
    currency and limited to ``Decimal`` rounding otherwise; a larger residual signals an error.
    """

    total: Decimal
    realised: Decimal
    unrealised_change: Decimal
    income: Decimal
    costs: Decimal
    cash_fx: Decimal
    residual: Decimal


@dataclass(frozen=True)
class CurrencyEffect:
    """Split of a base-currency return into local return and currency effect (local first)."""

    local_return: float
    fx_return: float
    base_return: float
    fx_effect: float


def external_flows_by_date(history: LedgerHistory) -> dict[date, Decimal]:
    """Net external flows per date in the base currency (+ in, - out)."""
    flows: dict[date, Decimal] = {}
    for flow in history.external_flows:
        flows[flow.trade_date] = flows.get(flow.trade_date, Decimal(0)) + flow.amount_base
    return flows


def time_weighted_returns(
    valuation: Valuation, flows: Mapping[date, Decimal], *, flow_timing: FlowTiming
) -> TwrResult:
    """Chain-linked time-weighted returns between consecutive valuation dates.

    Every flow must fall on a valuation date, and no flow may precede the first one (the value
    before the first valuation date is taken as zero). Periods whose starting capital is zero
    (e.g. before the first deposit with ``END_OF_DAY``) are skipped and listed.
    """
    if not isinstance(flow_timing, FlowTiming):
        raise ValidationError(f"flow_timing must be a FlowTiming, got {flow_timing!r}")
    dates = list(valuation.totals)
    for day in flows:
        if day not in valuation.totals:
            raise ValidationError(f"flow on {day} is not on a valuation date")
    previous = Decimal(0)
    returns: dict[date, float] = {}
    skipped: list[date] = []
    for day in dates:
        value, flow = valuation.totals[day], flows.get(day, Decimal(0))
        if flow_timing is FlowTiming.START_OF_DAY:
            numerator, denominator = value, previous + flow
        else:
            numerator, denominator = value - flow, previous
        if denominator == 0:
            skipped.append(day)
        else:
            returns[day] = float(numerator / denominator - 1)
        previous = value
    series = pd.Series(
        list(returns.values()),
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in returns]),
        name="TWR",
        dtype="float64",
    )
    total = math.prod(1.0 + r for r in returns.values()) - 1.0
    return TwrResult(series, total, tuple(skipped), flow_timing)


def xirr(flows: Sequence[tuple[date, Decimal]]) -> XirrResult:
    """Annual internal rate of return of dated flows (ACT/365), solved with Brent's method.

    Flows are from the investor's point of view: money paid in is negative, money received
    (including the final value) is positive.

    Raises
    ------
    UndefinedMetricError
        Without at least one negative and one positive flow, or when no root is bracketed.
    """
    merged: dict[date, float] = {}
    for day, amount in flows:
        merged[day] = merged.get(day, 0.0) + float(amount)
    ordered = [(d, a) for d, a in sorted(merged.items()) if a != 0.0]
    if not any(a < 0 for _, a in ordered) or not any(a > 0 for _, a in ordered):
        raise UndefinedMetricError("xirr needs at least one negative and one positive flow")
    start = ordered[0][0]
    times = [(d - start).days / 365.0 for d, _ in ordered]
    amounts = [a for _, a in ordered]

    def npv(rate: float) -> float:
        return float(sum(a / (1.0 + rate) ** t for a, t in zip(amounts, times, strict=True)))

    # Several roots are possible (one per sign change at most): scan a dense grid of rates for
    # sign changes, solve each bracket with Brent's method, and keep every root found.
    grid = np.unique(
        np.concatenate([np.linspace(-0.999999, 1.0, 4001), np.geomspace(1.0, 1e6, 400), [0.0]])
    )
    values = np.array([npv(float(r)) for r in grid])
    roots: list[float] = []
    for index in np.flatnonzero(np.sign(values[:-1]) * np.sign(values[1:]) <= 0):
        i = int(index)
        low, high = float(grid[i]), float(grid[i + 1])
        if values[i] == 0:
            roots.append(low)
        else:
            roots.append(float(brentq(npv, low, high, xtol=1e-14, rtol=1e-14, maxiter=500)))
    if not roots:
        raise UndefinedMetricError("xirr: no rate between -99.9999 % and 1e8 % solves the flows")
    unique = sorted({round(r, 12) for r in roots})
    rate = min(unique, key=abs)
    signs = [a > 0 for a in amounts]
    changes = sum(1 for a, b in pairwise(signs) if a != b)
    return XirrResult(rate, changes, tuple(unique))


def money_weighted_return(history: LedgerHistory, valuation: Valuation, *, end: date) -> XirrResult:
    """MWR from inception to ``end``: investor flows plus the value on ``end``.

    ``end`` must be a valuation date.
    """
    if end not in valuation.totals:
        raise ValidationError(f"end {end} is not a valuation date")
    flows = [(f.trade_date, -f.amount_base) for f in history.external_flows if f.trade_date <= end]
    flows.append((end, valuation.totals[end]))
    return xirr(flows)


def pnl_breakdown(
    history: LedgerHistory, valuation: Valuation, to_base: ToBase, *, start: date | None, end: date
) -> PnlBreakdown:
    """Decompose the profit and loss over ``(start, end]`` in the base currency.

    Parameters
    ----------
    history, valuation
        Ledger history and its valuation.
    to_base
        The converter used for the ledger and the valuation (needed for the cash FX effect).
    start
        A valuation date, or ``None`` for inception (zero value before the first transaction).
    end
        A valuation date after ``start``.
    """
    _check_period(valuation, start, end)

    def in_period(day: date) -> bool:
        return (start is None or day > start) and day <= end

    value_start = Decimal(0) if start is None else valuation.totals[start]
    flows = sum(
        (f.amount_base for f in history.external_flows if in_period(f.trade_date)), Decimal(0)
    )
    total = valuation.totals[end] - value_start - flows
    realised = sum((g.gain_base for g in history.realised if in_period(g.trade_date)), Decimal(0))
    unrealised = _unrealised(history, valuation, end) - (
        Decimal(0) if start is None else _unrealised(history, valuation, start)
    )
    income = sum((i.net_base for i in history.income if in_period(i.trade_date)), Decimal(0))
    costs = sum((c.amount_base for c in history.costs if in_period(c.trade_date)), Decimal(0))
    cash_fx = _cash_fx(history, to_base, start, end, in_period)
    residual = total - (realised + unrealised + income - costs + cash_fx)
    return PnlBreakdown(total, realised, unrealised, income, costs, cash_fx, residual)


def contribution_by_position(
    history: LedgerHistory, valuation: Valuation, to_base: ToBase, *, start: date | None, end: date
) -> dict[tuple[str, Isin], Decimal]:
    """Money P&L per position over ``(start, end]``: realised + unrealised change + dividends.

    The remainder of :func:`pnl_breakdown` (interest, standalone costs, cash FX effect) belongs
    to no position. Percentage contributions linked over several periods are part of
    attribution (phase 4.4).
    """
    _check_period(valuation, start, end)

    def in_period(day: date) -> bool:
        return (start is None or day > start) and day <= end

    result: dict[tuple[str, Isin], Decimal] = {}

    def add(key: tuple[str, Isin], amount: Decimal) -> None:
        result[key] = result.get(key, Decimal(0)) + amount

    for gain in history.realised:
        if in_period(gain.trade_date):
            add((gain.account, gain.isin), gain.gain_base)
    for income in history.income:
        if income.isin is not None and in_period(income.trade_date):
            add((income.account, income.isin), income.net_base)
    for key, value in _unrealised_by_position(history, valuation, end).items():
        add(key, value)
    if start is not None:
        for key, value in _unrealised_by_position(history, valuation, start).items():
            add(key, -value)
    return result


def currency_effect(*, local_return: float, fx_return: float) -> CurrencyEffect:
    r"""Split a base-currency return with the local-first convention.

    :math:`1 + r_{base} = (1 + r_{local})(1 + r_{fx})` and the currency effect is
    :math:`(1 + r_{local})\, r_{fx}`, so that ``local_return + fx_effect == base_return``.
    ``fx_return`` is the change in the base-currency value of one unit of the local currency.
    """
    for name, value in (("local_return", local_return), ("fx_return", fx_return)):
        if not math.isfinite(value) or value <= -1.0:
            raise ValidationError(f"{name} must be finite and greater than -1, got {value}")
    base = (1.0 + local_return) * (1.0 + fx_return) - 1.0
    return CurrencyEffect(local_return, fx_return, base, (1.0 + local_return) * fx_return)


# --------------------------------------------------------------------------- helpers
def _check_period(valuation: Valuation, start: date | None, end: date) -> None:
    for day in (start, end):
        if day is not None and day not in valuation.totals:
            raise ValidationError(f"{day} is not a valuation date")
    if start is not None and start >= end:
        raise ValidationError(f"start {start} must be before end {end}")


def _unrealised_by_position(
    history: LedgerHistory, valuation: Valuation, day: date
) -> dict[tuple[str, Isin], Decimal]:
    state = history.state_on(day)
    return {
        key: value - state.positions[key].cost_base
        for key, value in valuation.positions[day].items()
    }


def _unrealised(history: LedgerHistory, valuation: Valuation, day: date) -> Decimal:
    return sum(_unrealised_by_position(history, valuation, day).values(), Decimal(0))


def _cash_fx(
    history: LedgerHistory,
    to_base: ToBase,
    start: date | None,
    end: date,
    in_period: object,
) -> Decimal:
    """Revaluation of foreign-currency cash between the movement (or start) and ``end``."""
    assert callable(in_period)
    base = history.base

    def unit_value(currency: object, day: date) -> Decimal:
        assert currency is not None
        converted = to_base(Money(Decimal(1), currency), day)  # type: ignore[arg-type]
        return converted.amount

    effect = Decimal(0)
    if start is not None:
        for (_, currency), balance in history.state_on(start).cash.items():
            if currency != base and balance:
                effect += balance * (unit_value(currency, end) - unit_value(currency, start))
    for movement in history.cash_movements:
        if movement.currency != base and in_period(movement.trade_date):
            effect += movement.amount * (
                unit_value(movement.currency, end)
                - unit_value(movement.currency, movement.trade_date)
            )
    return effect
