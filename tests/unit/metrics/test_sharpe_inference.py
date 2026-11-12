"""Sharpe-ratio inference (hand values from design note 5.1).

- PSR: SR 0.1 a month, T 120, skewness 0, kurtosis 3, benchmark 0: z 1.088154, PSR 0.861736;
- DSR: N 100 trials with variance 0.01: threshold 0.253060; SR 0.3 gives z 0.500905, DSR 0.691781;
- JKM: SR 0.2 and 0.1, rho 0.5, T 120: theta 0.0085, z 1.084652, p 0.278076.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.sharpe_inference import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    jkm_statistic,
    probabilistic_sharpe,
    probabilistic_sharpe_ratio,
    sharpe_difference_bootstrap,
    sharpe_difference_hac,
    sharpe_difference_jkm,
)


def _series(values: np.ndarray) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2000-01-31", periods=len(values), freq="ME"))


def test_psr_hand_example() -> None:
    result = probabilistic_sharpe(0.1, n=120, skew=0.0, kurtosis=3.0, benchmark=0.0)
    assert result.z == pytest.approx(1.088154, abs=1e-6)
    assert result.probability == pytest.approx(0.861736, abs=1e-6)


def test_dsr_hand_example() -> None:
    threshold = expected_max_sharpe(n_trials=100, variance=0.01)
    assert threshold == pytest.approx(0.253060, abs=1e-6)
    dsr = probabilistic_sharpe(0.3, n=120, skew=0.0, kurtosis=3.0, benchmark=threshold)
    assert dsr.z == pytest.approx(0.500905, abs=1e-6)
    assert dsr.probability == pytest.approx(0.691781, abs=1e-6)


def test_psr_and_dsr_from_returns(rng: np.random.Generator) -> None:
    returns = _series(rng.normal(0.01, 0.04, 240))
    psr = probabilistic_sharpe_ratio(returns, benchmark=0.0)
    sr = float(returns.mean() / returns.std(ddof=1))
    assert psr.sharpe == pytest.approx(sr)
    assert psr.skewness == pytest.approx(float(stats.skew(returns, bias=False)))
    assert psr.kurtosis == pytest.approx(float(stats.kurtosis(returns, bias=False)) + 3.0)
    trials = pd.Series(rng.normal(0.0, 0.1, 50))
    by_trials = deflated_sharpe_ratio(returns, n_trials=50, trial_sharpes=trials, variance=None)
    by_variance = deflated_sharpe_ratio(
        returns, n_trials=50, trial_sharpes=None, variance=float(trials.var(ddof=1))
    )
    assert by_trials.probability == pytest.approx(by_variance.probability)
    assert by_trials.probability < psr.probability  # deflating for 50 trials lowers the PSR


def test_psr_and_dsr_errors() -> None:
    with pytest.raises(UndefinedMetricError, match="3 observations"):
        probabilistic_sharpe(0.1, n=2, skew=0.0, kurtosis=3.0, benchmark=0.0)
    with pytest.raises(UndefinedMetricError, match="undefined for these moments"):
        probabilistic_sharpe(2.0, n=50, skew=2.0, kurtosis=1.0, benchmark=0.0)
    with pytest.raises(ValidationError, match="n_trials"):
        expected_max_sharpe(n_trials=1, variance=0.01)
    with pytest.raises(ValidationError, match="variance"):
        expected_max_sharpe(n_trials=5, variance=-1.0)
    returns = _series(np.array([0.01, -0.02, 0.03, 0.0]))
    with pytest.raises(ValidationError, match="exactly one"):
        deflated_sharpe_ratio(returns, n_trials=5, trial_sharpes=None, variance=None)
    with pytest.raises(ValidationError, match="two finite"):
        deflated_sharpe_ratio(returns, n_trials=5, trial_sharpes=pd.Series([0.1]), variance=None)


def test_jkm_hand_example() -> None:
    theta, z = jkm_statistic(0.2, 0.1, rho=0.5, n=120)
    assert theta == pytest.approx(0.0085)
    assert z == pytest.approx(1.084652, abs=1e-6)
    assert 2 * stats.norm.sf(z) == pytest.approx(0.278076, abs=1e-6)
    with pytest.raises(UndefinedMetricError, match="zero variance"):
        jkm_statistic(0.1, 0.1, rho=1.0, n=120)


def test_sharpe_difference_tests_on_data(rng: np.random.Generator) -> None:
    common = rng.normal(0.0, 1.0, 600)
    a = _series(0.01 + 0.04 * common)
    b = _series(0.004 + 0.04 * (0.5 * common + math.sqrt(0.75) * rng.normal(0.0, 1.0, 600)))
    jkm = sharpe_difference_jkm(a, b)
    hac = sharpe_difference_hac(a, b, hac_lags=3)
    assert jkm.difference == pytest.approx(jkm.sharpe_1 - jkm.sharpe_2)
    assert jkm.method == "jobson_korkie_memmel"
    assert hac.method == "ledoit_wolf_hac(3)"
    assert 0 < hac.pvalue < 1
    assert hac.n == jkm.n == 600
    iid = sharpe_difference_hac(a, b, hac_lags=0)
    assert iid.standard_error == pytest.approx(jkm.standard_error, rel=0.15)  # normal data


@pytest.mark.parametrize("test", ["jkm", "hac"])
def test_size_under_equal_sharpe_ratios(test: str, rng: np.random.Generator) -> None:
    rejections = 0
    replications = 2000
    for _ in range(replications):
        z1 = rng.normal(0.0, 1.0, 240)
        z2 = 0.5 * z1 + math.sqrt(0.75) * rng.normal(0.0, 1.0, 240)
        a, b = _series(0.1 + z1), _series(0.1 + z2)
        result = (
            sharpe_difference_jkm(a, b)
            if test == "jkm"
            else sharpe_difference_hac(a, b, hac_lags=0)
        )
        rejections += result.pvalue < 0.05
    rate = rejections / replications
    assert abs(rate - 0.05) < 3 * math.sqrt(0.05 * 0.95 / replications)


def test_bootstrap_interval(rng: np.random.Generator) -> None:
    a = _series(rng.normal(0.01, 0.04, 240))
    b = _series(rng.normal(0.005, 0.04, 240))
    first = sharpe_difference_bootstrap(
        a, b, mean_block_length=6.0, n_resamples=500, confidence=0.9, rng=np.random.default_rng(1)
    )
    again = sharpe_difference_bootstrap(
        a, b, mean_block_length=6.0, n_resamples=500, confidence=0.9, rng=np.random.default_rng(1)
    )
    assert first.low <= first.estimate <= first.high
    assert (first.low, first.high) == (again.low, again.high)
    sr_a = float(a.mean() / a.std(ddof=1))
    sr_b = float(b.mean() / b.std(ddof=1))
    assert first.estimate == pytest.approx(sr_a - sr_b)


def test_difference_errors() -> None:
    a = _series(np.array([0.01, -0.02, 0.03, 0.0, 0.01]))
    with pytest.raises(UndefinedMetricError, match="zero variance"):
        sharpe_difference_hac(a, a, hac_lags=0)
    with pytest.raises(UndefinedMetricError, match="zero variance"):
        sharpe_difference_jkm(a, a)
    flat = _series(np.full(5, 0.01))
    with pytest.raises(UndefinedMetricError, match="zero variance"):
        sharpe_difference_hac(flat, a, hac_lags=0)
    with pytest.raises(UndefinedMetricError, match="zero variance"):
        sharpe_difference_jkm(flat, a)
    with pytest.raises(AlignmentError):
        sharpe_difference_jkm(a, a.iloc[1:])
    with pytest.raises(UndefinedMetricError, match="3 observations"):
        sharpe_difference_jkm(a.iloc[:2], a.iloc[:2])
    with pytest.raises(ValidationError, match="hac_lags"):
        sharpe_difference_hac(a, a, hac_lags=-1)
    with pytest.raises(ValidationError, match="smaller"):
        sharpe_difference_hac(a, a, hac_lags=5)
