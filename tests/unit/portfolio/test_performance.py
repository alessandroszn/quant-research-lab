"""Performance: TWR, MWR (XIRR), P&L decomposition, contribution and currency effect.

Hand values from docs/design/2.1-portfolio.md (toy portfolio, flows at start of day):

- period returns -0.001, 15,490/14,990 - 1, 15,290/15,490 - 1, 15,480/15,290 - 1;
  TWR = 11,863 / 374,750 = 3.16558 %
- XIRR of (-10,000 on 2026-01-02, -5,000 on 2026-01-30, +15,480 on 2026-03-31) = 15.7293 %
- P&L 480 = realised 185 + unrealised 195 + dividend 100
- currency example: local +10 %, EUR/USD 1.25 -> 1.20: FX +4.1667 %, base +14.5833 %,
  FX effect (local first) 4.5833 %
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.portfolio.performance import (
    FlowTiming,
    contribution_by_position,
    currency_effect,
    external_flows_by_date,
    money_weighted_return,
    pnl_breakdown,
    time_weighted_returns,
    xirr,
)
from qrlab.portfolio.transactions import TransactionKind
from support.portfolio import D0, D1, D2, D3, X, Y, eur_only, multi_currency_setup, toy_setup

K = TransactionKind


# --------------------------------------------------------------------------- TWR
def test_twr_hand_example_start_of_day() -> None:
    history, valuation = toy_setup()
    result = time_weighted_returns(
        valuation, external_flows_by_date(history), flow_timing=FlowTiming.START_OF_DAY
    )
    expected = [
        Fraction(9990, 10000) - 1,
        Fraction(15490, 14990) - 1,
        Fraction(15290, 15490) - 1,
        Fraction(15480, 15290) - 1,
    ]
    assert result.returns.name == "TWR"
    assert result.returns.tolist() == pytest.approx([float(e) for e in expected], abs=1e-15)
    total = math.prod(1 + float(e) for e in expected) - 1
    assert result.total == pytest.approx(float(Fraction(11863, 374750)), abs=1e-14)
    assert result.total == pytest.approx(total, abs=1e-14)
    assert result.skipped == ()


def test_twr_end_of_day_skips_zero_starting_capital() -> None:
    history, valuation = toy_setup()
    result = time_weighted_returns(
        valuation, external_flows_by_date(history), flow_timing=FlowTiming.END_OF_DAY
    )
    assert result.skipped == (D0,)  # no capital before the first end-of-day flow
    assert result.returns.iloc[0] == pytest.approx((15490 - 5000) / 9990 - 1)


def test_twr_flows_must_fall_on_valuation_dates() -> None:
    history, valuation = toy_setup()
    flows = {**external_flows_by_date(history), date(2026, 1, 15): Decimal(1)}
    with pytest.raises(ValidationError, match="valuation date"):
        time_weighted_returns(valuation, flows, flow_timing=FlowTiming.START_OF_DAY)


def test_twr_needs_flow_timing_enum() -> None:
    history, valuation = toy_setup()
    with pytest.raises(ValidationError, match="FlowTiming"):
        time_weighted_returns(valuation, external_flows_by_date(history), flow_timing="start")  # type: ignore[arg-type]


def test_twr_equals_simple_return_without_flows() -> None:
    history, valuation = toy_setup()
    # from D1 on there are no flows: TWR over D2..D3 equals V_D3 / V_D1 - 1
    flows = {d: f for d, f in external_flows_by_date(history).items() if d > D1}
    sub = type(valuation)(
        valuation.base, {d: v for d, v in valuation.totals.items() if d >= D1}, {}, {}, ()
    )
    result = time_weighted_returns(sub, flows, flow_timing=FlowTiming.START_OF_DAY)
    assert result.skipped == (D1,)  # first date: no previous value inside this window
    assert result.total == pytest.approx(15480 / 15490 - 1, abs=1e-15)


# --------------------------------------------------------------------------- XIRR / MWR
def test_xirr_closed_form() -> None:
    result = xirr([(date(2025, 1, 2), Decimal(-10000)), (date(2026, 1, 2), Decimal(11000))])
    assert result.rate == pytest.approx(0.10, abs=1e-12)
    assert result.sign_changes == 1


def test_mwr_hand_example() -> None:
    history, valuation = toy_setup()
    result = money_weighted_return(history, valuation, end=D3)
    assert result.rate == pytest.approx(0.15729318, abs=1e-8)
    assert result.label == "MWR (XIRR, ACT/365)"


def test_xirr_matches_independent_bisection() -> None:
    flows = [(date(2026, 1, 2), -10000), (date(2026, 1, 30), -5000), (date(2026, 3, 31), 15480)]

    def npv(r: float) -> float:
        return float(sum(a / (1 + r) ** ((d - flows[0][0]).days / 365) for d, a in flows))

    lo, hi = -0.99, 10.0
    for _ in range(300):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if npv(lo) * npv(mid) <= 0 else (mid, hi)
    assert xirr([(d, Decimal(a)) for d, a in flows]).rate == pytest.approx((lo + hi) / 2, abs=1e-10)


@pytest.mark.parametrize(
    "flows",
    [
        [(D0, Decimal(-1)), (D1, Decimal(-2))],
        [(D0, Decimal(1)), (D1, Decimal(2))],
        [(D0, Decimal(0))],
        [],
    ],
)
def test_xirr_undefined_without_both_signs(flows: list[tuple[date, Decimal]]) -> None:
    with pytest.raises(UndefinedMetricError):
        xirr(flows)


def test_xirr_reports_several_sign_changes() -> None:
    # 365-day spacing (2021 and 2022 are not leap years), so ACT/365 gives whole years:
    # -100 + 230 / x - 132 / x^2 = 0 with x = 1 + r has roots x = 1.1 and x = 1.2
    flows = [
        (date(2021, 1, 1), Decimal(-100)),
        (date(2022, 1, 1), Decimal(230)),
        (date(2023, 1, 1), Decimal(-132)),
    ]
    result = xirr(flows)
    assert result.sign_changes == 2
    assert not result.unique_root_guaranteed
    assert result.candidates == pytest.approx((0.1, 0.2), abs=1e-6)
    assert result.rate == pytest.approx(0.1, abs=1e-6)


def test_mwr_end_must_be_a_valuation_date() -> None:
    history, valuation = toy_setup()
    with pytest.raises(ValidationError, match="valuation date"):
        money_weighted_return(history, valuation, end=date(2026, 3, 30))


# --------------------------------------------------------------------------- P&L
def test_pnl_breakdown_toy_reconciles_exactly() -> None:
    history, valuation = toy_setup()
    pnl = pnl_breakdown(history, valuation, eur_only, start=None, end=D3)
    assert pnl.total == Decimal(480)
    assert pnl.realised == Decimal(185)
    assert pnl.unrealised_change == Decimal(195)
    assert pnl.income == Decimal(100)
    assert pnl.costs == Decimal(0)
    assert pnl.cash_fx == Decimal(0)
    assert pnl.residual == Decimal(0)


def test_pnl_breakdown_sub_period() -> None:
    history, valuation = toy_setup()
    pnl = pnl_breakdown(history, valuation, eur_only, start=D1, end=D3)
    # V 15,490 -> 15,480 with no flows: -10 = realised 185 + unrealised (195 - 490) + income 100
    assert pnl.total == Decimal(-10)
    assert pnl.unrealised_change == Decimal(-295)
    assert pnl.residual == Decimal(0)


def test_pnl_breakdown_multi_currency_hand_example() -> None:
    # D3: EUR 5,000 + Y 6,000 USD / 1.6 = 3,750 + USD 1,250 / 1.6 = 781.25 -> 9,531.25
    # total -468.75 = unrealised (3,750 - 4,000) + cash FX effect 1,250 x (1/1.6 - 1/1.25)
    history, valuation, convert = multi_currency_setup()
    assert valuation.totals[D3] == Decimal("9531.25")
    pnl = pnl_breakdown(history, valuation, convert, start=None, end=D3)
    assert pnl.total == Decimal("-468.75")
    assert pnl.unrealised_change == Decimal(-250)
    assert pnl.cash_fx == Decimal("-218.75")
    assert pnl.residual == Decimal(0)


def test_pnl_breakdown_dates_must_be_valuation_dates() -> None:
    history, valuation = toy_setup()
    with pytest.raises(ValidationError, match="valuation date"):
        pnl_breakdown(history, valuation, eur_only, start=date(2026, 1, 3), end=D3)
    with pytest.raises(ValidationError, match="before"):
        pnl_breakdown(history, valuation, eur_only, start=D3, end=D1)


# --------------------------------------------------------------------------- contribution
def test_contribution_by_position_sums_to_total() -> None:
    history, valuation = toy_setup()
    contributions = contribution_by_position(history, valuation, eur_only, start=None, end=D3)
    assert contributions == {("main", X): Decimal(480)}  # 185 + 195 + dividend 100
    pnl = pnl_breakdown(history, valuation, eur_only, start=None, end=D3)
    other = pnl.total - sum(contributions.values(), Decimal(0))
    assert other == Decimal(0)


def test_contribution_multi_currency_excludes_cash_fx() -> None:
    history, valuation, convert = multi_currency_setup()
    contributions = contribution_by_position(history, valuation, convert, start=None, end=D3)
    assert contributions == {("main", Y): Decimal(-250)}


# --------------------------------------------------------------------------- currency effect
def test_currency_effect_hand_example() -> None:
    effect = currency_effect(local_return=0.10, fx_return=1.25 / 1.20 - 1)
    assert effect.fx_return == pytest.approx(0.0416666667, abs=1e-10)
    assert effect.base_return == pytest.approx(0.1458333333, abs=1e-10)
    assert effect.fx_effect == pytest.approx(0.0458333333, abs=1e-10)
    assert effect.local_return + effect.fx_effect == pytest.approx(effect.base_return)


@pytest.mark.parametrize("bad", [-1.0, -1.5, math.nan, math.inf])
def test_currency_effect_validation(bad: float) -> None:
    with pytest.raises(ValidationError):
        currency_effect(local_return=bad, fx_return=0.0)


def test_money_type_used_for_flows() -> None:
    history, _ = toy_setup()
    assert external_flows_by_date(history) == {D0: Decimal(10000), D1: Decimal(5000)}
    assert isinstance(Money.of(1, "EUR"), Money)


def test_xirr_zero_rate_is_found_exactly() -> None:
    result = xirr([(D0, Decimal(-100)), (D3, Decimal(100))])
    assert result.rate == 0.0


def test_xirr_beyond_the_search_range_is_undefined() -> None:
    with pytest.raises(UndefinedMetricError, match="no rate"):
        xirr([(D0, Decimal(-1)), (date(2026, 1, 3), Decimal(10**12))])


def test_contribution_sub_period() -> None:
    history, valuation = toy_setup()
    # D2..D3: realised 185 on D3; unrealised 195 - (100 x 52 - 5,010 = 190); dividend on D2 excluded
    contributions = contribution_by_position(history, valuation, eur_only, start=D2, end=D3)
    assert contributions == {("main", X): Decimal(190)}


def test_pnl_breakdown_multi_currency_from_a_valuation_date() -> None:
    history, valuation, convert = multi_currency_setup()
    pnl = pnl_breakdown(history, valuation, convert, start=D0, end=D3)
    assert pnl.total == Decimal("-468.75")  # 9,531.25 - 10,000, no flows after D0
    assert pnl.cash_fx == Decimal("-218.75")  # USD 1,250 held over the period
    assert pnl.residual == Decimal(0)


def test_contribution_excludes_sales_before_the_period() -> None:
    history, valuation = toy_setup()
    # the only sale is on D3, outside (D0, D2]; D0..D2: unrealised 190 - (-10) and dividend 100
    contributions = contribution_by_position(history, valuation, eur_only, start=D0, end=D2)
    assert contributions == {("main", X): Decimal(300)}
