"""Monte Carlo engines. Seeded and synthetic.

Hand value (design note 3.3): one asset, log mean 0.005 and volatility 0.04 a month, 120
months: E[W_T] = exp(120 (0.005 + 0.0008)) = 2.005714.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.simulation import (
    MAX_CELLS,
    LogMoments,
    bootstrap_returns,
    log_moments,
    normal_returns,
    student_t_returns,
)

SIMPLE, RAISE = ReturnKind.SIMPLE, NanPolicy.RAISE


def _moments(
    mean: list[float], cov: list[list[float]], names: list[str] | None = None
) -> LogMoments:
    labels = names or [f"a{i}" for i in range(len(mean))]
    return LogMoments(
        pd.Series(mean, index=labels), pd.DataFrame(cov, index=labels, columns=labels), 100
    )


def _history(rng: np.random.Generator, rows: int = 60) -> pd.DataFrame:
    index = pd.date_range("2015-01-31", periods=rows, freq="ME")
    return pd.DataFrame(rng.normal(0.005, 0.03, size=(rows, 2)), index=index, columns=["eq", "bd"])


def test_normal_engine_matches_the_lognormal_closed_form() -> None:
    moments = _moments([0.005], [[0.04**2]])
    sim = normal_returns(
        moments, n_paths=200_000, n_periods=120, rng=np.random.default_rng(1), max_cells=MAX_CELLS
    )
    terminal = np.prod(1.0 + sim.returns[:, :, 0], axis=1)
    expected = math.exp(120 * (0.005 + 0.04**2 / 2))
    assert expected == pytest.approx(2.005714, abs=1e-6)
    standard_error = terminal.std(ddof=1) / math.sqrt(len(terminal))
    assert abs(terminal.mean() - expected) < 3 * standard_error
    assert (sim.n_paths, sim.n_periods, sim.assets, sim.engine) == (200_000, 120, ("a0",), "normal")


def test_normal_engine_reproduces_mean_and_covariance() -> None:
    cov = [[0.0016, 0.0004], [0.0004, 0.0009]]
    sim = normal_returns(
        _moments([0.004, 0.002], cov),
        n_paths=20_000,
        n_periods=10,
        rng=np.random.default_rng(2),
        max_cells=MAX_CELLS,
    )
    logs = np.log1p(sim.returns.reshape(-1, 2))
    np.testing.assert_allclose(logs.mean(axis=0), [0.004, 0.002], atol=3e-4)
    np.testing.assert_allclose(np.cov(logs, rowvar=False), cov, atol=3e-5)
    assert (sim.returns > -1.0).all()


def test_singular_covariance_is_allowed() -> None:
    sim = normal_returns(
        _moments([0.0, 0.0], [[0.01, 0.01], [0.01, 0.01]]),
        n_paths=100,
        n_periods=3,
        rng=np.random.default_rng(3),
        max_cells=MAX_CELLS,
    )
    np.testing.assert_allclose(sim.returns[..., 0], sim.returns[..., 1], atol=1e-12)


def test_student_t_keeps_the_covariance_and_fattens_the_tails() -> None:
    cov = [[0.0016, 0.0004], [0.0004, 0.0009]]
    sim = student_t_returns(
        _moments([0.0, 0.0], cov),
        dof=5,
        n_paths=100_000,
        n_periods=5,
        rng=np.random.default_rng(4),
        max_cells=MAX_CELLS,
    )
    logs = np.log1p(sim.returns.reshape(-1, 2))
    np.testing.assert_allclose(np.cov(logs, rowvar=False), cov, rtol=0.05)
    assert float(stats.kurtosis(logs[:, 0])) > 2.0  # t(5) has excess kurtosis 6
    assert sim.params == {"dof": 5.0}
    for dof in (2, 1.5, True, "5"):
        with pytest.raises(ValidationError, match="dof"):
            student_t_returns(
                _moments([0.0], [[0.01]]),
                dof=dof,  # type: ignore[arg-type]
                n_paths=1,
                n_periods=1,
                rng=np.random.default_rng(0),
                max_cells=MAX_CELLS,
            )


def test_bootstrap_resamples_whole_historical_rows(rng: np.random.Generator) -> None:
    history = _history(rng)
    sim = bootstrap_returns(
        history,
        kind=SIMPLE,
        missing=RAISE,
        mean_block_length=6.0,
        n_paths=2_000,
        n_periods=240,
        rng=np.random.default_rng(5),
        max_cells=MAX_CELLS,
    )
    rows = {tuple(r) for r in history.to_numpy()}
    assert all(tuple(r) in rows for r in sim.returns.reshape(-1, 2)[:5000])
    np.testing.assert_allclose(sim.returns.reshape(-1, 2).mean(axis=0), history.mean(), atol=5e-4)
    assert sim.params == {"mean_block_length": 6.0, "history_rows": 60.0}
    assert sim.assets == ("eq", "bd")


def test_bootstrap_blocks_keep_consecutive_rows(rng: np.random.Generator) -> None:
    history = _history(rng, rows=10)
    sim = bootstrap_returns(
        history,
        kind=SIMPLE,
        missing=RAISE,
        mean_block_length=1e9,
        n_paths=3,
        n_periods=25,
        rng=np.random.default_rng(6),
        max_cells=MAX_CELLS,
    )
    for path in sim.returns:  # one block per path: consecutive rows, wrapping around
        first = int(np.where((history.to_numpy() == path[0]).all(axis=1))[0][0])
        expected = history.to_numpy()[(first + np.arange(25)) % 10]
        np.testing.assert_array_equal(path, expected)


def test_same_seed_same_paths() -> None:
    moments = _moments([0.0], [[0.01]])
    a = normal_returns(
        moments, n_paths=10, n_periods=5, rng=np.random.default_rng(7), max_cells=MAX_CELLS
    )
    b = normal_returns(
        moments, n_paths=10, n_periods=5, rng=np.random.default_rng(7), max_cells=MAX_CELLS
    )
    c = normal_returns(
        moments, n_paths=10, n_periods=5, rng=np.random.default_rng(8), max_cells=MAX_CELLS
    )
    np.testing.assert_array_equal(a.returns, b.returns)
    assert not np.array_equal(a.returns, c.returns)


def test_monte_carlo_error_halves_with_four_times_the_paths() -> None:
    moments = _moments([0.005], [[0.0016]])

    def error(paths: int) -> float:
        sim = normal_returns(
            moments, n_paths=paths, n_periods=12, rng=np.random.default_rng(9), max_cells=MAX_CELLS
        )
        terminal = np.prod(1.0 + sim.returns[:, :, 0], axis=1)
        return float(terminal.std(ddof=1) / math.sqrt(paths))

    assert error(10_000) / error(40_000) == pytest.approx(2.0, rel=0.1)


def test_log_moments_from_history(rng: np.random.Generator) -> None:
    history = _history(rng)
    moments = log_moments(history, kind=SIMPLE, missing=RAISE)
    logs = np.log1p(history.to_numpy())
    np.testing.assert_allclose(moments.mean, logs.mean(axis=0))
    np.testing.assert_allclose(moments.covariance, np.cov(logs, rowvar=False))
    assert moments.n_obs == 60
    gappy = history.copy()
    gappy.iloc[0, 0] = np.nan
    assert log_moments(gappy, kind=SIMPLE, missing=NanPolicy.DROP).n_obs == 59
    with pytest.raises(ValidationError, match="simple returns"):
        log_moments(history, kind=ReturnKind.LOG, missing=RAISE)
    with pytest.raises(ValidationError, match="missing"):
        log_moments(history, kind=SIMPLE, missing=NanPolicy.KEEP)
    with pytest.raises(ValidationError, match="two observations"):
        log_moments(history.iloc[:1], kind=SIMPLE, missing=RAISE)
    crash = history.copy()
    crash.iloc[0, 0] = -1.0
    with pytest.raises(ValidationError, match="above -1"):
        log_moments(crash, kind=SIMPLE, missing=RAISE)


def test_moments_are_validated() -> None:
    with pytest.raises(ValidationError, match="labels"):
        LogMoments(
            pd.Series([0.0], index=["a"]), pd.DataFrame([[0.01]], index=["b"], columns=["b"]), 2
        )
    with pytest.raises(ValidationError, match="finite"):
        _moments([np.nan], [[0.01]])
    with pytest.raises(ValidationError, match="symmetric"):
        _moments([0.0, 0.0], [[0.01, 0.002], [0.001, 0.01]])
    with pytest.raises(ValidationError, match="semi-definite"):
        _moments([0.0, 0.0], [[0.01, 0.02], [0.02, 0.01]])


def test_sizes_and_generator_are_checked(rng: np.random.Generator) -> None:
    moments = _moments([0.0], [[0.01]])
    with pytest.raises(ValidationError, match="max_cells"):
        normal_returns(moments, n_paths=100, n_periods=100, rng=rng, max_cells=9_999)
    for paths in (0, 1.5):
        with pytest.raises(ValidationError, match="n_paths"):
            normal_returns(moments, n_paths=paths, n_periods=1, rng=rng, max_cells=10)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="Generator"):
        normal_returns(moments, n_paths=1, n_periods=1, rng=np.random.RandomState(0), max_cells=10)  # type: ignore[arg-type]
    history = _history(rng)
    for block in (0.5, True):
        with pytest.raises(ValidationError, match="mean_block_length"):
            bootstrap_returns(
                history,
                kind=SIMPLE,
                missing=RAISE,
                mean_block_length=block,
                n_paths=1,
                n_periods=1,
                rng=rng,
                max_cells=10,
            )
    with pytest.raises(ValidationError, match="simple returns"):
        bootstrap_returns(
            history,
            kind=ReturnKind.LOG,
            missing=RAISE,
            mean_block_length=2.0,
            n_paths=1,
            n_periods=1,
            rng=rng,
            max_cells=10,
        )
    with pytest.raises(ValidationError, match="missing"):
        bootstrap_returns(
            history,
            kind=SIMPLE,
            missing=NanPolicy.KEEP,
            mean_block_length=2.0,
            n_paths=1,
            n_periods=1,
            rng=rng,
            max_cells=10,
        )
    with pytest.raises(ValidationError, match="two rows"):
        bootstrap_returns(
            history.iloc[:1],
            kind=SIMPLE,
            missing=RAISE,
            mean_block_length=2.0,
            n_paths=1,
            n_periods=1,
            rng=rng,
            max_cells=10,
        )
