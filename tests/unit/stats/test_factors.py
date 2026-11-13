"""Rolling regressions and factor exposures. Synthetic, seeded data only."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.stats.factors import FactorSet, factor_exposures
from qrlab.stats.regression import CovType, newey_west_lags, ols
from qrlab.stats.rolling import rolling_ols

P = 12


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2000-01-31", periods=n, freq="ME")


@pytest.fixture
def factor_data(rng: np.random.Generator) -> tuple[pd.Series, pd.DataFrame]:
    """Return y = 0.002 + 1.1 MKT + 0.3 SMB - 0.2 HML + 0.1 MOM + noise (monthly, 360 months)."""
    n = 360
    factors = pd.DataFrame(
        rng.normal(0.0, [0.045, 0.03, 0.03, 0.02, 0.02, 0.04], size=(n, 6)),
        index=_idx(n),
        columns=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "WML"],
    )
    factors["RF"] = 0.002
    y = (
        0.002
        + 1.1 * factors["Mkt-RF"]
        + 0.3 * factors["SMB"]
        - 0.2 * factors["HML"]
        + 0.1 * factors["WML"]
        + rng.normal(0, 0.005, n)
    )
    return y.rename("excess"), factors


# --------------------------------------------------------------------------- factor exposures
def test_known_answer_recovery(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    result = factor_exposures(
        y,
        factors,
        model=FactorSet.FF3_MOM,
        periods_per_year=P,
        cov_type=CovType.HAC,
        hac_lags=newey_west_lags(len(y)),
        momentum_column="WML",
    )
    assert list(result.betas.index) == ["Mkt-RF", "SMB", "HML", "MOM"]
    np.testing.assert_allclose(result.betas.to_numpy(), [1.1, 0.3, -0.2, 0.1], atol=0.03)
    assert result.alpha == pytest.approx(0.002, abs=0.001)
    assert result.alpha_annualised == pytest.approx(result.alpha * P)
    assert result.alpha_se_annualised == pytest.approx(result.regression.std_errors["const"] * P)
    assert result.r_squared > 0.95
    assert result.nobs == 360
    assert result.model is FactorSet.FF3_MOM


def test_equals_plain_ols_on_the_same_columns(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    result = factor_exposures(
        y, factors, model=FactorSet.FF5, periods_per_year=P, cov_type=CovType.HC1, hac_lags=None,
        momentum_column=None,
    )  # fmt: skip
    reference = ols(
        y, factors[["Mkt-RF", "SMB", "HML", "RMW", "CMA"]], add_intercept=True,
        cov_type=CovType.HC1, hac_lags=None,
    )  # fmt: skip
    np.testing.assert_allclose(
        result.betas.to_numpy(), reference.params.iloc[1:].to_numpy(), rtol=1e-14
    )
    np.testing.assert_allclose(result.tvalues.to_numpy(), reference.tvalues.to_numpy(), rtol=1e-14)


def test_capm_uses_only_the_market(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    result = factor_exposures(
        y, factors, model=FactorSet.CAPM, periods_per_year=P, cov_type=CovType.NONROBUST,
        hac_lags=None, momentum_column=None,
    )  # fmt: skip
    assert list(result.betas.index) == ["Mkt-RF"]


def test_us_momentum_column_name(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    us = factors.rename(columns={"WML": "Mom"})
    result = factor_exposures(
        y, us, model=FactorSet.FF5_MOM, periods_per_year=P, cov_type=CovType.NONROBUST,
        hac_lags=None, momentum_column="Mom",
    )  # fmt: skip
    assert list(result.betas.index)[-1] == "MOM"


@pytest.mark.parametrize(
    ("model", "momentum_column", "match"),
    [
        (FactorSet.FF3_MOM, None, "momentum_column"),
        (FactorSet.FF3, "WML", "momentum_column"),
        (FactorSet.FF3_MOM, "UMD", "UMD"),
    ],
)
def test_momentum_column_rules(
    factor_data: tuple[pd.Series, pd.DataFrame],
    model: FactorSet,
    momentum_column: str | None,
    match: str,
) -> None:
    y, factors = factor_data
    with pytest.raises(ValidationError, match=match):
        factor_exposures(
            y, factors, model=model, periods_per_year=P, cov_type=CovType.NONROBUST, hac_lags=None,
            momentum_column=momentum_column,
        )  # fmt: skip


def test_missing_factor_column_raises(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    with pytest.raises(ValidationError, match="RMW"):
        factor_exposures(
            y, factors.drop(columns="RMW"), model=FactorSet.FF5, periods_per_year=P,
            cov_type=CovType.NONROBUST, hac_lags=None, momentum_column=None,
        )  # fmt: skip


def test_validation_of_model_and_periods(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    with pytest.raises(ValidationError, match="FactorSet"):
        factor_exposures(
            y, factors, model="FF3", periods_per_year=P, cov_type=CovType.NONROBUST,  # type: ignore[arg-type]
            hac_lags=None, momentum_column=None,
        )  # fmt: skip
    with pytest.raises(ValidationError, match="periods_per_year"):
        factor_exposures(
            y, factors, model=FactorSet.FF3, periods_per_year=0, cov_type=CovType.NONROBUST,
            hac_lags=None, momentum_column=None,
        )  # fmt: skip


# --------------------------------------------------------------------------- rolling regressions
def test_rolling_matches_fitting_each_window(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    x = factors[["Mkt-RF", "SMB"]]
    result = rolling_ols(y, x, window=60, add_intercept=True, cov_type=CovType.HAC, hac_lags=3)
    assert len(result.params) == len(y) - 59
    assert result.params.index[0] == y.index[59]  # labelled by window end
    for end in (59, 200, len(y) - 1):
        window = slice(end - 59, end + 1)
        reference = ols(
            y.iloc[window], x.iloc[window], add_intercept=True, cov_type=CovType.HAC, hac_lags=3
        )
        label = y.index[end]
        np.testing.assert_allclose(
            result.params.loc[label].to_numpy(), reference.params.to_numpy(), rtol=1e-12
        )
        np.testing.assert_allclose(
            result.std_errors.loc[label].to_numpy(), reference.std_errors.to_numpy(), rtol=1e-12
        )


def test_rolling_has_no_look_ahead(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    x = factors[["Mkt-RF"]]
    base = rolling_ols(
        y, x, window=36, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None
    )
    changed_future = y.copy()
    changed_future.iloc[200:] += 1.0  # shock everything after the 200th observation
    shocked = rolling_ols(
        changed_future, x, window=36, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None
    )
    cutoff = y.index[199]
    pd.testing.assert_frame_equal(base.params.loc[:cutoff], shocked.params.loc[:cutoff])
    assert not np.allclose(base.params.loc[y.index[200]], shocked.params.loc[y.index[200]])


def test_rolling_window_validation(factor_data: tuple[pd.Series, pd.DataFrame]) -> None:
    y, factors = factor_data
    x = factors[["Mkt-RF", "SMB"]]
    bad_windows: list[object] = [3, 0, 1.5, len(y) + 1]
    for bad in bad_windows:
        with pytest.raises(ValidationError, match="window"):
            rolling_ols(
                y,
                x,
                window=bad,  # type: ignore[arg-type]
                add_intercept=True,
                cov_type=CovType.NONROBUST,
                hac_lags=None,
            )


def test_periods_per_year_must_match_the_dates(
    factor_data: tuple[pd.Series, pd.DataFrame],
) -> None:
    """Design note 7.1: monthly excess returns annualised with 252 are refused."""
    y, factors = factor_data
    with pytest.raises(ValidationError, match="dates are monthly"):
        factor_exposures(
            y,
            factors,
            model=FactorSet.FF3_MOM,
            periods_per_year=252,
            cov_type=CovType.HAC,
            hac_lags=6,
            momentum_column="WML",
        )
