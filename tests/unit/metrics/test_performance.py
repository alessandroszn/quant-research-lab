"""Performance metrics. Hand values from the approved design note (docs/design/1.4-metrics.md).

Series r = (0.10, -0.05, 0.02, -0.03, 0.04), P = 12:

- mean 0.016, annual arithmetic 0.192; s = sqrt(0.00353) = 0.0594138, annual vol 0.205815
- CAGR 1.07527992 ** (12/5) - 1 = 0.190287
- Sharpe 0.269298 per period, 0.932875 annual; Lo SE 0.455250 per period, 1.577031 annual
- downside deviation (target 0) 0.0260768, annual 0.0903327; Sortino annual 2.12548
- hit rate 0.6; gain/loss 1.33333
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind, compound
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.moments import excess_kurtosis, skewness
from qrlab.metrics.performance import (
    SharpeSE,
    annualised_arithmetic_return,
    annualised_geometric_return,
    annualised_volatility,
    downside_deviation,
    gain_loss_ratio,
    hit_rate,
    sharpe_ratio,
    sortino_ratio,
)

P = 12
HAND = [0.10, -0.05, 0.02, -0.03, 0.04]


def _s(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2026-01-31", periods=len(values), freq="ME"))


R = _s(HAND)


# --------------------------------------------------------------------------- hand examples
def test_returns_and_volatility_hand_example() -> None:
    assert annualised_arithmetic_return(R, periods_per_year=P) == pytest.approx(0.192, abs=1e-15)
    assert annualised_geometric_return(R, periods_per_year=P) == pytest.approx(
        0.1902869876, abs=1e-10
    )
    assert annualised_volatility(R, periods_per_year=P) == pytest.approx(0.2058154513, abs=1e-10)


def test_sharpe_hand_example_with_lo_standard_error() -> None:
    est = sharpe_ratio(R, periods_per_year=P, se_method=SharpeSE.IID_NORMAL)
    assert est.value == pytest.approx(0.9328745669, abs=1e-10)
    assert est.standard_error == pytest.approx(1.5770305944, abs=1e-10)
    assert est.n == 5
    assert est.method is SharpeSE.IID_NORMAL


def test_sharpe_mertens_matches_its_formula() -> None:
    est = sharpe_ratio(R, periods_per_year=P, se_method=SharpeSE.IID_NON_NORMAL)
    sr = 0.016 / math.sqrt(0.00353)
    g3, ex = skewness(R), excess_kurtosis(R)
    expected = math.sqrt((1 + sr**2 / 2 - g3 * sr + ex / 4 * sr**2) / 5) * math.sqrt(P)
    assert est.value == pytest.approx(sr * math.sqrt(P))
    assert est.standard_error == pytest.approx(expected, rel=1e-12)


def test_sortino_and_downside_deviation_hand_example() -> None:
    assert downside_deviation(R, target=0.0, periods_per_year=P) == pytest.approx(
        0.0903327183, abs=1e-10
    )
    assert sortino_ratio(R, target=0.0, periods_per_year=P) == pytest.approx(
        2.1254757253, abs=1e-10
    )


def test_downside_deviation_uses_the_target() -> None:
    # target 0.02: shortfalls 0, -0.07, 0, -0.05, 0 -> sqrt((0.0049 + 0.0025) / 5)
    expected = math.sqrt((0.0049 + 0.0025) / 5) * math.sqrt(P)
    assert downside_deviation(R, target=0.02, periods_per_year=P) == pytest.approx(expected)


def test_hit_rate_and_gain_loss_hand_example() -> None:
    assert hit_rate(R) == pytest.approx(0.6)
    assert gain_loss_ratio(R) == pytest.approx(4 / 3)


def test_zero_return_is_not_a_hit() -> None:
    assert hit_rate(_s([0.0, 0.01, -0.01, 0.0])) == pytest.approx(0.25)


# --------------------------------------------------------------------------- cross-checks
def test_volatility_matches_numpy(rng: np.random.Generator) -> None:
    r = _s(list(rng.normal(0.01, 0.04, 240)))
    expected = np.std(r.to_numpy(), ddof=1) * math.sqrt(P)
    assert annualised_volatility(r, periods_per_year=P) == pytest.approx(expected, rel=1e-12)


def test_geometric_return_consistent_with_core_compound(rng: np.random.Generator) -> None:
    r = _s(list(rng.normal(0.005, 0.03, 120)))
    total = compound(r, kind=ReturnKind.SIMPLE)
    assert annualised_geometric_return(r, periods_per_year=P) == pytest.approx(
        (1 + total) ** (P / 120) - 1, rel=1e-12
    )


def test_moments_match_scipy(rng: np.random.Generator) -> None:
    r = _s(list(rng.standard_t(5, 300) * 0.02))
    assert skewness(r) == pytest.approx(stats.skew(r.to_numpy(), bias=False), rel=1e-12)
    assert excess_kurtosis(r) == pytest.approx(
        stats.kurtosis(r.to_numpy(), fisher=True, bias=False), rel=1e-12
    )


def test_sharpe_standard_error_coverage(rng: np.random.Generator) -> None:
    """95 % intervals from the Lo SE cover a known Sharpe ratio 93-97 % of the time."""
    true_sr_period, n, runs = 0.1, 120, 2000
    sigma = 0.04
    samples = rng.normal(true_sr_period * sigma, sigma, size=(runs, n))
    true_annual = true_sr_period * math.sqrt(P)
    index = pd.date_range("2000-01-31", periods=n, freq="ME")
    covered = 0
    for row in samples:
        est = sharpe_ratio(
            pd.Series(row, index=index), periods_per_year=P, se_method=SharpeSE.IID_NORMAL
        )
        covered += abs(est.value - true_annual) <= 1.959964 * est.standard_error
    assert 0.93 <= covered / runs <= 0.97


# --------------------------------------------------------------------------- undefined and invalid
@pytest.mark.parametrize(
    ("func", "values"),
    [
        (lambda r: annualised_volatility(r, periods_per_year=P), [0.01]),
        (
            lambda r: sharpe_ratio(r, periods_per_year=P, se_method=SharpeSE.IID_NORMAL),
            [0.01, 0.01],
        ),
        (
            lambda r: sharpe_ratio(r, periods_per_year=P, se_method=SharpeSE.IID_NON_NORMAL),
            [0.01, 0.02, 0.03],
        ),
        (lambda r: sortino_ratio(r, target=0.0, periods_per_year=P), [0.01, 0.02]),
        (lambda r: gain_loss_ratio(r), [0.01, 0.02]),
        (lambda r: gain_loss_ratio(r), [-0.01, -0.02]),
        (lambda r: annualised_geometric_return(r, periods_per_year=P), [-1.0, 0.5]),
        (lambda r: annualised_arithmetic_return(r, periods_per_year=P), []),
        (lambda r: hit_rate(r), []),
        (lambda r: skewness(r), [0.01, 0.02]),
        (lambda r: excess_kurtosis(r), [0.01, 0.02, 0.03]),
        (lambda r: skewness(r), [0.01, 0.01, 0.01]),
    ],
    ids=[
        "vol-single",
        "sharpe-zero-variance",
        "mertens-too-few",
        "sortino-no-downside",
        "gainloss-no-losses",
        "gainloss-no-gains",
        "cagr-wiped-out",
        "arith-empty",
        "hit-empty",
        "skew-too-few",
        "kurt-too-few",
        "skew-zero-variance",
    ],
)
def test_undefined_metrics_raise(func: object, values: list[float]) -> None:
    series = _s(values) if values else pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    with pytest.raises(UndefinedMetricError):
        func(series)  # type: ignore[operator]


def test_undefined_metric_error_is_a_validation_error() -> None:
    assert issubclass(UndefinedMetricError, ValidationError)


def test_nan_is_refused() -> None:
    with pytest.raises(ValidationError, match="NaN"):
        annualised_volatility(_s([0.01, np.nan, 0.02]), periods_per_year=P)


@pytest.mark.parametrize("bad", [0, -12, math.inf, math.nan, True, "12"])
def test_periods_per_year_must_be_positive_finite_number(bad: object) -> None:
    with pytest.raises(ValidationError, match="periods_per_year"):
        annualised_volatility(R, periods_per_year=bad)  # type: ignore[arg-type]


def test_se_method_must_be_enum() -> None:
    with pytest.raises(ValidationError, match="SharpeSE"):
        sharpe_ratio(R, periods_per_year=P, se_method="lo")  # type: ignore[arg-type]


def test_target_must_be_finite() -> None:
    with pytest.raises(ValidationError, match="target"):
        sortino_ratio(R, target=math.nan, periods_per_year=P)


def test_inputs_are_not_mutated() -> None:
    r = R.copy()
    sharpe_ratio(r, periods_per_year=P, se_method=SharpeSE.IID_NON_NORMAL)
    sortino_ratio(r, target=0.0, periods_per_year=P)
    pd.testing.assert_series_equal(r, R)


def test_mertens_variance_can_be_negative_in_tiny_samples() -> None:
    # (0.02, 0.02, 0.03, 0.03): bias-corrected excess kurtosis is -6, which makes the
    # Mertens radicand 1 + SR^2/2 + (-6) SR^2/4 negative (SR = 4.33 per period).
    with pytest.raises(UndefinedMetricError, match="Mertens"):
        sharpe_ratio(
            _s([0.02, 0.02, 0.03, 0.03]), periods_per_year=P, se_method=SharpeSE.IID_NON_NORMAL
        )
