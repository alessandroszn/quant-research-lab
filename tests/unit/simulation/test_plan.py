"""Savings and withdrawal plans on deterministic returns (hand values, design note 3.3).

- contribution 100 at the start of 12 months, 1 % a month: 100 x sum 1.01^k = 1,280.93;
- costs 1 % a year charged monthly, zero return, 12 months: (1 - 0.01/12)^12 = 0.990046;
- wealth 15,000 with basis 10,000, tax 26 %, net withdrawal 1,000: gross 1,094.89, tax 94.89,
  basis reduced by 729.93; liquidating 15,000 nets 13,700;
- zero return, 2,500 and a net withdrawal of 1,000 a period: depleted in period 2 (0-based;
  the third period) with shortfall 500;
- 50/50, A +20 %, B 0 %: weights 54.55 % / 45.45 % before rebalancing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.simulation import MAX_CELLS, LogMoments, normal_returns
from qrlab.simulation.engines import SimulatedReturns
from qrlab.simulation.plan import Flow, Plan, TaxModel, project

EUR = Currency("EUR")
NO_TAX = TaxModel(0.0, 0.0)


def _returns(per_period: list[list[float]] | np.ndarray, paths: int = 1) -> SimulatedReturns:
    values = np.asarray(per_period, dtype=np.float64)  # periods x assets
    assets = tuple(f"a{i}" for i in range(values.shape[1]))
    return SimulatedReturns(np.broadcast_to(values, (paths, *values.shape)).copy(), assets, "fixed")


def _plan(weights: list[float], **changes: object) -> Plan:
    fields: dict[str, object] = {
        "initial_wealth": 0.0,
        "currency": EUR,
        "weights": pd.Series(weights, index=[f"a{i}" for i in range(len(weights))]),
        "periods_per_year": 12,
        "flows": (),
        "flow_timing": "start",
        "rebalance_every": None,
        "annual_cost": 0.0,
        "inflation": 0.0,
        "taxes": NO_TAX,
    }
    fields.update(changes)
    return Plan(**fields)  # type: ignore[arg-type]


def test_monthly_contributions_hand_example() -> None:
    plan = _plan([1.0], flows=(Flow("contribution", 100.0, 0, 11, False),))
    result = project(plan, _returns([[0.01]] * 12))
    assert result.nominal[0, -1] == pytest.approx(1280.9328, abs=1e-4)
    assert result.nominal[0, 0] == 0.0
    end = project(_plan([1.0], flows=plan.flows, flow_timing="end"), _returns([[0.01]] * 12))
    assert end.nominal[0, -1] == pytest.approx(1280.9328 / 1.01, abs=1e-4)


def test_costs_hand_example() -> None:
    result = project(_plan([1.0], initial_wealth=1000.0, annual_cost=0.01), _returns([[0.0]] * 12))
    assert result.nominal[0, -1] == pytest.approx(1000 * 0.990046, abs=1e-3)


def test_inflation_indexes_flows_and_deflates_wealth() -> None:
    plan = _plan([1.0], flows=(Flow("contribution", 100.0, 0, 11, True),), inflation=0.02)
    result = project(plan, _returns([[0.0]] * 12))
    expected = sum(100 * 1.02 ** (t / 12) for t in range(12))
    assert result.nominal[0, -1] == pytest.approx(expected)
    assert result.real[0, -1] == pytest.approx(expected / 1.02)
    assert result.real[0, 0] == result.nominal[0, 0]


def test_withdrawal_tax_hand_example() -> None:
    # 10,000 invested, +50 % in period 0, net withdrawal 1,000 at the end of period 0
    plan = _plan(
        [1.0],
        initial_wealth=10_000.0,
        flow_timing="end",
        flows=(Flow("withdrawal", 1000.0, 0, 0, False),),
        taxes=TaxModel(0.26, 0.0),
    )
    result = project(plan, _returns([[0.5], [0.0]]))
    assert result.nominal[0, 1] == pytest.approx(15_000 - 1094.8905, abs=1e-3)
    assert result.taxes_paid[0] == pytest.approx(94.8905, abs=1e-4)
    basis = 10_000 - 729.9270
    gain = result.nominal[0, -1] - basis
    assert result.liquidation_value[0] == pytest.approx(result.nominal[0, -1] - 0.26 * gain)
    full = project(
        _plan([1.0], initial_wealth=10_000.0, taxes=TaxModel(0.26, 0.0)), _returns([[0.5]])
    )
    assert full.liquidation_value[0] == pytest.approx(13_700.0)


def test_wealth_tax_is_charged_pro_rata() -> None:
    plan = _plan([1.0], initial_wealth=10_000.0, taxes=TaxModel(0.0, 0.002))
    result = project(plan, _returns([[0.0]] * 12))
    assert result.nominal[0, -1] == pytest.approx(10_000 * (1 - 0.002 / 12) ** 12)
    assert result.taxes_paid[0] == pytest.approx(10_000 - result.nominal[0, -1])


def test_depletion_hand_example() -> None:
    plan = _plan(
        [1.0],
        initial_wealth=2500.0,
        flow_timing="end",
        flows=(Flow("withdrawal", 1000.0, 0, 4, False), Flow("contribution", 50.0, 3, 4, False)),
    )
    result = project(plan, _returns([[0.0]] * 5))
    assert result.nominal[0].tolist() == pytest.approx([2500, 1500, 500, 0, 0, 0])
    assert result.depleted_period[0] == 2
    assert result.shortfall[0] == pytest.approx(500)  # later flows are ignored once depleted
    never = project(_plan([1.0], initial_wealth=5000.0), _returns([[0.0]] * 5))
    assert never.depleted_period[0] == -1


def test_withdrawal_from_nothing_depletes_at_once() -> None:
    plan = _plan([1.0], flows=(Flow("withdrawal", 10.0, 0, 0, False),))
    result = project(plan, _returns([[0.0]]))
    assert (result.depleted_period[0], result.shortfall[0]) == (0, 10.0)


def test_rebalancing_hand_example() -> None:
    plan = _plan([0.5, 0.5], initial_wealth=1.0, rebalance_every=1, taxes=TaxModel(0.26, 0.0))
    result = project(plan, _returns([[0.2, 0.0]]))
    assert pytest.approx(0.5455, abs=1e-4) == 0.6 / 1.1
    # sell 0.05 of A whose gain share is 0.1/0.6: realised 0.05 x 1/6, tax 26 % of it
    tax = 0.26 * 0.05 / 6
    assert result.taxes_paid[0] == pytest.approx(tax)
    assert result.nominal[0, -1] == pytest.approx(1.1 - tax)
    buy_and_hold = project(
        _plan([0.5, 0.5], initial_wealth=1.0), _returns([[0.2, 0.0], [0.2, 0.0]])
    )
    assert buy_and_hold.nominal[0, -1] == pytest.approx(0.5 * 1.44 + 0.5)


def test_rebalancing_keeps_basis_for_the_liquidation_tax() -> None:
    plan = _plan([0.5, 0.5], initial_wealth=1.0, rebalance_every=1, taxes=TaxModel(0.26, 0.0))
    result = project(plan, _returns([[0.2, 0.0], [0.0, 0.0]]))
    no_tax = project(
        _plan([0.5, 0.5], initial_wealth=1.0, rebalance_every=1), _returns([[0.2, 0.0], [0.0, 0.0]])
    )
    assert result.liquidation_value[0] < no_tax.liquidation_value[0]
    assert no_tax.liquidation_value[0] == pytest.approx(1.1)


def test_paths_are_independent_and_depleted_paths_stay_at_zero() -> None:
    returns = SimulatedReturns(np.array([[[0.0], [0.0]], [[1.0], [1.0]]]), ("a0",), "fixed")
    plan = _plan(
        [1.0],
        initial_wealth=100.0,
        flow_timing="end",
        flows=(Flow("withdrawal", 150.0, 0, 1, False),),
    )
    result = project(plan, returns)
    assert result.depleted_period.tolist() == [0, 1]  # 100 -> 200 - 150 = 50 -> 100 < 150
    assert result.nominal[0].tolist() == [100.0, 0.0, 0.0]
    assert result.nominal[1].tolist() == pytest.approx([100.0, 50.0, 0.0])
    assert result.shortfall.tolist() == pytest.approx([50.0, 50.0])


def test_projection_on_simulated_paths_is_reproducible() -> None:
    moments = LogMoments(
        pd.Series([0.004], index=["a0"]), pd.DataFrame([[0.0016]], index=["a0"], columns=["a0"]), 60
    )
    plan = _plan(
        [1.0],
        initial_wealth=1000.0,
        flows=(Flow("contribution", 100.0, 0, 119, True),),
        inflation=0.02,
    )
    runs = [
        project(
            plan,
            normal_returns(
                moments,
                n_paths=500,
                n_periods=120,
                rng=np.random.default_rng(1),
                max_cells=MAX_CELLS,
            ),
        )
        for _ in range(2)
    ]
    np.testing.assert_array_equal(runs[0].nominal, runs[1].nominal)
    assert runs[0].engine == "normal"


def test_plan_validation() -> None:
    bad: list[dict[str, object]] = [
        {"initial_wealth": -1.0},
        {"periods_per_year": 0},
        {"flow_timing": "middle"},
        {"rebalance_every": 0},
        {"annual_cost": 1.0},
        {"inflation": -1.0},
    ]
    for changes in bad:
        with pytest.raises(ValidationError):
            _plan([1.0], **changes)
    for weights in ([0.5, 0.4], [1.5, -0.5], [float("nan"), 1.0]):
        with pytest.raises(ValidationError, match="weights"):
            _plan(weights)
    for args in (
        ("gift", 1.0, 0, 0, False),
        ("contribution", 0.0, 0, 0, False),
        ("contribution", 1.0, -1, 0, False),
        ("contribution", 1.0, 2, 1, False),
        ("contribution", 1.0, 0, 0, 1),
    ):
        with pytest.raises(ValidationError):
            Flow(*args)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        TaxModel(1.0, 0.0)
    with pytest.raises(ValidationError, match="must match"):
        project(_plan([1.0]), _returns([[0.0, 0.0]]))
    with pytest.raises(ValidationError, match="after the horizon"):
        project(_plan([1.0], flows=(Flow("contribution", 1.0, 0, 5, False),)), _returns([[0.0]]))
