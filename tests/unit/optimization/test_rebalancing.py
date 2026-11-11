"""Rebalancing policies and trade costs (hand values from design note 4.2).

- band 5 %, target 60/40, drift to 66/34: rebalance; to="band" gives 65/35;
- every 12: trades at periods 12, 24, ..., never in between;
- 10,000 EUR from 60/40 to 50/50 with 0.10 % and a 2 EUR fixed fee: turnover 0.2, traded
  2,000, cost 2 + 2 x 2 = 6.
"""

from __future__ import annotations

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.optimization import CalendarPolicy, CostModel, ThresholdPolicy, trade

TARGET = pd.Series({"eq": 0.6, "bd": 0.4})


def test_threshold_policy_hand_example() -> None:
    drifted = pd.Series({"eq": 0.66, "bd": 0.34})
    policy = ThresholdPolicy(0.05, "band")
    assert policy.due(7, drifted, TARGET)
    assert policy.destination(drifted, TARGET).to_list() == pytest.approx([0.65, 0.35])
    assert ThresholdPolicy(0.05, "target").destination(drifted, TARGET).to_list() == [0.6, 0.4]
    assert not policy.due(7, pd.Series({"eq": 0.64, "bd": 0.36}), TARGET)


def test_band_edge_redistributes_the_residual() -> None:
    target = pd.Series({"a": 0.4, "b": 0.3, "c": 0.3})
    current = pd.Series({"a": 0.5, "b": 0.27, "c": 0.23})
    edge = ThresholdPolicy(0.05, "band").destination(current, target)
    assert edge.sum() == pytest.approx(1.0)
    assert edge["a"] == pytest.approx(0.45)
    assert edge["c"] == pytest.approx(0.25)
    assert edge["b"] == pytest.approx(0.30)  # the 0.03 residual goes to b, the only asset inside
    target2 = pd.Series({"a": 0.3, "b": 0.4, "c": 0.3})
    out = ThresholdPolicy(0.05, "band").destination(
        pd.Series({"a": 0.6, "b": 0.1, "c": 0.3}), target2
    )
    assert out.to_list() == pytest.approx([0.35, 0.35, 0.3])


def test_calendar_policy() -> None:
    policy = CalendarPolicy(12)
    due = [t for t in range(40) if policy.due(t, TARGET, TARGET)]
    assert due == [12, 24, 36]
    assert policy.destination(pd.Series({"eq": 0.7, "bd": 0.3}), TARGET).to_list() == [0.6, 0.4]


def test_trade_cost_hand_example() -> None:
    result = trade(TARGET, pd.Series({"eq": 0.5, "bd": 0.5}), 10_000.0, CostModel(0.001, 2.0))
    assert result.turnover == pytest.approx(0.2)
    assert result.traded == pytest.approx(2000.0)
    assert result.cost == pytest.approx(6.0)
    assert result.trades == 2
    assert result.amounts.to_list() == pytest.approx([-1000.0, 1000.0])
    nothing = trade(TARGET, TARGET, 10_000.0, CostModel(0.001, 2.0))
    assert (nothing.cost, nothing.trades) == (0.0, 0)


def test_validation() -> None:
    for kwargs in ({"every": 0},):
        with pytest.raises(ValidationError):
            CalendarPolicy(**kwargs)
    with pytest.raises(ValidationError, match="band"):
        ThresholdPolicy(0.0, "band")
    with pytest.raises(ValidationError, match="to must"):
        ThresholdPolicy(0.05, "edge")
    with pytest.raises(ValidationError, match="proportional"):
        CostModel(-0.1, 0.0)
    with pytest.raises(ValidationError, match="fixed"):
        CostModel(0.0, float("nan"))
    with pytest.raises(ValidationError, match="same assets"):
        trade(TARGET, pd.Series({"eq": 1.0}), 1.0, CostModel(0.0, 0.0))
    with pytest.raises(ValidationError, match="sum to 1"):
        ThresholdPolicy(0.05, "band").due(0, pd.Series({"eq": 0.5, "bd": 0.4}), TARGET)
    with pytest.raises(ValidationError, match="value"):
        trade(TARGET, TARGET, -1.0, CostModel(0.0, 0.0))
