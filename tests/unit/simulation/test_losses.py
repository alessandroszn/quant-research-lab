"""Italian-style capital losses in projections and backtests (design 8.6b), by hand.

The design note's case, at 26 %, with losses usable for four years after the year they are
realised:

- year 1: a share is sold at a loss of 1,000: no tax, 1,000 carried;
- year 2: a fund gain of 600 and a share gain of 600: the fund's gain is capital income, taxed
  in full (156); the share's 600 uses 600 of the loss (tax 0); 400 is carried;
- year 6: the 400 from year 1 has expired (usable in years 1-5): a share gain of 400 pays 104.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.backtest import BacktestResult, run_backtest_targets
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.optimization import CalendarPolicy, CostModel
from qrlab.simulation import Flow, LossRules, Plan, SimulatedReturns, TaxModel, project
from qrlab.simulation.losses import LossBalance, realised_tax

TAU = 0.26
FUND_FIRST = np.array([True, False])  # assets: fund, share
RULES = LossRules(carry_years=4, fund_assets=frozenset({"fund"}))
ALL_FUNDS = LossRules(carry_years=4, fund_assets=frozenset({"fund", "share"}))


# --------------------------------------------------------------------------- the rule itself
def test_the_notes_case_by_hand() -> None:
    balance = LossBalance(paths=1, years=7, carry_years=4)

    def tax(fund: float, share: float, year: int) -> float:
        return float(realised_tax(np.array([[fund, share]]), TAU, FUND_FIRST, balance, year)[0])

    assert tax(0.0, -1000.0, 1) == 0.0
    assert balance.available(1)[0] == pytest.approx(1000.0)
    assert tax(600.0, 600.0, 2) == pytest.approx(156.0)
    assert balance.available(2)[0] == pytest.approx(400.0)
    assert balance.available(5)[0] == pytest.approx(400.0)  # the last year it can be used
    assert balance.available(6)[0] == 0.0
    assert tax(0.0, 400.0, 6) == pytest.approx(104.0)


def test_fund_losses_join_the_balance_but_fund_gains_never_use_it() -> None:
    balance = LossBalance(paths=1, years=3, carry_years=4)
    assert realised_tax(np.array([[-500.0, 0.0]]), TAU, FUND_FIRST, balance, 0)[0] == 0.0
    assert balance.available(0)[0] == 500.0
    assert realised_tax(np.array([[500.0, 0.0]]), TAU, FUND_FIRST, balance, 1)[0] == pytest.approx(
        130.0
    )
    assert balance.available(1)[0] == 500.0
    assert realised_tax(np.array([[0.0, 300.0]]), TAU, FUND_FIRST, balance, 1)[0] == 0.0
    assert balance.available(1)[0] == pytest.approx(200.0)


def test_one_sale_nets_its_own_gains_and_losses_first() -> None:
    """A share gain of 300 and a loss of 100 in one sale: 200 taxable, nothing carried."""
    balance = LossBalance(paths=1, years=1, carry_years=4)
    gains = np.array([[0.0, 300.0, -100.0]])
    tax = realised_tax(gains, TAU, np.array([True, False, False]), balance, 0)
    assert tax[0] == pytest.approx(52.0)
    assert balance.available(0)[0] == 0.0


def test_rules_are_validated() -> None:
    with pytest.raises(ValidationError, match="carry_years"):
        LossRules(carry_years=-1, fund_assets=frozenset())
    with pytest.raises(ValidationError, match="fund_assets"):
        LossRules(carry_years=4, fund_assets={"fund"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="LossRules"):
        TaxModel(TAU, 0.0, losses="italy")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- projections
def _returns(rows: list[list[float]]) -> SimulatedReturns:
    return SimulatedReturns(np.array([rows], dtype=np.float64), ("fund", "share"), "fixed")


def _plan(
    taxes: TaxModel, flows: tuple[Flow, ...] = (), rebalance: int | None = 1, wealth: float = 2000.0
) -> Plan:
    return Plan(
        initial_wealth=wealth,
        currency=Currency("EUR"),
        weights=pd.Series([0.5, 0.5], index=["fund", "share"]),
        periods_per_year=1,
        flows=flows,
        flow_timing="end",
        rebalance_every=rebalance,
        annual_cost=0.0,
        inflation=0.0,
        taxes=taxes,
    )


def test_funds_only_projection_is_byte_identical(rng: np.random.Generator) -> None:
    """With only funds, losses can never be used: the rules change no number, bit for bit."""
    returns = SimulatedReturns(rng.normal(0.004, 0.08, (200, 30, 2)), ("fund", "share"), "rnd")
    flows = (Flow("contribution", 100.0, 0, 9, True), Flow("withdrawal", 400.0, 10, 29, True))
    plain = project(_plan(TaxModel(TAU, 0.002), flows, 3), returns)
    ruled = project(_plan(TaxModel(TAU, 0.002, losses=ALL_FUNDS), flows, 3), returns)
    assert (plain.depleted_period >= 0).any()  # some paths run out: that branch is compared too
    for name in ("nominal", "taxes_paid", "liquidation_value", "shortfall", "depleted_period"):
        assert np.array_equal(getattr(plain, name), getattr(ruled, name)), name


def test_rebalancing_carries_a_share_loss_by_hand() -> None:
    """Year 0: fund -30 % (700), share -10 % (900 on a basis of 1,000); target 800 each.

    1/9 of the share is sold at a loss of (900 - 1,000)/9 = -11.111; 100 of fund is bought.
    Year 1: fund 0 % (800), share +50 % (1,200 on a basis of 8,000/9). Rebalancing sells 1/6
    of the share: a gain of (1,200 - 888.89)/6 = 51.852. Without the rules the tax is
    26 % x 51.852 = 13.481; with them the 11.111 is used first: 26 % x 40.741 = 10.593.
    """
    rows = [[-0.30, -0.10], [0.0, 0.50]]
    gain = (1200.0 - 8000.0 / 9.0) / 6.0
    plain = project(_plan(TaxModel(TAU, 0.0)), _returns(rows))
    ruled = project(_plan(TaxModel(TAU, 0.0, losses=RULES)), _returns(rows))
    assert plain.taxes_paid[0] == pytest.approx(TAU * gain)
    assert ruled.taxes_paid[0] == pytest.approx(TAU * (gain - 100.0 / 9.0))


def test_a_withdrawal_beyond_the_carried_losses_by_hand() -> None:
    """Year 0 withdraws 160 net at a loss; year 1 withdraws 300 net at a gain.

    Year 0: fund 700 and share 900, both on a basis of 1,000 (W = 1,600). Nothing is taxed, so
    160 is sold: 10 % of each, losses 30 + 10 = 40 carried. Left: fund 630, share 810, each on
    a basis of 900.
    Year 1: both +50 %: fund 945 (gain F = 45), share 1,215 (gain D = 315), W = 2,160,
    C = 40. Without offset S = 300 / (1 - 26 % x 45 / 2,160) = 301.63 would realise
    301.63/2,160 x 315 = 43.99 > 40 of share gain, so the closed form with the offset applies:
    S = W (N - tau C) / (W - tau (F + D)) = 2,160 x 289.6 / 2,066.4 = 302.718.
    Its tax tau (sF + sD - C) = 2.718, and S - tax = 300 exactly.
    """
    rows = [[-0.30, -0.10], [0.50, 0.50]]
    flows = (Flow("withdrawal", 160.0, 0, 0, False), Flow("withdrawal", 300.0, 1, 1, False))
    ruled = project(_plan(TaxModel(TAU, 0.0, losses=RULES), flows, None), _returns(rows))
    gross = 2160.0 * (300.0 - TAU * 40.0) / (2160.0 - TAU * 360.0)
    share = gross / 2160.0
    assert TAU * (share * 45.0 + share * 315.0 - 40.0) == pytest.approx(gross - 300.0)
    assert ruled.taxes_paid[0] == pytest.approx(gross - 300.0)
    assert ruled.nominal[0, 2] == pytest.approx(2160.0 - gross)
    plain = project(_plan(TaxModel(TAU, 0.0), flows, None), _returns(rows))
    assert plain.taxes_paid[0] == pytest.approx(300.0 / (1.0 - TAU * 360.0 / 2160.0) - 300.0)
    # The liquidation value uses what is left of the balance (nothing here) the same way.
    assert ruled.liquidation_value[0] == pytest.approx(
        ruled.nominal[0, 2] - TAU * 360.0 * (1.0 - share)
    )


def test_running_out_pays_what_is_left_net_of_tax() -> None:
    """Share 1,500 on a basis of 1,000 and fund 1,000: selling all pays 26 % x 500 = 130."""
    flows = (Flow("withdrawal", 5000.0, 0, 0, False),)
    out = project(_plan(TaxModel(TAU, 0.0, losses=RULES), flows, None), _returns([[0.0, 0.5]]))
    assert out.depleted_period[0] == 0
    assert out.taxes_paid[0] == pytest.approx(130.0)
    assert out.shortfall[0] == pytest.approx(5000.0 - (2500.0 - 130.0))


def test_unknown_fund_assets_raise() -> None:
    rules = LossRules(carry_years=4, fund_assets=frozenset({"fnd"}))
    with pytest.raises(ValidationError, match="fnd"):
        project(_plan(TaxModel(TAU, 0.0, losses=rules)), _returns([[0.0, 0.0]]))


# --------------------------------------------------------------------------- backtests
def _backtest(taxes: TaxModel) -> BacktestResult:
    """Run the projection's rebalancing case on calendar years 2024 and 2025."""
    dates = pd.to_datetime(["2024-12-31", "2025-12-31", "2026-12-31"])
    returns = pd.DataFrame({"fund": [-0.30, 0.0, 0.0], "share": [-0.10, 0.50, 0.0]}, index=dates)
    targets = pd.DataFrame({"fund": [0.5], "share": [0.5]}, index=dates[:1])
    return run_backtest_targets(
        returns,
        targets,
        execution_lag=1,
        policy=CalendarPolicy(1),
        costs=CostModel(0.0, 0.0),
        taxes=taxes,
        initial_weights=pd.Series({"fund": 0.5, "share": 0.5}),
        initial_value=Money.of("2000", "EUR"),
        long_only=True,
    )


def test_backtest_carries_the_share_loss_by_hand() -> None:
    gain = (1200.0 - 8000.0 / 9.0) / 6.0
    assert _backtest(TaxModel(TAU, 0.0)).taxes_paid == pytest.approx(TAU * gain)
    ruled = _backtest(TaxModel(TAU, 0.0, losses=RULES))
    assert ruled.taxes_paid == pytest.approx(TAU * (gain - 100.0 / 9.0))


def test_backtest_funds_only_is_byte_identical() -> None:
    plain = _backtest(TaxModel(TAU, 0.0))
    ruled = _backtest(TaxModel(TAU, 0.0, losses=ALL_FUNDS))
    assert plain.net_values.equals(ruled.net_values)
    assert plain.taxes_paid == ruled.taxes_paid


def test_backtest_unknown_fund_assets_raise() -> None:
    with pytest.raises(ValidationError, match="fnd"):
        _backtest(TaxModel(TAU, 0.0, losses=LossRules(4, frozenset({"fnd"}))))
