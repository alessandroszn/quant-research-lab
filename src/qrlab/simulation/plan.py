r"""Savings and withdrawal plans projected over simulated returns.

Wealth is tracked per path and per asset, with its average cost basis, in floating point in
the base currency (Monte Carlo works with floats; ledgers keep exact decimals).

Within each period :math:`t` (0-based):

1. flows with ``flow_timing="start"``;
2. the simulated returns of period :math:`t`;
3. ongoing costs and the wealth tax, both annual rates charged pro rata on value;
4. flows with ``flow_timing="end"``;
5. rebalancing to the target weights every ``rebalance_every`` periods (``None``: never).

**Flows.** Contributions are invested at the target weights. Withdrawals are **net** amounts to
spend: holdings are sold in proportion to their value, and the capital-gains tax on the gains
realised is paid from wealth on top. Selling :math:`S` out of wealth :math:`W` realises
:math:`\sum_i (S/W)\max(H_i-B_i, 0)`, so :math:`S = N/(1-\tau G/W)` with :math:`G=\sum_i
\max(H_i-B_i,0)`. Without :class:`~qrlab.simulation.losses.LossRules`, gains and losses of
different assets are not netted and losses are not carried forward, which overstates taxes
slightly. With them (phase 8.6b), fund gains are taxed in full and other gains use the losses,
the Italian way; a withdrawal then solves the same equation with the offset, which stays in
closed form (see :func:`_gross_withdrawal`). Indexed flows grow with inflation as
:math:`(1+\pi)^{t/P}`.

**Depletion.** A path is depleted in the first period whose withdrawal (plus tax) needs more
than its wealth: what is left is paid out (net of tax), the shortfall is recorded, and the path
stays at zero afterwards, ignoring later flows.

**Rebalancing** sells the assets above their target and buys the others. The tax on the gains
realised by those sales is computed on the pre-tax targets and then taken from all holdings
pro rata (a stated first-order approximation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.simulation.engines import SimulatedReturns
from qrlab.simulation.losses import LossBalance, LossRules, fund_mask, realised_tax

__all__ = ["Flow", "Plan", "Projection", "TaxModel", "project"]

_TIMINGS = ("start", "end")


@dataclass(frozen=True)
class Flow:
    """A recurring amount per period from ``first`` to ``last`` (inclusive, 0-based periods).

    ``kind`` is ``"contribution"`` or ``"withdrawal"`` (a net amount to spend). ``indexed`` makes
    the amount grow with inflation.
    """

    kind: str
    amount: float
    first: int
    last: int
    indexed: bool

    def __post_init__(self) -> None:
        """Validate the flow."""
        if self.kind not in ("contribution", "withdrawal"):
            raise ValidationError(
                f'flow kind must be "contribution" or "withdrawal", got {self.kind!r}'
            )
        if type(self.amount) not in (int, float) or not (
            math.isfinite(self.amount) and self.amount > 0
        ):
            raise ValidationError("flow amount must be a positive number")
        for name in ("first", "last"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValidationError(f"flow {name} must be an int >= 0")
        if self.last < self.first:
            raise ValidationError("flow last period is before its first period")
        if not isinstance(self.indexed, bool):
            raise ValidationError("indexed must be True or False")


@dataclass(frozen=True)
class TaxModel:
    """Capital-gains tax on realised gains and an annual tax on value (both fractions).

    ``losses`` (phase 8.6b): ``None`` ignores realised losses, as before; a
    :class:`~qrlab.simulation.losses.LossRules` carries them the Italian way.

    ``income_tax_rate`` and ``taxable_yield`` (phase 9.2): a yearly tax on the income the
    holdings yield, ``income_tax_rate x taxable_yield`` of value, paid each period like the
    wealth tax. It is exact for accumulating funds, whose reinvested income is taxed every
    year (Switzerland), and an approximation for distributing ones. Both 0: no such tax.
    """

    capital_gains_rate: float
    wealth_tax_rate: float
    losses: LossRules | None = None
    income_tax_rate: float = 0.0
    taxable_yield: float = 0.0

    def __post_init__(self) -> None:
        """Validate the rates."""
        for name in ("capital_gains_rate", "wealth_tax_rate", "income_tax_rate", "taxable_yield"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not 0.0 <= value < 1.0:
                raise ValidationError(f"{name} must be in [0, 1)")
        if self.losses is not None and not isinstance(self.losses, LossRules):
            raise ValidationError(f"losses must be LossRules or None, got {self.losses!r}")


@dataclass(frozen=True)
class Plan:
    """Everything a projection assumes, stated explicitly."""

    initial_wealth: float
    currency: Currency
    weights: pd.Series
    periods_per_year: int
    flows: tuple[Flow, ...]
    flow_timing: str
    rebalance_every: int | None
    annual_cost: float
    inflation: float
    taxes: TaxModel

    def __post_init__(self) -> None:
        """Validate the plan."""
        if type(self.initial_wealth) not in (int, float) or not (
            math.isfinite(self.initial_wealth) and self.initial_wealth >= 0
        ):
            raise ValidationError("initial_wealth must be a finite number >= 0")
        w = self.weights.to_numpy(dtype=np.float64)
        if self.weights.index.has_duplicates or not np.all(np.isfinite(w)) or (w < 0).any():
            raise ValidationError("weights must be unique, finite and non-negative")
        if abs(float(w.sum()) - 1.0) > 1e-9:
            raise ValidationError(f"weights must sum to 1 (got {w.sum()}); not rescaled")
        if type(self.periods_per_year) is not int or self.periods_per_year < 1:
            raise ValidationError("periods_per_year must be a positive int")
        if self.flow_timing not in _TIMINGS:
            raise ValidationError('flow_timing must be "start" or "end"')
        if self.rebalance_every is not None and (
            type(self.rebalance_every) is not int or self.rebalance_every < 1
        ):
            raise ValidationError("rebalance_every must be None or a positive int")
        if type(self.annual_cost) not in (int, float) or not 0.0 <= self.annual_cost < 1.0:
            raise ValidationError("annual_cost must be in [0, 1)")
        if type(self.inflation) not in (int, float) or not -1.0 < self.inflation < 1.0:
            raise ValidationError("inflation must be in (-1, 1)")


@dataclass(frozen=True)
class Projection:
    r"""Projected wealth per path.

    Attributes
    ----------
    nominal
        Wealth at the end of each period, shape (paths, periods + 1); column 0 is the start.
    real
        ``nominal`` in today's money, deflated by :math:`(1+\pi)^{t/P}`.
    depleted_period
        First depleted period per path, or -1.
    shortfall
        Net withdrawals that could not be paid, per path (nominal).
    taxes_paid
        Capital-gains and wealth taxes paid during the projection, per path (nominal).
    liquidation_value
        Terminal wealth after the capital-gains tax of selling everything (nominal).
    plan
        The plan projected.
    engine
        Name and parameters of the return engine.
    """

    nominal: np.ndarray
    real: np.ndarray
    depleted_period: np.ndarray
    shortfall: np.ndarray
    taxes_paid: np.ndarray
    liquidation_value: np.ndarray
    plan: Plan
    engine: str


def project(plan: Plan, returns: SimulatedReturns) -> Projection:
    """Project ``plan`` over ``returns`` (assets must match the plan's weights)."""
    if tuple(map(str, plan.weights.index)) != returns.assets:
        planned, simulated = list(plan.weights.index), list(returns.assets)
        raise ValidationError(f"plan assets {planned} must match the simulated {simulated}")
    periods, paths = returns.n_periods, returns.n_paths
    for flow in plan.flows:
        if flow.last >= periods:
            raise ValidationError(f"a flow ends in period {flow.last}, after the horizon {periods}")
    target = plan.weights.to_numpy(dtype=np.float64)
    rate = plan.taxes.capital_gains_rate
    rules = plan.taxes.losses
    losses = None
    if rules is not None:
        losses = _Losses(
            funds=fund_mask(rules, [str(a) for a in plan.weights.index]),
            balance=LossBalance(
                paths=paths,
                years=periods // plan.periods_per_year + 1,
                carry_years=rules.carry_years,
            ),
        )
    state = _State(
        holdings=np.outer(np.full(paths, float(plan.initial_wealth)), target),
        basis=np.outer(np.full(paths, float(plan.initial_wealth)), target),
        alive=np.ones(paths, dtype=bool),
        depleted=np.full(paths, -1),
        shortfall=np.zeros(paths),
        taxes=np.zeros(paths),
        losses=losses,
    )
    nominal = np.empty((paths, periods + 1))
    nominal[:, 0] = state.holdings.sum(axis=1)
    drag = 1.0 - plan.annual_cost / plan.periods_per_year
    taxes = plan.taxes
    wealth_tax = (
        taxes.wealth_tax_rate + taxes.income_tax_rate * taxes.taxable_yield
    ) / plan.periods_per_year
    for t in range(periods):
        index = (1.0 + plan.inflation) ** (t / plan.periods_per_year)
        state.year = t // plan.periods_per_year
        if plan.flow_timing == "start":
            _apply_flows(state, plan, t, index, target, rate)
        state.holdings *= 1.0 + returns.returns[:, t, :]
        state.holdings *= drag
        if wealth_tax:
            paid = state.holdings.sum(axis=1) * wealth_tax
            state.taxes += paid
            state.holdings *= 1.0 - wealth_tax
        if plan.flow_timing == "end":
            _apply_flows(state, plan, t, index, target, rate)
        if plan.rebalance_every is not None and (t + 1) % plan.rebalance_every == 0:
            _rebalance(state, target, rate)
        state.holdings[~state.alive] = 0.0
        nominal[:, t + 1] = state.holdings.sum(axis=1)
    deflator = (1.0 + plan.inflation) ** (np.arange(periods + 1) / plan.periods_per_year)
    if state.losses is None:
        liquidation_tax = rate * np.clip(state.holdings - state.basis, 0.0, None).sum(axis=1)
    else:
        liquidation_tax = realised_tax(
            state.holdings - state.basis,
            rate,
            state.losses.funds,
            state.losses.balance,
            periods // plan.periods_per_year,
        )
    return Projection(
        nominal=nominal,
        real=nominal / deflator,
        depleted_period=state.depleted,
        shortfall=state.shortfall,
        taxes_paid=state.taxes,
        liquidation_value=nominal[:, -1] - liquidation_tax,
        plan=plan,
        engine=returns.engine,
    )


@dataclass
class _Losses:
    funds: np.ndarray  # which assets are funds
    balance: LossBalance


@dataclass
class _State:
    holdings: np.ndarray
    basis: np.ndarray
    alive: np.ndarray
    depleted: np.ndarray
    shortfall: np.ndarray
    taxes: np.ndarray
    losses: _Losses | None = None
    year: int = 0


def _apply_flows(
    state: _State, plan: Plan, t: int, index: float, target: np.ndarray, rate: float
) -> None:
    contribution = withdrawal = 0.0
    for flow in plan.flows:
        if flow.first <= t <= flow.last:
            amount = flow.amount * (index if flow.indexed else 1.0)
            if flow.kind == "contribution":
                contribution += amount
            else:
                withdrawal += amount
    alive = state.alive
    if contribution:
        state.holdings[alive] += contribution * target
        state.basis[alive] += contribution * target
    if withdrawal:
        _withdraw(state, t, withdrawal, rate)


def _withdraw(state: _State, t: int, net: float, rate: float) -> None:
    wealth = state.holdings.sum(axis=1)
    if state.losses is None:
        gains = np.clip(state.holdings - state.basis, 0.0, None).sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            gain_share = np.where(wealth > 0, gains / wealth, 0.0)
        gross = net / (1.0 - rate * gain_share)
    else:
        gross = _gross_withdrawal(state, net, rate, wealth)
    enough = state.alive & (gross <= wealth)
    running_out = state.alive & ~enough
    with np.errstate(divide="ignore", invalid="ignore"):
        sold = np.where(enough, gross / wealth, 0.0)
    if state.losses is None:
        full_tax = rate * gains
    else:
        share = np.where(running_out, 1.0, sold)
        full_tax = realised_tax(
            share[:, None] * (state.holdings - state.basis),
            rate,
            state.losses.funds,
            state.losses.balance,
            state.year,
        )
    state.taxes += np.where(enough, gross - net, 0.0)
    state.holdings *= (1.0 - sold)[:, None]
    state.basis *= (1.0 - sold)[:, None]
    if running_out.any():
        paid_out = wealth - full_tax
        state.taxes += np.where(running_out, full_tax, 0.0)
        state.shortfall += np.where(running_out, net - paid_out, 0.0)
        state.depleted = np.where(running_out, t, state.depleted)
        state.alive &= ~running_out
        state.holdings[running_out] = 0.0
        state.basis[running_out] = 0.0


def _gross_withdrawal(state: _State, net: float, rate: float, wealth: np.ndarray) -> np.ndarray:
    r"""Return the gross sale :math:`S` that pays ``net`` after tax, with carried losses.

    Selling a share :math:`s = S/W` realises :math:`sF` on funds and :math:`sD` net on the
    other assets (:math:`D` = their gains minus every loss), with :math:`C` losses usable. The
    tax is :math:`\tau sF` while :math:`sD \le C` (or :math:`D \le 0`), so
    :math:`S = N/(1-\tau F/W)` as without losses; otherwise it is
    :math:`\tau(sF + sD - C)`, so :math:`S = W(N - \tau C)/(W - \tau(F + D))`.
    """
    assert state.losses is not None  # only called with rules
    diff = state.holdings - state.basis
    funds = state.losses.funds
    fund_gain = np.clip(diff[:, funds], 0.0, None).sum(axis=1)
    other = np.clip(diff[:, ~funds], 0.0, None).sum(axis=1) - np.clip(-diff, 0.0, None).sum(axis=1)
    carried = state.losses.balance.available(state.year)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain_share = np.where(wealth > 0, fund_gain / wealth, 0.0)
        gross = net / (1.0 - rate * gain_share)
        beyond = (other > 0) & (gross / wealth * other > carried)
        offset = wealth * (net - rate * carried) / (wealth - rate * (fund_gain + other))
    return np.where(beyond, offset, gross)


def _rebalance(state: _State, target: np.ndarray, rate: float) -> None:
    wealth = state.holdings.sum(axis=1, keepdims=True)
    goal = wealth * target
    with np.errstate(divide="ignore", invalid="ignore"):
        sold_share = np.where(state.holdings > goal, (state.holdings - goal) / state.holdings, 0.0)
    if state.losses is None:
        realised = sold_share * np.clip(state.holdings - state.basis, 0.0, None)
        tax = rate * realised.sum(axis=1)
    else:
        tax = realised_tax(
            sold_share * (state.holdings - state.basis),
            rate,
            state.losses.funds,
            state.losses.balance,
            state.year,
        )
    state.taxes += np.where(state.alive, tax, 0.0)
    bought = np.clip(goal - state.holdings, 0.0, None)
    state.basis = state.basis * (1.0 - sold_share) + bought
    with np.errstate(divide="ignore", invalid="ignore"):
        after_tax = np.where(wealth[:, 0] > 0, 1.0 - tax / wealth[:, 0], 0.0)
    state.holdings = goal * after_tax[:, None]
    state.basis *= after_tax[:, None]
