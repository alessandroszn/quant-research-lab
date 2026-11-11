"""Covariance estimators and risk decomposition. All data synthetic.

Hand values (design note 3.1):

- sigma 20 % / 10 %, rho 0.5, weights 0.5 / 0.5: Sigma w = (0.025, 0.010), sigma_p =
  sqrt(0.0175) = 0.132288, MCR = (0.188982, 0.075593), CCR = (0.094491, 0.037796), shares
  71.43 % / 28.57 %;
- EWMA with lambda 0.5, zero mean, returns 0.01, 0.02, -0.01 (oldest first): weights 0.142857,
  0.285714, 0.571429; variance 1.857143e-4;
- effective bets: N uncorrelated equal-variance assets with equal weights give N.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from sklearn.covariance import ledoit_wolf

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.risk import historical_es, parametric_es
from qrlab.risk import (
    CovarianceEstimate,
    effective_number_of_bets,
    ewma_covariance,
    historical_es_contributions,
    ledoit_wolf_covariance,
    normal_es_contributions,
    sample_covariance,
    volatility_contributions,
)

SIMPLE = ReturnKind.SIMPLE
RAISE = NanPolicy.RAISE


def _returns(values: np.ndarray, columns: list[str] | None = None) -> pd.DataFrame:
    index = pd.date_range("2020-01-31", periods=len(values), freq="ME")
    names = columns or [f"A{i}" for i in range(values.shape[1])]
    return pd.DataFrame(values, index=index, columns=names)


def _cov(matrix: list[list[float]], names: list[str]) -> CovarianceEstimate:
    return CovarianceEstimate(pd.DataFrame(matrix, index=names, columns=names), "given", 0, 0)


# --------------------------------------------------------------------------- covariance
def test_sample_covariance_matches_numpy_and_reports_dropped_rows(rng: np.random.Generator) -> None:
    values = rng.normal(0.0, 0.02, size=(60, 3))
    frame = _returns(values)
    estimate = sample_covariance(frame, kind=SIMPLE, missing=RAISE)
    np.testing.assert_allclose(estimate.matrix.to_numpy(), np.cov(values, rowvar=False))
    assert (estimate.estimator, estimate.n_obs, estimate.dropped_rows) == ("sample", 60, 0)
    gappy = frame.copy()
    gappy.iloc[5, 1] = np.nan
    with pytest.raises(ValidationError):
        sample_covariance(gappy, kind=SIMPLE, missing=RAISE)
    dropped = sample_covariance(gappy, kind=SIMPLE, missing=NanPolicy.DROP)
    assert (dropped.n_obs, dropped.dropped_rows) == (59, 1)
    np.testing.assert_allclose(estimate.volatilities(), values.std(axis=0, ddof=1))


def test_ewma_hand_example() -> None:
    frame = _returns(np.array([[0.01], [0.02], [-0.01]]))
    estimate = ewma_covariance(frame, kind=SIMPLE, missing=RAISE, decay=0.5, demean=False)
    assert estimate.matrix.to_numpy()[0, 0] == pytest.approx(1.857143e-4, rel=1e-6)
    assert estimate.params == {"lambda": 0.5, "demean": 0.0}
    demeaned = ewma_covariance(frame, kind=SIMPLE, missing=RAISE, decay=0.5, demean=True)
    mean = 0.02 / 3
    expected = (
        (0.01 - mean) ** 2 * 0.125 + (0.02 - mean) ** 2 * 0.25 + (-0.01 - mean) ** 2 * 0.5
    ) / 0.875
    assert demeaned.matrix.to_numpy()[0, 0] == pytest.approx(expected)


def test_ewma_approaches_equal_weights_as_lambda_tends_to_one(rng: np.random.Generator) -> None:
    frame = _returns(rng.normal(0.0, 0.01, size=(50, 2)))
    near_one = ewma_covariance(frame, kind=SIMPLE, missing=RAISE, decay=0.999999, demean=True)
    biased = np.cov(frame.to_numpy(), rowvar=False, ddof=0)
    np.testing.assert_allclose(near_one.matrix.to_numpy(), biased, rtol=1e-3)


@pytest.mark.parametrize("decay", [0.0, 1.0, 1, True, "0.94"])
def test_ewma_rejects_bad_decay(decay: object) -> None:
    frame = _returns(np.array([[0.01], [0.02]]))
    with pytest.raises(ValidationError, match="decay"):
        ewma_covariance(frame, kind=SIMPLE, missing=RAISE, decay=decay, demean=False)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="demean"):
        ewma_covariance(frame, kind=SIMPLE, missing=RAISE, decay=0.9, demean=1)  # type: ignore[arg-type]


def test_ledoit_wolf_matches_scikit_learn(rng: np.random.Generator) -> None:
    values = rng.normal(0.0, 1.0, size=(40, 5)) * np.array([0.01, 0.02, 0.03, 0.015, 0.05])
    estimate = ledoit_wolf_covariance(_returns(values), kind=SIMPLE, missing=RAISE)
    reference, shrinkage = ledoit_wolf(values)
    np.testing.assert_allclose(estimate.matrix.to_numpy(), reference, rtol=1e-10, atol=1e-16)
    assert estimate.params["shrinkage"] == pytest.approx(shrinkage, rel=1e-10)


def test_ledoit_wolf_shrinkage_limits(rng: np.random.Generator) -> None:
    distinct = rng.normal(0.0, 1.0, size=(20_000, 3)) * np.array([0.01, 0.03, 0.09])
    large = ledoit_wolf_covariance(_returns(distinct), kind=SIMPLE, missing=RAISE)
    assert large.params["shrinkage"] < 0.01
    identity_draws = rng.normal(0.0, 1.0, size=(10, 4))
    small = ledoit_wolf_covariance(_returns(identity_draws), kind=SIMPLE, missing=RAISE)
    assert small.params["shrinkage"] > 0.5
    more_assets = rng.normal(0.0, 1.0, size=(5, 8))
    singular = sample_covariance(_returns(more_assets), kind=SIMPLE, missing=RAISE)
    assert np.linalg.matrix_rank(singular.matrix.to_numpy()) < 8
    shrunk = ledoit_wolf_covariance(_returns(more_assets), kind=SIMPLE, missing=RAISE)
    assert np.linalg.matrix_rank(shrunk.matrix.to_numpy()) == 8
    flat = ledoit_wolf_covariance(
        _returns(np.array([[1.0, 2.0], [-1.0, -2.0], [1.0, -2.0], [-1.0, 2.0]]) * 0.01),
        kind=SIMPLE,
        missing=RAISE,
    )
    assert flat.params["shrinkage"] >= 0.0


def test_ledoit_wolf_of_a_scaled_identity_sample_does_not_shrink() -> None:
    values = np.array([[1.0, 1.0], [1.0, -1.0], [-1.0, 1.0], [-1.0, -1.0]])
    estimate = ledoit_wolf_covariance(_returns(values), kind=SIMPLE, missing=RAISE)
    assert estimate.params["shrinkage"] == 0.0
    np.testing.assert_allclose(estimate.matrix.to_numpy(), np.eye(2))


def test_input_validation() -> None:
    frame = _returns(np.array([[0.01, 0.02]]))
    with pytest.raises(ValidationError, match="simple returns"):
        sample_covariance(frame, kind=ReturnKind.LOG, missing=RAISE)
    with pytest.raises(ValidationError, match="missing"):
        sample_covariance(frame, kind=SIMPLE, missing=NanPolicy.KEEP)
    with pytest.raises(ValidationError, match="at least 2"):
        sample_covariance(frame, kind=SIMPLE, missing=RAISE)
    empty = pd.DataFrame(index=pd.date_range("2020-01-31", periods=3, freq="ME"))
    with pytest.raises(ValidationError, match="asset column"):
        sample_covariance(empty, kind=SIMPLE, missing=RAISE)


def test_covariance_estimate_is_checked() -> None:
    with pytest.raises(ValidationError, match="symmetric"):
        _cov([[1.0, 0.5], [0.4, 1.0]], ["a", "b"])
    with pytest.raises(ValidationError, match="semi-definite"):
        _cov([[1.0, 2.0], [2.0, 1.0]], ["a", "b"])


# --------------------------------------------------------------------------- decomposition
SIGMA = _cov([[0.04, 0.01], [0.01, 0.01]], ["a", "b"])
HALF = pd.Series({"a": 0.5, "b": 0.5})


def test_volatility_contributions_hand_example() -> None:
    result = volatility_contributions(SIGMA, HALF)
    assert result.total == pytest.approx(math.sqrt(0.0175))
    assert result.marginal is not None
    assert result.marginal.to_list() == pytest.approx([0.188982, 0.075593], abs=1e-6)
    assert result.component.to_list() == pytest.approx([0.094491, 0.037796], abs=1e-6)
    assert float(result.component.sum()) == pytest.approx(result.total, abs=1e-15)
    assert result.share.to_list() == pytest.approx([0.0125 / 0.0175, 0.005 / 0.0175])
    assert result.weight_sum == 1.0


def test_long_short_weights_and_zero_volatility() -> None:
    hedge = volatility_contributions(SIGMA, pd.Series({"a": 1.0, "b": -1.0}))
    assert hedge.weight_sum == 0.0
    assert float(hedge.component.sum()) == pytest.approx(hedge.total)
    with pytest.raises(UndefinedMetricError, match="zero"):
        volatility_contributions(SIGMA, pd.Series({"a": 0.0, "b": 0.0}))


def test_weight_labels_must_match() -> None:
    with pytest.raises(ValidationError, match="missing"):
        volatility_contributions(SIGMA, pd.Series({"a": 1.0}))
    with pytest.raises(ValidationError, match="duplicated"):
        volatility_contributions(SIGMA, pd.Series([0.5, 0.5], index=["a", "a"]))
    with pytest.raises(ValidationError, match="finite"):
        volatility_contributions(SIGMA, pd.Series({"a": np.nan, "b": 1.0}))
    with pytest.raises(ValidationError, match="Series"):
        volatility_contributions(SIGMA, {"a": 0.5, "b": 0.5})  # type: ignore[arg-type]


def test_es_contributions_sum_to_the_metrics(rng: np.random.Generator) -> None:
    frame = _returns(rng.standard_t(4, size=(250, 3)) * 0.01, ["x", "y", "z"])
    weights = pd.Series({"x": 0.5, "y": 0.3, "z": 0.2})
    portfolio = frame @ weights
    hist = historical_es_contributions(frame, weights, confidence=0.975, kind=SIMPLE, missing=RAISE)
    assert hist.total == pytest.approx(historical_es(portfolio, confidence=0.975), abs=1e-12)
    assert float(hist.share.sum()) == pytest.approx(1.0)
    normal = normal_es_contributions(frame, weights, confidence=0.975, kind=SIMPLE, missing=RAISE)
    assert normal.total == pytest.approx(parametric_es(portfolio, confidence=0.975), abs=1e-12)
    assert normal.marginal is None


def test_historical_es_hand_example_with_fractional_tail() -> None:
    # 10 dates at 85 %: m = 1.5, the worst date counts fully and the second worst half.
    a = [0.01, -0.05, 0.02, 0.0, -0.02, 0.01, 0.03, 0.0, 0.01, 0.02]
    b = [0.0] * 10
    frame = _returns(np.array([a, b]).T, ["a", "b"])
    weights = pd.Series({"a": 1.0, "b": 0.0})
    result = historical_es_contributions(
        frame, weights, confidence=0.85, kind=SIMPLE, missing=RAISE
    )
    assert result.component["a"] == pytest.approx((0.05 + 0.5 * 0.02) / 1.5)
    assert result.component["b"] == 0.0


def test_es_contributions_edge_cases() -> None:
    frame = _returns(np.array([[0.01, 0.02], [0.03, -0.01]]), ["a", "b"])
    with pytest.raises(UndefinedMetricError, match="tail"):
        historical_es_contributions(frame, HALF, confidence=0.95, kind=SIMPLE, missing=RAISE)
    flat = _returns(np.array([[0.01, 0.01], [0.01, 0.01]]), ["a", "b"])
    with pytest.raises(UndefinedMetricError, match="zero"):
        normal_es_contributions(flat, HALF, confidence=0.95, kind=SIMPLE, missing=RAISE)
    for bad in (1.0, True, "0.95"):
        with pytest.raises(ValidationError, match="confidence"):
            normal_es_contributions(frame, HALF, confidence=bad, kind=SIMPLE, missing=RAISE)  # type: ignore[arg-type]


def test_effective_number_of_bets() -> None:
    names = ["a", "b", "c", "d"]
    identity = _cov((np.eye(4) * 0.01).tolist(), names)
    equal = pd.Series(0.25, index=names)
    assert effective_number_of_bets(identity, equal) == pytest.approx(4.0)
    single = pd.Series({"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0})
    assert effective_number_of_bets(identity, single) == pytest.approx(1.0)
    assert 1.0 <= effective_number_of_bets(SIGMA, HALF) <= 2.0
    with pytest.raises(UndefinedMetricError, match="zero"):
        effective_number_of_bets(identity, pd.Series(0.0, index=names))


def test_historical_es_with_a_whole_tail() -> None:
    a = [0.01] * 19 + [-0.08]
    frame = _returns(np.array([a, [0.0] * 20]).T, ["a", "b"])
    result = historical_es_contributions(
        frame, pd.Series({"a": 0.5, "b": 0.5}), confidence=0.95, kind=SIMPLE, missing=RAISE
    )
    assert result.total == pytest.approx(0.04)  # m = 1: the worst date, 0.5 x 8 %
