"""Brinson-Fachler attribution (hand values from design note 4.4).

Segments equity, bonds, cash; w_p (0.6, 0.3, 0.1), w_b (0.5, 0.4, 0.1); r_p (12 %, 3 %, 1 %),
r_b (10 %, 4 %, 1 %): R_p 8.2 %, R_b 6.7 %, active 1.5 % = allocation 0.60 % (0.33 + 0.27)
+ selection 0.60 % (1.00 - 0.40) + interaction 0.30 % (0.20 + 0.10). Two periods with
R_p (8.2 %, -2 %) and R_b (6.7 %, -3 %): compounded active 2.5370 %, plain sum 2.5000 %.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.attribution import Attribution, brinson_fachler
from qrlab.core.errors import AlignmentError, ValidationError

SEGMENTS = ["equity", "bonds", "cash"]


def _frame(rows: list[list[float]]) -> pd.DataFrame:
    index = pd.date_range("2025-12-31", periods=len(rows), freq="ME")
    return pd.DataFrame(rows, index=index, columns=SEGMENTS)


WP = _frame([[0.6, 0.3, 0.1]])
WB = _frame([[0.5, 0.4, 0.1]])
RP = _frame([[0.12, 0.03, 0.01]])
RB = _frame([[0.10, 0.04, 0.01]])


def _run(**changes: object) -> Attribution:
    kwargs: dict[str, object] = {
        "portfolio_weights": WP,
        "portfolio_returns": RP,
        "benchmark_weights": WB,
        "benchmark_returns": RB,
        "interaction": "separate",
        "linking": "carino",
    }
    kwargs.update(changes)
    return brinson_fachler(**kwargs)  # type: ignore[arg-type]


def test_one_period_hand_example() -> None:
    result = _run()
    assert result.portfolio_return == pytest.approx(0.082)
    assert result.benchmark_return == pytest.approx(0.067)
    assert result.active_return == pytest.approx(0.015)
    totals = result.totals
    assert totals["allocation"].to_list() == pytest.approx([0.0033, 0.0027, 0.0])
    assert totals["selection"].to_list() == pytest.approx([0.010, -0.004, 0.0])
    assert totals["interaction"].to_list() == pytest.approx([0.002, 0.001, 0.0])
    assert result.effect_totals().to_list() == pytest.approx([0.006, 0.006, 0.003])
    assert float(totals.to_numpy().sum()) == pytest.approx(0.015, abs=1e-15)
    assert result.residual == 0.0
    assert result.by_period.columns.get_level_values(0).unique().to_list() == [
        "allocation",
        "selection",
        "interaction",
    ]


def test_interaction_in_selection() -> None:
    result = _run(interaction="in_selection")
    assert result.effect_totals().to_list() == pytest.approx([0.006, 0.009, 0.0])
    assert result.interaction == "in_selection"


def test_two_periods_with_carino_and_without_linking() -> None:
    wp = _frame([[0.6, 0.3, 0.1], [0.6, 0.3, 0.1]])
    wb = _frame([[0.5, 0.4, 0.1], [0.5, 0.4, 0.1]])
    rp = _frame([[0.12, 0.03, 0.01], [-0.05, 0.03, 0.01]])
    rb = _frame([[0.10, 0.04, 0.01], [-0.07, 0.01, 0.01]])
    linked = _run(
        portfolio_weights=wp, portfolio_returns=rp, benchmark_weights=wb, benchmark_returns=rb
    )
    assert linked.portfolio_return == pytest.approx(
        1.082 * 0.98 - 1
    )  # R_p,2 = -3 % + 0.9 % + 0.1 %
    assert linked.benchmark_return == pytest.approx(1.067 * 0.97 - 1)
    assert linked.active_return == pytest.approx(0.02537, abs=1e-9)
    assert float(linked.totals.to_numpy().sum()) == pytest.approx(linked.active_return, abs=1e-14)
    plain = _run(
        portfolio_weights=wp,
        portfolio_returns=rp,
        benchmark_weights=wb,
        benchmark_returns=rb,
        linking="none",
    )
    assert float(plain.totals.to_numpy().sum()) == pytest.approx(0.025, abs=1e-12)
    assert plain.residual == pytest.approx(0.00037, abs=1e-9)
    assert plain.linking == "none"


def test_equal_portfolio_and_benchmark_and_equal_period_returns() -> None:
    same = _run(portfolio_weights=WB, portfolio_returns=RB)
    assert np.allclose(same.totals.to_numpy(), 0.0)
    assert same.active_return == 0.0
    # equal total returns in one period use the limit 1/(1+R) of the Carino coefficient
    wp = _frame([[0.5, 0.5, 0.0], [0.6, 0.3, 0.1]])
    wb = _frame([[0.5, 0.5, 0.0], [0.5, 0.4, 0.1]])
    rp = _frame([[0.02, 0.0, 0.0], [0.12, 0.03, 0.01]])
    rb = _frame([[0.0, 0.02, 0.0], [0.10, 0.04, 0.01]])
    mixed = _run(
        portfolio_weights=wp, portfolio_returns=rp, benchmark_weights=wb, benchmark_returns=rb
    )
    assert float(mixed.totals.to_numpy().sum()) == pytest.approx(mixed.active_return, abs=1e-14)


def test_input_errors() -> None:
    with pytest.raises(ValidationError, match="interaction"):
        _run(interaction="both")
    with pytest.raises(ValidationError, match="linking"):
        _run(linking="frongello")
    with pytest.raises(ValidationError, match="sum to 1"):
        _run(portfolio_weights=_frame([[0.6, 0.3, 0.2]]))
    with pytest.raises(ValidationError, match="same order"):
        _run(benchmark_returns=RB[["bonds", "equity", "cash"]])
    with pytest.raises(AlignmentError):
        _run(benchmark_returns=RB.set_axis(pd.DatetimeIndex(["2026-01-31"])))
    with pytest.raises(ValidationError):
        _run(portfolio_returns=_frame([[np.nan, 0.03, 0.01]]))
    with pytest.raises(ValidationError, match="-100"):
        _run(
            portfolio_weights=_frame([[1.0, 0.0, 0.0]]),
            portfolio_returns=_frame([[-1.0, 0.0, 0.0]]),
        )
    empty = WP.iloc[:0]
    with pytest.raises(ValidationError, match="at least one period"):
        _run(
            portfolio_weights=empty,
            portfolio_returns=RP.iloc[:0],
            benchmark_weights=WB.iloc[:0],
            benchmark_returns=RB.iloc[:0],
        )
