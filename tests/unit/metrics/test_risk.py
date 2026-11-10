"""Value at risk and expected shortfall (positive numbers are losses, one period).

Hand values on r = (-0.05, -0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03, 0.04, 0.05), with
m = n (1 - confidence):

- 0.80: m = 2   -> VaR = -r(2) = 0.03, ES = (0.05 + 0.03) / 2 = 0.04
- 0.85: m = 1.5 -> VaR = -r(2) = 0.03, ES = (0.05 + 0.5 * 0.03) / 1.5 = 0.043333
- 0.95: m = 0.5 -> undefined
Parametric normal, mean 0, s = 0.01, 0.95: VaR = 0.0164485, ES = 0.0206271.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var

TAIL = [-0.05, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05]


def _s(values: list[float] | np.ndarray) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2026-01-05", periods=len(values)))


# --------------------------------------------------------------------------- historical
@pytest.mark.parametrize(
    ("confidence", "var", "es"),
    [(0.80, 0.03, 0.04), (0.85, 0.03, 0.065 / 1.5)],
)
def test_historical_hand_examples(confidence: float, var: float, es: float) -> None:
    shuffled = _s([TAIL[i] for i in (4, 9, 0, 6, 2, 8, 1, 5, 3, 7)])  # order must not matter
    assert historical_var(shuffled, confidence=confidence) == pytest.approx(var, abs=1e-15)
    assert historical_es(shuffled, confidence=confidence) == pytest.approx(es, abs=1e-15)


def test_too_few_observations_for_the_confidence() -> None:
    with pytest.raises(UndefinedMetricError, match="tail"):
        historical_var(_s(TAIL), confidence=0.95)
    with pytest.raises(UndefinedMetricError, match="tail"):
        historical_es(_s(TAIL), confidence=0.95)


def test_floating_point_tail_size_regression() -> None:
    # 20 * (1 - 0.95) is 1.0000000000000009 in floating point; without rounding the
    # ceiling would be 2 and VaR would use the second-worst return instead of the worst.
    r = _s(list(np.linspace(-0.10, 0.09, 20)))
    assert historical_var(r, confidence=0.95) == pytest.approx(0.10)
    assert historical_es(r, confidence=0.95) == pytest.approx(0.10)


def test_es_is_mean_of_worst_returns_when_tail_is_whole(rng: np.random.Generator) -> None:
    values = rng.normal(0, 0.02, 1000)
    worst = np.sort(values)[:50]
    assert historical_es(_s(values), confidence=0.95) == pytest.approx(-worst.mean(), rel=1e-12)
    assert historical_var(_s(values), confidence=0.95) == pytest.approx(-worst[-1], rel=1e-12)


def test_es_is_never_below_var(rng: np.random.Generator) -> None:
    values = _s(rng.standard_t(4, 777) * 0.01)
    for confidence in (0.5, 0.9, 0.95, 0.975, 0.99):
        assert historical_es(values, confidence=confidence) >= historical_var(
            values, confidence=confidence
        )


def test_historical_converges_to_parametric_for_normal_data(rng: np.random.Generator) -> None:
    values = _s(rng.normal(0.0005, 0.01, 200_000))
    for confidence in (0.95, 0.99):
        assert historical_var(values, confidence=confidence) == pytest.approx(
            parametric_var(values, confidence=confidence), rel=0.02
        )
        assert historical_es(values, confidence=confidence) == pytest.approx(
            parametric_es(values, confidence=confidence), rel=0.02
        )


# --------------------------------------------------------------------------- parametric
def test_parametric_hand_example() -> None:
    values = _s([0.01, -0.01] * 50)  # mean 0; sample s = 0.01 * sqrt(100 / 99)
    s = 0.01 * math.sqrt(100 / 99)
    z = 1.6448536269514722
    assert parametric_var(values, confidence=0.95) == pytest.approx(s * z, rel=1e-12)
    assert parametric_es(values, confidence=0.95) == pytest.approx(
        s * stats.norm.pdf(z) / 0.05, rel=1e-12
    )
    # with s = 0.01 exactly these are the design-note numbers
    assert 0.01 * z == pytest.approx(0.0164485363)
    assert 0.01 * stats.norm.pdf(z) / 0.05 == pytest.approx(0.0206271281)


def test_parametric_es_matches_numerical_integration() -> None:
    values = _s([0.03, -0.01, 0.02, -0.04, 0.01, 0.0])
    mean, s = float(np.mean(values)), float(np.std(values, ddof=1))
    q = stats.norm.ppf(0.05, loc=mean, scale=s)
    tail_mean = stats.norm.expect(lambda x: x, loc=mean, scale=s, ub=q, conditional=True)
    assert parametric_es(values, confidence=0.95) == pytest.approx(-tail_mean, rel=1e-8)


def test_mean_shifts_parametric_var() -> None:
    base = _s([0.01, -0.01] * 10)
    shifted = base + 0.002
    assert parametric_var(shifted, confidence=0.99) == pytest.approx(
        parametric_var(base, confidence=0.99) - 0.002
    )


# --------------------------------------------------------------------------- validation
@pytest.mark.parametrize("bad", [0.0, 1.0, -0.5, 1.5, math.nan, True])
def test_confidence_must_be_strictly_between_zero_and_one(bad: float) -> None:
    for func in (historical_var, historical_es, parametric_var, parametric_es):
        with pytest.raises(ValidationError, match="confidence"):
            func(_s(TAIL), confidence=bad)


def test_parametric_needs_two_observations() -> None:
    with pytest.raises(UndefinedMetricError):
        parametric_var(_s([0.01]), confidence=0.95)


def test_nan_refused() -> None:
    with pytest.raises(ValidationError, match="NaN"):
        historical_var(_s([0.01, np.nan] * 10), confidence=0.8)
