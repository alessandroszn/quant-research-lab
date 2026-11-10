"""Stationary bootstrap (Politis and Romano, 1994). Seeded synthetic data only.

Exact properties used as hand checks:

- a block length far beyond the sample makes every resample a rotation of the circular
  series, so every resampled mean equals the sample mean;
- rows of a frame are resampled together, so a statistic of identical columns stays zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.stats.bootstrap import stationary_bootstrap, stationary_bootstrap_indices


def _s(values: np.ndarray) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2000-01-31", periods=len(values), freq="ME"))


def _mean(values: np.ndarray) -> float:
    return float(np.mean(values))


# --------------------------------------------------------------------------- indices
def test_indices_shape_range_and_block_structure(rng: np.random.Generator) -> None:
    idx = stationary_bootstrap_indices(50, mean_block_length=5.0, n_resamples=200, rng=rng)
    assert idx.shape == (200, 50)
    assert idx.min() >= 0
    assert idx.max() <= 49
    steps = (np.diff(idx, axis=1) % 50) == 1  # continuation of a block, wrapping around
    assert 0.7 < steps.mean() < 0.9  # P(continue) = 1 - 1/5 = 0.8


def test_huge_block_length_gives_rotations(rng: np.random.Generator) -> None:
    data = _s(rng.normal(0, 1, 50))
    result = stationary_bootstrap(
        data, _mean, mean_block_length=1e12, n_resamples=200, confidence=0.9, rng=rng
    )
    np.testing.assert_allclose(result.distribution, data.mean(), rtol=0, atol=1e-14)
    assert result.low == pytest.approx(data.mean())
    assert result.high == pytest.approx(data.mean())


def test_block_length_one_is_the_iid_bootstrap(rng: np.random.Generator) -> None:
    idx = stationary_bootstrap_indices(40, mean_block_length=1.0, n_resamples=4000, rng=rng)
    steps = (np.diff(idx, axis=1) % 40) == 1
    assert steps.mean() == pytest.approx(1 / 40, abs=0.005)  # only by chance, as for iid draws
    counts = np.bincount(idx.ravel(), minlength=40) / idx.size
    np.testing.assert_allclose(counts, 1 / 40, atol=0.003)


# --------------------------------------------------------------------------- inference
def test_rows_are_resampled_together(rng: np.random.Generator) -> None:
    column = rng.normal(0, 1, 60)
    frame = pd.DataFrame(
        {"a": column, "b": column}, index=pd.date_range("2000-01-31", periods=60, freq="ME")
    )

    def difference(values: np.ndarray) -> float:
        return float(np.mean(values[:, 0] - values[:, 1]))

    result = stationary_bootstrap(
        frame, difference, mean_block_length=3.0, n_resamples=300, confidence=0.95, rng=rng
    )
    assert np.all(result.distribution == 0.0)


def test_coverage_of_the_mean_for_iid_data(rng: np.random.Generator) -> None:
    runs, covered = 300, 0
    for _ in range(runs):
        data = _s(rng.normal(0.5, 1.0, 100))
        result = stationary_bootstrap(
            data, _mean, mean_block_length=1.0, n_resamples=500, confidence=0.95, rng=rng
        )
        covered += result.low <= 0.5 <= result.high
    assert 0.90 <= covered / runs <= 0.98


def test_dependence_widens_the_interval(rng: np.random.Generator) -> None:
    n = 400
    x = np.zeros(n)
    shocks = rng.normal(0, 1, n)
    for t in range(1, n):
        x[t] = 0.8 * x[t - 1] + shocks[t]
    data = _s(x)
    iid = stationary_bootstrap(
        data, _mean, mean_block_length=1.0, n_resamples=1000, confidence=0.95, rng=rng
    )
    blocks = stationary_bootstrap(
        data, _mean, mean_block_length=20.0, n_resamples=1000, confidence=0.95, rng=rng
    )
    assert (blocks.high - blocks.low) > 1.5 * (iid.high - iid.low)


def test_reproducible_with_the_same_seed() -> None:
    data = _s(np.linspace(-1, 1, 30))
    first = stationary_bootstrap(
        data, _mean, mean_block_length=4.0, n_resamples=200, confidence=0.9,
        rng=np.random.default_rng(7),
    )  # fmt: skip
    second = stationary_bootstrap(
        data, _mean, mean_block_length=4.0, n_resamples=200, confidence=0.9,
        rng=np.random.default_rng(7),
    )  # fmt: skip
    np.testing.assert_array_equal(first.distribution, second.distribution)
    assert first.estimate == pytest.approx(0.0, abs=1e-15)
    assert first.method == "percentile"


# --------------------------------------------------------------------------- validation
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"mean_block_length": 0.5}, "mean_block_length"),
        ({"mean_block_length": float("nan")}, "mean_block_length"),
        ({"n_resamples": 50}, "n_resamples"),
        ({"n_resamples": 1000.0}, "n_resamples"),
        ({"confidence": 1.0}, "confidence"),
        ({"rng": 42}, "Generator"),
    ],
)
def test_parameter_validation(kwargs: dict[str, object], match: str) -> None:
    params: dict[str, object] = {
        "mean_block_length": 2.0,
        "n_resamples": 200,
        "confidence": 0.95,
        "rng": np.random.default_rng(1),
    }
    params.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        stationary_bootstrap(_s(np.arange(10.0)), _mean, **params)  # type: ignore[arg-type]


def test_statistic_must_return_a_finite_number() -> None:
    def bad(values: np.ndarray) -> float:
        return float("nan")

    with pytest.raises(ValidationError, match="finite"):
        stationary_bootstrap(
            _s(np.arange(10.0)), bad, mean_block_length=2.0, n_resamples=200, confidence=0.9,
            rng=np.random.default_rng(1),
        )  # fmt: skip


def test_needs_two_observations_and_no_nan() -> None:
    with pytest.raises(ValidationError, match="observations"):
        stationary_bootstrap(
            _s(np.array([1.0])), _mean, mean_block_length=2.0, n_resamples=200, confidence=0.9,
            rng=np.random.default_rng(1),
        )  # fmt: skip
    with pytest.raises(ValidationError, match="NaN"):
        stationary_bootstrap(
            _s(np.array([1.0, np.nan, 2.0])), _mean, mean_block_length=2.0, n_resamples=200,
            confidence=0.9, rng=np.random.default_rng(1),
        )  # fmt: skip


def test_indices_need_two_observations(rng: np.random.Generator) -> None:
    with pytest.raises(ValidationError, match="observations"):
        stationary_bootstrap_indices(1, mean_block_length=2.0, n_resamples=100, rng=rng)
