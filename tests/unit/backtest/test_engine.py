"""The backtest engine on a hand-checked three-asset toy (design note 4.3).

Returns of A, B, C: period 1 (+10 %, 0, -5 %), 2 (-5 %, +5 %, 0), 3 (0, 0, +10 %),
4 (+5 %, -5 %, 0); start 300 at 1/3 each.

- buy and hold: 305, 304.5, 314, 313.975 (+4.6583 %);
- rebalance to 1/3 every close, no costs: 305, 305, 315.1667, 315.1667;
- the same on three periods with 0.10 % costs: net 304.9833, 304.9732, 315.1254; costs 0.040387;
- a signal at the close of 1 going all into C, lag 1: trades at the close of 2, +11.65 %.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from qrlab.backtest import TradeOnSignal, run_backtest, run_backtest_targets
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.optimization import CalendarPolicy, CostModel, ThresholdPolicy
from qrlab.simulation import TaxModel

INDEX = pd.date_range("2020-01-31", periods=4, freq="ME")
TOY = pd.DataFrame(
    [[0.10, 0.0, -0.05], [-0.05, 0.05, 0.0], [0.0, 0.0, 0.10], [0.05, -0.05, 0.0]],
    index=INDEX,
    columns=["A", "B", "C"],
)
THIRD = pd.Series(1 / 3, index=["A", "B", "C"])
FREE = CostModel(0.0, 0.0)
VALUE = Money.of("300", "EUR")
ALL_C = pd.Series({"A": 0.0, "B": 0.0, "C": 1.0})


def _never(history: pd.DataFrame) -> pd.Series | None:
    return None


def _run(strategy=_never, returns: pd.DataFrame = TOY, **changes: object):  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = {
        "decide_every": 1,
        "execution_lag": 1,
        "policy": TradeOnSignal(),
        "costs": FREE,
        "taxes": None,
        "initial_weights": THIRD,
        "initial_value": VALUE,
        "long_only": True,
    }
    kwargs.update(changes)
    return run_backtest(returns, strategy, **kwargs)  # type: ignore[arg-type]


def test_buy_and_hold_hand_example() -> None:
    result = _run()
    assert result.net_values.to_list() == pytest.approx([300, 305, 304.5, 314, 313.975])
    assert result.gross_values.to_list() == result.net_values.to_list()
    assert result.executions == ()
    assert result.net_returns.iloc[0] == pytest.approx(305 / 300 - 1)
    assert result.weights.iloc[0].to_list() == pytest.approx([110 / 305, 100 / 305, 95 / 305])
    assert result.currency == "EUR"


def test_rebalancing_every_close_hand_example() -> None:
    result = _run(policy=CalendarPolicy(1))
    assert result.net_values.iloc[1:].to_list() == pytest.approx(
        [305, 305, 315.16667, 315.16667], abs=1e-4
    )
    assert len(result.executions) == 4
    assert result.settings["policy"] == "calendar every 1 periods"


def test_costs_hit_the_net_ledger_only() -> None:
    result = _run(returns=TOY.iloc[:3], policy=CalendarPolicy(1), costs=CostModel(0.001, 0.0))
    assert result.net_values.iloc[1:].to_list() == pytest.approx(
        [304.98333, 304.97317, 315.12539], abs=1e-4
    )
    assert result.costs_paid == pytest.approx(0.0403871, abs=1e-6)
    assert result.gross_values.iloc[1:].to_list() == pytest.approx([305, 305, 315.16667], abs=1e-4)
    assert result.taxes_paid == 0.0


def test_lag_hand_example_and_precomputed_targets() -> None:
    def all_in_c_after_period_1(history: pd.DataFrame) -> pd.Series | None:
        return ALL_C if len(history) == 1 else None

    result = _run(all_in_c_after_period_1)
    assert result.net_values.iloc[-1] / 300 - 1 == pytest.approx(0.1165)
    (trade,) = result.executions
    assert (trade.decided, trade.executed) == (INDEX[0].date(), INDEX[1].date())
    targets = pd.DataFrame([ALL_C], index=INDEX[:1])
    precomputed = run_backtest_targets(
        TOY,
        targets,
        execution_lag=1,
        policy=TradeOnSignal(),
        costs=FREE,
        taxes=None,
        initial_weights=THIRD,
        initial_value=VALUE,
        long_only=True,
    )
    assert precomputed.net_values.to_list() == pytest.approx(result.net_values.to_list())
    assert precomputed.settings["targets"] == "precomputed"
    assert result.settings["targets"] == "strategy"
    slower = _run(all_in_c_after_period_1, execution_lag=2)
    assert slower.net_values.iloc[-1] != pytest.approx(result.net_values.iloc[-1])


def test_lag_zero_is_refused() -> None:
    with pytest.raises(ValidationError, match="execution_lag"):
        _run(execution_lag=0)


def test_strategy_cannot_see_the_future() -> None:
    def peeks(history: pd.DataFrame) -> pd.Series | None:
        _ = history.iloc[len(history)]  # the next period does not exist in the copy
        return None

    with pytest.raises(IndexError):
        _run(peeks)

    seen: list[int] = []

    def records(history: pd.DataFrame) -> pd.Series | None:
        seen.append(len(history))
        history.iloc[:, :] = 0.0  # mutating the copy must not change the backtest
        return None

    result = _run(records)
    assert seen == [1, 2, 3, 4]
    assert result.net_values.iloc[-1] == pytest.approx(313.975)


def test_a_leaked_signal_gives_a_different_result(rng: np.random.Generator) -> None:
    index = pd.date_range("2015-01-31", periods=120, freq="ME")
    data = pd.DataFrame(
        rng.normal(0.005, 0.04, size=(120, 3)), index=index, columns=["A", "B", "C"]
    )

    def honest(history: pd.DataFrame) -> pd.Series:
        best = history.iloc[-1].idxmax()  # last period's winner
        return pd.Series({c: float(c == best) for c in history.columns})

    def leaky(history: pd.DataFrame) -> pd.Series:
        t = len(history)
        nxt = data.iloc[min(t + 1, len(data) - 1)]  # captured full frame: peeks at r_{t+2}
        best = nxt.idxmax()
        return pd.Series({c: float(c == best) for c in history.columns})

    fair = _run(honest, returns=data, initial_weights=pd.Series(1 / 3, index=data.columns))
    cheat = _run(leaky, returns=data, initial_weights=pd.Series(1 / 3, index=data.columns))
    assert cheat.net_values.iloc[-1] > 5 * fair.net_values.iloc[-1]


def test_capital_gains_tax_on_rebalancing_sales() -> None:
    index = pd.date_range("2020-01-31", periods=2, freq="ME")
    returns = pd.DataFrame([[0.0, 0.0], [1.0, 0.0]], index=index, columns=["A", "B"])
    target = pd.Series({"A": 0.6, "B": 0.4})

    def decide(history: pd.DataFrame) -> pd.Series | None:
        return target if len(history) == 1 else None

    result = run_backtest(
        returns,
        decide,
        decide_every=1,
        execution_lag=1,
        policy=TradeOnSignal(),
        costs=FREE,
        taxes=TaxModel(0.26, 0.0),
        initial_weights=pd.Series({"A": 0.5, "B": 0.5}),
        initial_value=Money.of("200", "EUR"),
        long_only=True,
    )
    # A grows 100 -> 200; selling 20 of it (10 % of the position) realises a gain of 10
    assert result.taxes_paid == pytest.approx(2.6)
    assert result.net_values.iloc[-1] == pytest.approx(300 - 2.6)
    assert result.gross_values.iloc[-1] == pytest.approx(300)
    assert result.weights.iloc[-1].to_list() == pytest.approx([0.6, 0.4])


def test_threshold_policy_trades_only_outside_the_band() -> None:
    index = pd.date_range("2020-01-31", periods=3, freq="ME")
    returns = pd.DataFrame([[0.02, 0.0], [0.30, 0.0], [0.0, 0.0]], index=index, columns=["E", "B"])
    result = run_backtest(
        returns,
        _never,
        decide_every=1,
        execution_lag=1,
        policy=ThresholdPolicy(0.05, "target"),
        costs=FREE,
        taxes=None,
        initial_weights=pd.Series({"E": 0.6, "B": 0.4}),
        initial_value=VALUE,
        long_only=True,
    )
    assert [e.executed for e in result.executions] == [index[1].date()]
    assert result.executions[0].decided is None
    assert result.weights.iloc[1].to_list() == pytest.approx([0.6, 0.4])


def test_late_decisions_are_reported_not_executed() -> None:
    def last(history: pd.DataFrame) -> pd.Series | None:
        return ALL_C if len(history) == 4 else None

    result = _run(last)
    assert result.not_executed == (INDEX[3].date(),)
    assert result.executions == ()


def test_input_validation() -> None:
    bad_returns = TOY.copy()
    bad_returns.iloc[0, 0] = np.nan
    with pytest.raises(ValidationError):
        _run(returns=bad_returns)
    crash = TOY.copy()
    crash.iloc[0, 0] = -1.0
    with pytest.raises(ValidationError, match="above -1"):
        _run(returns=crash)
    with pytest.raises(ValidationError, match="decide_every"):
        _run(decide_every=0)
    with pytest.raises(ValidationError, match="policy"):
        _run(policy="monthly")
    with pytest.raises(ValidationError, match="initial_value"):
        _run(initial_value=Money.of("0", "EUR"))
    for weights, match in (
        (pd.Series({"A": 1.0}), "cover exactly"),
        (pd.Series({"A": 0.5, "B": 0.5, "C": 0.5}), "sum to 1"),
        (pd.Series({"A": 1.5, "B": -0.5, "C": 0.0}), "negative"),
        (pd.Series({"A": np.nan, "B": 0.5, "C": 0.5}), "finite"),
        ([1 / 3] * 3, "pandas Series"),
    ):
        with pytest.raises(ValidationError, match=match):
            _run(initial_weights=weights)
    with pytest.raises(ValidationError, match="decision 2020-01-31"):
        _run(lambda h: pd.Series({"A": 2.0, "B": -1.0, "C": 0.0}))
    with pytest.raises(ValidationError, match="target dates"):
        run_backtest_targets(
            TOY,
            pd.DataFrame([ALL_C], index=[pd.Timestamp("2019-01-01")]),
            execution_lag=1,
            policy=TradeOnSignal(),
            costs=FREE,
            taxes=None,
            initial_weights=THIRD,
            initial_value=VALUE,
            long_only=True,
        )
    long_short = _run(initial_weights=pd.Series({"A": 1.5, "B": -0.5, "C": 0.0}), long_only=False)
    assert long_short.net_values.iloc[1] == pytest.approx(300 * (1.5 * 1.1 - 0.5))


def test_single_period() -> None:
    result = _run(returns=TOY.iloc[:1])
    assert result.net_values.to_list() == pytest.approx([300, 305])
    assert result.net_values.index[0] == pd.Timestamp("2020-01-30")
    assert date(2020, 1, 31) == result.weights.index[0].date()


def test_decision_schedule_and_empty_returns() -> None:
    seen: list[int] = []

    def every_other(history: pd.DataFrame) -> pd.Series | None:
        seen.append(len(history))
        return None

    result = _run(every_other, decide_every=2)
    assert seen == [2, 4]
    assert result.settings["decide_every"] == 2.0
    with pytest.raises(ValidationError, match="at least one period"):
        _run(returns=TOY.iloc[:0])
