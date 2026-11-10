"""Benchmark-relative metrics. Hand values from the approved design note.

- r_p = r_b + c: beta 1, alpha c per period, tracking error 0 (information ratio undefined).
  Exact zero tracking error needs values exact in binary floating point, so the exact case uses
  c = 0.125 on (0.25, -0.5, 0.75); the design-note case c = 0.01 is checked with tolerances.
- r_b = (0.02, -0.01, 0.03, -0.02), r_p = r_b / 2, P = 12: up capture 0.466242, down 0.520573
  (Morningstar geometric definition: half exposure is not 0.5).
- active share of {A: .5, B: .5} vs {A: .25, B: .25, C: .5} is 0.5.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.relative import (
    active_share,
    capm_regression,
    down_capture,
    information_ratio,
    tracking_error,
    up_capture,
)

P = 12


def _s(values: list[float] | np.ndarray, start: str = "2026-01-31") -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="ME"))


# --------------------------------------------------------------------------- tracking and IR
def test_constant_outperformance_exact_case() -> None:
    b = _s([0.25, -0.5, 0.75])
    p = b + 0.125
    assert tracking_error(p, b, periods_per_year=P) == 0.0
    with pytest.raises(UndefinedMetricError, match="tracking error"):
        information_ratio(p, b, periods_per_year=P)
    est = capm_regression(p, b, periods_per_year=P)
    assert est.beta == pytest.approx(1.0, abs=1e-15)
    assert est.alpha_annualised == pytest.approx(0.125 * P, abs=1e-14)
    assert est.r_squared == pytest.approx(1.0)


def test_design_note_case_with_tolerance() -> None:
    b = _s([0.02, -0.01, 0.03, 0.005])
    est = capm_regression(b + 0.01, b, periods_per_year=P)
    assert est.beta == pytest.approx(1.0, abs=1e-12)
    assert est.alpha_annualised == pytest.approx(0.12, abs=1e-12)


def test_tracking_error_and_information_ratio_hand_example() -> None:
    b = _s([0.01, 0.02, -0.01, 0.00])
    p = _s([0.02, 0.01, 0.00, 0.01])
    # active returns 0.01, -0.01, 0.01, 0.01: mean 0.005, s = 0.01 (ddof 1)
    assert tracking_error(p, b, periods_per_year=P) == pytest.approx(0.01 * math.sqrt(P))
    assert information_ratio(p, b, periods_per_year=P) == pytest.approx(
        0.005 * P / (0.01 * math.sqrt(P))
    )


# --------------------------------------------------------------------------- CAPM cross-check
def test_capm_matches_statsmodels(rng: np.random.Generator) -> None:
    b = rng.normal(0.005, 0.04, 180)
    p = 0.001 + 1.2 * b + rng.normal(0, 0.01, 180)
    est = capm_regression(_s(p), _s(b), periods_per_year=P)
    ols = sm.OLS(p, sm.add_constant(b)).fit()
    assert est.beta == pytest.approx(ols.params[1], rel=1e-10)
    assert est.alpha_annualised == pytest.approx(ols.params[0] * P, rel=1e-10)
    assert est.se_beta == pytest.approx(ols.bse[1], rel=1e-10)
    assert est.se_alpha_annualised == pytest.approx(ols.bse[0] * P, rel=1e-10)
    assert est.r_squared == pytest.approx(ols.rsquared, rel=1e-10)
    assert est.n == 180


def test_capm_undefined_cases() -> None:
    with pytest.raises(UndefinedMetricError):
        capm_regression(_s([0.01, 0.02]), _s([0.01, 0.03]), periods_per_year=P)  # n - 2 = 0
    with pytest.raises(UndefinedMetricError, match="variance"):
        capm_regression(_s([0.01, 0.02, 0.03]), _s([0.01, 0.01, 0.01]), periods_per_year=P)
    with pytest.raises(UndefinedMetricError, match="R"):
        capm_regression(_s([0.01, 0.01, 0.01]), _s([0.01, 0.02, 0.03]), periods_per_year=P)


# --------------------------------------------------------------------------- capture
def test_capture_hand_example() -> None:
    b = _s([0.02, -0.01, 0.03, -0.02])
    p = b / 2
    assert up_capture(p, b, periods_per_year=P) == pytest.approx(0.4662417739, abs=1e-9)
    assert down_capture(p, b, periods_per_year=P) == pytest.approx(0.5205729851, abs=1e-9)


def test_identical_series_capture_one() -> None:
    b = _s([0.02, -0.01, 0.03, -0.02, 0.0])
    assert up_capture(b, b, periods_per_year=P) == pytest.approx(1.0)
    assert down_capture(b, b, periods_per_year=P) == pytest.approx(1.0)


def test_capture_without_up_or_down_periods_is_undefined() -> None:
    b = _s([0.01, 0.02, 0.0])
    with pytest.raises(UndefinedMetricError, match="down"):
        down_capture(b, b, periods_per_year=P)
    with pytest.raises(UndefinedMetricError, match="up"):
        up_capture(-b, -b, periods_per_year=P)


def test_capture_with_wiped_out_portfolio_is_undefined() -> None:
    b = _s([-0.10, 0.05])
    p = _s([-1.0, 0.05])
    with pytest.raises(UndefinedMetricError, match="wealth"):
        down_capture(p, b, periods_per_year=P)


# --------------------------------------------------------------------------- alignment
def test_benchmark_must_share_the_index() -> None:
    p = _s([0.01, 0.02, 0.03])
    b = _s([0.01, 0.02, 0.03], start="2026-02-28")
    for func in (tracking_error, information_ratio, capm_regression, up_capture, down_capture):
        with pytest.raises(AlignmentError):
            func(p, b, periods_per_year=P)


# --------------------------------------------------------------------------- active share
def test_active_share_hand_example() -> None:
    wp = pd.Series({"A": 0.5, "B": 0.5})
    wb = pd.Series({"A": 0.25, "B": 0.25, "C": 0.5})
    assert active_share(wp, wb, weight_tolerance=1e-9) == pytest.approx(0.5)


def test_active_share_bounds() -> None:
    w = pd.Series({"A": 0.3, "B": 0.7})
    assert active_share(w, w, weight_tolerance=1e-9) == 0.0
    assert active_share(pd.Series({"X": 1.0}), pd.Series({"Y": 1.0}), weight_tolerance=1e-9) == 1.0


@pytest.mark.parametrize(
    ("weights", "match"),
    [
        (pd.Series({"A": 0.5, "B": 0.4}), "sum"),
        (pd.Series({"A": 1.2, "B": -0.2}), "negative"),
        (pd.Series({"A": 0.5, "B": np.nan}), "finite"),
        (pd.Series([0.5, 0.5], index=["A", "A"]), "duplicated"),
        (pd.Series([], dtype=float), "empty"),
    ],
)
def test_active_share_validation(weights: pd.Series, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        active_share(weights, pd.Series({"A": 1.0}), weight_tolerance=1e-6)


def test_active_share_never_renormalises() -> None:
    wp = pd.Series({"A": 0.495, "B": 0.495})  # sums to 0.99
    with pytest.raises(ValidationError, match="sum"):
        active_share(wp, pd.Series({"A": 1.0}), weight_tolerance=0.005)
    assert active_share(wp, pd.Series({"A": 1.0}), weight_tolerance=0.02) == pytest.approx(0.5)


def test_weight_tolerance_validation() -> None:
    w = pd.Series({"A": 1.0})
    with pytest.raises(ValidationError, match="weight_tolerance"):
        active_share(w, w, weight_tolerance=-1.0)
