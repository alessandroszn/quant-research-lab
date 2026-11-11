"""Drawdowns. The wealth path starts at W0 = 1, so a first-period loss is a drawdown.

Hand values for r = (0.10, -0.05, 0.02, -0.03, 0.04): wealth 1.10, 1.045, 1.0659, 1.033923,
1.07527992; drawdowns 0, -0.05, -0.031, -0.06007, -0.0224728; max -0.06007 not recovered;
Ulcer 0.0389215; Calmar 0.190287 / 0.06007 = 3.16775.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.metrics.drawdown import (
    calmar_ratio,
    drawdown_episodes,
    drawdown_series,
    max_drawdown,
    ulcer_index,
)
from qrlab.metrics.errors import UndefinedMetricError

P = 12


def _s(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2026-01-31", periods=len(values), freq="ME"))


R = _s([0.10, -0.05, 0.02, -0.03, 0.04])


def test_drawdown_series_hand_example() -> None:
    dd = drawdown_series(R)
    np.testing.assert_allclose(
        dd.to_numpy(), [0.0, -0.05, -0.031, -0.06007, -0.0224728], atol=1e-12
    )
    assert dd.index.equals(R.index)
    assert max_drawdown(R) == pytest.approx(-0.06007, abs=1e-12)


def test_ulcer_and_calmar_hand_example() -> None:
    assert ulcer_index(R) == pytest.approx(0.0389215407, abs=1e-10)
    assert calmar_ratio(R, periods_per_year=P) == pytest.approx(3.1677540806, abs=1e-9)


def test_episode_hand_example() -> None:
    episodes = drawdown_episodes(R)
    assert len(episodes) == 1
    row = episodes.iloc[0]
    assert row["peak"] == pd.Timestamp("2026-01-31")
    assert not row["peak_is_sample_start"]
    assert row["trough"] == pd.Timestamp("2026-04-30")
    assert pd.isna(row["recovery"])
    assert row["depth"] == pytest.approx(-0.06007)
    assert row["periods_to_trough"] == 3
    assert pd.isna(row["periods_to_recovery"])


def test_first_period_loss_counts_as_drawdown_from_initial_wealth() -> None:
    r = _s([-0.10, 0.05, 0.10])
    assert max_drawdown(r) == pytest.approx(-0.10)
    episodes = drawdown_episodes(r)
    row = episodes.iloc[0]
    assert row["peak_is_sample_start"]
    assert pd.isna(row["peak"])
    assert row["trough"] == pd.Timestamp("2026-01-31")
    # wealth 0.90, 0.945, 1.0395: recovered in the third period, three periods after W0
    assert row["recovery"] == pd.Timestamp("2026-03-31")
    assert row["periods_to_trough"] == 1
    assert row["periods_to_recovery"] == 3


def test_multiple_episodes_in_chronological_order() -> None:
    r = _s([0.05, -0.10, 0.20, -0.05, -0.05, 0.02])
    episodes = drawdown_episodes(r)
    assert len(episodes) == 2
    assert list(episodes["trough"]) == [pd.Timestamp("2026-02-28"), pd.Timestamp("2026-05-31")]
    assert episodes.iloc[0]["recovery"] == pd.Timestamp("2026-03-31")
    assert pd.isna(episodes.iloc[1]["recovery"])
    assert episodes["depth"].min() == pytest.approx(max_drawdown(r))


def test_recovery_requires_reaching_the_previous_peak_exactly_or_above() -> None:
    # wealth 1.25 -> 1.0 -> 1.25, exact in binary floating point: recovery at equality
    r = _s([0.25, -0.20, 0.25])
    episodes = drawdown_episodes(r)
    assert episodes.iloc[0]["recovery"] == pd.Timestamp("2026-03-31")


def test_no_drawdown() -> None:
    r = _s([0.01, 0.02, 0.0])
    assert max_drawdown(r) == 0.0
    assert ulcer_index(r) == 0.0
    assert drawdown_episodes(r).empty
    with pytest.raises(UndefinedMetricError, match="drawdown"):
        calmar_ratio(r, periods_per_year=P)


def test_total_loss() -> None:
    r = _s([0.10, -1.0])
    assert max_drawdown(r) == pytest.approx(-1.0)


def test_drawdowns_match_independent_cummax(rng: np.random.Generator) -> None:
    r = _s(list(rng.normal(0.005, 0.05, 300)))
    wealth = np.concatenate([[1.0], np.cumprod(1 + r.to_numpy())])
    peaks = np.maximum.accumulate(wealth)
    expected = (wealth / peaks - 1)[1:]
    np.testing.assert_allclose(drawdown_series(r).to_numpy(), expected, rtol=1e-12, atol=1e-15)
    assert ulcer_index(r) == pytest.approx(math.sqrt(np.mean(expected**2)), rel=1e-12)


def test_empty_series_is_undefined() -> None:
    empty = pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    with pytest.raises(UndefinedMetricError):
        max_drawdown(empty)
