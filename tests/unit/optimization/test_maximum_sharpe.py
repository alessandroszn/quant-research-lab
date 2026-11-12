"""Long-only maximum Sharpe ratio: hand-calculated cases, then cross-checks."""

from __future__ import annotations

import itertools
import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.optimization import maximum_sharpe
from qrlab.risk.covariance import CovarianceEstimate


def _cov(matrix: list[list[float]] | np.ndarray, names: list[str]) -> CovarianceEstimate:
    return CovarianceEstimate(pd.DataFrame(matrix, index=names, columns=names), "sample", 60, 0)


def _sharpe(w: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
    return float(w @ mu / math.sqrt(w @ sigma @ w))


def test_two_uncorrelated_assets_by_hand() -> None:
    # Sigma^-1 mu = (0.01/0.01, 0.02/0.04) = (1, 0.5), normalised: (2/3, 1/3).
    cov = _cov([[0.01, 0.0], [0.0, 0.04]], ["a", "b"])
    result = maximum_sharpe(pd.Series({"a": 0.01, "b": 0.02}), cov)
    assert result.weights.to_numpy() == pytest.approx([2 / 3, 1 / 3], abs=1e-8)
    assert result.method == "maximum_sharpe"
    # Sharpe of (2/3, 1/3): mean 0.04/3, variance (4/9) 0.01 + (1/9) 0.04 = 0.08/9.
    assert result.objective == pytest.approx((0.04 / 3) / math.sqrt(0.08 / 9), rel=1e-8)


def test_negative_expected_return_gets_zero_weight() -> None:
    # Unconstrained Sigma^-1 mu = (1, -0.25): long-only puts everything in a.
    cov = _cov([[0.01, 0.0], [0.0, 0.04]], ["a", "b"])
    result = maximum_sharpe(pd.Series({"a": 0.01, "b": -0.01}), cov)
    assert result.weights.to_numpy() == pytest.approx([1.0, 0.0], abs=1e-10)
    assert result.weights["b"] == 0.0
    assert result.active == ("b",)


def test_matches_tangency_when_it_is_long_only(rng: np.random.Generator) -> None:
    names = ["a", "b", "c", "d"]
    x = rng.normal(0.0, 0.05, (200, 4))
    sigma = np.cov(x, rowvar=False)
    mu = sigma @ np.array([1.0, 2.0, 0.5, 1.5])  # tangency proportional to (1, 2, 0.5, 1.5)
    result = maximum_sharpe(pd.Series(mu, index=names), _cov(sigma, names))
    assert result.weights.to_numpy() == pytest.approx(np.array([1, 2, 0.5, 1.5]) / 5.0, abs=1e-7)


def test_beats_every_point_of_a_simplex_grid(rng: np.random.Generator) -> None:
    names = ["a", "b", "c"]
    sigma = np.array([[0.04, 0.012, -0.004], [0.012, 0.09, 0.02], [-0.004, 0.02, 0.0225]])
    mu = np.array([0.006, 0.012, -0.002])
    result = maximum_sharpe(pd.Series(mu, index=names), _cov(sigma, names))
    best = max(
        _sharpe(np.array([i, j, 100 - i - j]) / 100.0, mu, sigma)
        for i, j in itertools.product(range(101), repeat=2)
        if i + j <= 100 and (i * mu[0] + j * mu[1] + (100 - i - j) * mu[2]) > 0
    )
    assert result.objective >= best - 1e-9
    assert result.weights.sum() == pytest.approx(1.0)
    assert (result.weights >= 0).all()


def test_no_positive_expected_return_raises() -> None:
    cov = _cov([[0.01, 0.0], [0.0, 0.04]], ["a", "b"])
    with pytest.raises(ValidationError, match="positive expected"):
        maximum_sharpe(pd.Series({"a": 0.0, "b": -0.01}), cov)


def test_inputs_are_validated() -> None:
    cov = _cov([[0.01, 0.0], [0.0, 0.04]], ["a", "b"])
    with pytest.raises(ValidationError, match="expected returns"):
        maximum_sharpe(pd.Series({"a": 0.01, "c": 0.02}), cov)
    zero = _cov([[0.0, 0.0], [0.0, 0.04]], ["a", "b"])
    with pytest.raises(ValidationError, match="positive variance"):
        maximum_sharpe(pd.Series({"a": 0.01, "b": 0.02}), zero)


def test_solver_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = SimpleNamespace(x=np.array([0.0, 0.0]), success=False, message="no", nit=1)
    monkeypatch.setattr("scipy.optimize.minimize", lambda *a, **k: failed)
    cov = _cov([[0.01, 0.0], [0.0, 0.04]], ["a", "b"])
    with pytest.raises(ValidationError, match="optimisation failed"):
        maximum_sharpe(pd.Series({"a": 0.01, "b": 0.02}), cov)
