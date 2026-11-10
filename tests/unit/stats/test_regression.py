"""OLS with classical, White (HC1) and Newey-West (HAC) standard errors.

Hand example (design note): y = (2, 3, 5) on x = (1, 2, 3) with an intercept gives
beta = 3/2, alpha = 1/3, residuals (1/6, -1/3, 1/6), SSR = 1/6, se(beta) = 0.288675,
se(alpha) = 0.623610.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.stats.regression import CovType, newey_west_lags, ols


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2000-01-31", periods=n, freq="ME")


def _xy(x: list[float], y: list[float]) -> tuple[pd.Series, pd.DataFrame]:
    index = _idx(len(y))
    return pd.Series(y, index=index, name="y"), pd.DataFrame({"x": x}, index=index)


# --------------------------------------------------------------------------- hand example
def test_classical_ols_hand_example() -> None:
    y, x = _xy([1, 2, 3], [2, 3, 5])
    result = ols(y, x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)
    assert result.params["const"] == pytest.approx(1 / 3, abs=1e-14)
    assert result.params["x"] == pytest.approx(1.5, abs=1e-14)
    np.testing.assert_allclose(result.residuals.to_numpy(), [1 / 6, -1 / 3, 1 / 6], atol=1e-14)
    assert result.std_errors["x"] == pytest.approx(math.sqrt(1 / 12), abs=1e-12)
    assert result.std_errors["const"] == pytest.approx(0.6236095645, abs=1e-9)
    assert result.nobs == 3
    assert result.df_resid == 1
    assert result.cov_type is CovType.NONROBUST


def test_newey_west_lag_rule() -> None:
    assert newey_west_lags(120) == 4
    assert newey_west_lags(240) == 4
    assert newey_west_lags(1000) == 6
    with pytest.raises(ValidationError):
        newey_west_lags(0)


# --------------------------------------------------------------------------- cross-checks
@pytest.fixture
def regression_data(rng: np.random.Generator) -> tuple[pd.Series, pd.DataFrame]:
    n = 240
    x = pd.DataFrame(rng.normal(0, 0.04, size=(n, 2)), index=_idx(n), columns=["mkt", "smb"])
    noise = np.zeros(n)
    shocks = rng.normal(0, 0.01, n)
    for t in range(1, n):
        noise[t] = 0.5 * noise[t - 1] + shocks[t]
    y = pd.Series(0.002 + 1.1 * x["mkt"] + 0.3 * x["smb"] + noise, index=x.index, name="y")
    return y, x


@pytest.mark.parametrize(
    ("cov_type", "lags", "sm_kwargs"),
    [
        (CovType.NONROBUST, None, {}),
        (CovType.HC1, None, {"cov_type": "HC1"}),
        (CovType.HAC, 4, {"cov_type": "HAC", "cov_kwds": {"maxlags": 4, "use_correction": True}}),
    ],
)
def test_matches_statsmodels(
    regression_data: tuple[pd.Series, pd.DataFrame],
    cov_type: CovType,
    lags: int | None,
    sm_kwargs: dict[str, object],
) -> None:
    y, x = regression_data
    result = ols(y, x, add_intercept=True, cov_type=cov_type, hac_lags=lags)
    reference = sm.OLS(y, sm.add_constant(x)).fit(use_t=True, **sm_kwargs)
    np.testing.assert_allclose(result.params.to_numpy(), reference.params.to_numpy(), rtol=1e-12)
    np.testing.assert_allclose(result.std_errors.to_numpy(), reference.bse.to_numpy(), rtol=1e-12)
    np.testing.assert_allclose(result.pvalues.to_numpy(), reference.pvalues.to_numpy(), rtol=1e-10)
    assert result.r_squared == pytest.approx(reference.rsquared, rel=1e-12)
    assert result.r_squared_adj == pytest.approx(reference.rsquared_adj, rel=1e-12)


def test_newey_west_matches_independent_formula(
    regression_data: tuple[pd.Series, pd.DataFrame],
) -> None:
    """Bartlett-kernel HAC with n/(n-k) correction, written out with NumPy."""
    y, x = regression_data
    lags = 4
    design = np.column_stack([np.ones(len(y)), x.to_numpy()])
    beta = np.linalg.solve(design.T @ design, design.T @ y.to_numpy())
    u = y.to_numpy() - design @ beta
    scores = design * u[:, None]
    meat = scores.T @ scores
    for lag in range(1, lags + 1):
        weight = 1 - lag / (lags + 1)
        gamma = scores[lag:].T @ scores[:-lag]
        meat += weight * (gamma + gamma.T)
    bread = np.linalg.inv(design.T @ design)
    n, k = design.shape
    cov = bread @ meat @ bread * n / (n - k)
    result = ols(y, x, add_intercept=True, cov_type=CovType.HAC, hac_lags=lags)
    np.testing.assert_allclose(result.std_errors.to_numpy(), np.sqrt(np.diag(cov)), rtol=1e-10)


def test_interval_uses_t_distribution(regression_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, x = regression_data
    result = ols(y, x, add_intercept=True, cov_type=CovType.HAC, hac_lags=4)
    reference = sm.OLS(y, sm.add_constant(x)).fit(
        cov_type="HAC", cov_kwds={"maxlags": 4, "use_correction": True}, use_t=True
    )
    low, high = result.interval(0.90)
    ref = reference.conf_int(alpha=0.10)
    np.testing.assert_allclose(low.to_numpy(), ref.iloc[:, 0].to_numpy(), rtol=1e-10)
    np.testing.assert_allclose(high.to_numpy(), ref.iloc[:, 1].to_numpy(), rtol=1e-10)


def test_without_intercept(regression_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, x = regression_data
    result = ols(y, x, add_intercept=False, cov_type=CovType.NONROBUST, hac_lags=None)
    reference = sm.OLS(y, x).fit()
    assert list(result.params.index) == ["mkt", "smb"]
    np.testing.assert_allclose(result.params.to_numpy(), reference.params.to_numpy(), rtol=1e-12)


def test_hac_coverage_beats_classical_with_autocorrelated_errors(rng: np.random.Generator) -> None:
    """Known answer: with AR(1) errors and an AR(1) regressor, classical intervals undercover."""
    n, runs, beta = 240, 400, 1.1
    index = _idx(n)
    covered = {CovType.NONROBUST: 0, CovType.HAC: 0}
    for _ in range(runs):
        x = np.zeros(n)
        e = np.zeros(n)
        ex, ee = rng.normal(0, 1, n), rng.normal(0, 1, n)
        for t in range(1, n):
            x[t] = 0.7 * x[t - 1] + ex[t]
            e[t] = 0.7 * e[t - 1] + ee[t]
        y = pd.Series(beta * x + e, index=index)
        frame = pd.DataFrame({"x": x}, index=index)
        for cov_type, lags in ((CovType.NONROBUST, None), (CovType.HAC, newey_west_lags(n))):
            low, high = ols(
                y, frame, add_intercept=True, cov_type=cov_type, hac_lags=lags
            ).interval(0.95)
            covered[cov_type] += low["x"] <= beta <= high["x"]
    assert covered[CovType.NONROBUST] / runs < 0.85
    assert 0.85 <= covered[CovType.HAC] / runs <= 0.98
    assert covered[CovType.HAC] > covered[CovType.NONROBUST]


# --------------------------------------------------------------------------- validation
def test_hac_lags_rules() -> None:
    y, x = _xy([1, 2, 3, 4, 5], [2, 3, 5, 4, 6])
    with pytest.raises(ValidationError, match="hac_lags"):
        ols(y, x, add_intercept=True, cov_type=CovType.HAC, hac_lags=None)
    with pytest.raises(ValidationError, match="hac_lags"):
        ols(y, x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=2)
    with pytest.raises(ValidationError, match="hac_lags"):
        ols(y, x, add_intercept=True, cov_type=CovType.HAC, hac_lags=-1)


def test_collinear_regressors_raise() -> None:
    index = _idx(5)
    y = pd.Series([1.0, 2, 3, 4, 6], index=index)
    x = pd.DataFrame({"a": [1.0, 2, 3, 4, 5], "b": [2.0, 4, 6, 8, 10]}, index=index)
    with pytest.raises(ValidationError, match="rank"):
        ols(y, x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)


def test_constant_column_with_intercept_raises() -> None:
    index = _idx(4)
    y = pd.Series([1.0, 2, 3, 5], index=index)
    x = pd.DataFrame({"a": [1.0, 2, 3, 4], "c": [1.0, 1, 1, 1]}, index=index)
    with pytest.raises(ValidationError, match="constant"):
        ols(y, x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)


def test_too_few_observations_raise() -> None:
    y, x = _xy([1, 2], [2, 3])
    with pytest.raises(ValidationError, match="observations"):
        ols(y, x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)


def test_misaligned_and_nan_inputs_raise() -> None:
    y, x = _xy([1, 2, 3, 4], [2, 3, 5, 4])
    with pytest.raises(AlignmentError):
        ols(y.iloc[1:], x.iloc[:-1], add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)
    with pytest.raises(ValidationError, match="NaN"):
        ols(y.where(y > 2), x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)


def test_regressors_needed_and_enum_checked() -> None:
    y, x = _xy([1, 2, 3, 4], [2, 3, 5, 4])
    with pytest.raises(ValidationError, match="regressor"):
        ols(y, x.iloc[:, []], add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)
    with pytest.raises(ValidationError, match="CovType"):
        ols(y, x, add_intercept=True, cov_type="hac", hac_lags=None)  # type: ignore[arg-type]


def test_interval_confidence_validation() -> None:
    y, x = _xy([1, 2, 3, 4], [2, 3, 5, 4])
    result = ols(y, x, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)
    with pytest.raises(ValidationError, match="confidence"):
        result.interval(1.0)
