r"""Ordinary least squares with classical, White and Newey-West standard errors.

Returns are rarely independent: volatility clusters and overlapping or smoothed returns are
autocorrelated. Classical standard errors then understate uncertainty. ``CovType.HAC``
(Newey and West, 1987) is robust to both heteroskedasticity and autocorrelation and is the
recommended choice for return regressions; the number of lags is always explicit.

Fixed conventions (documented, not parameters): Bartlett kernel for HAC, small-sample scaling
:math:`n/(n-k)` for HC1 and HAC, and Student-t inference with :math:`n-k` degrees of freedom.
Estimation wraps statsmodels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as sps

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_frame, validate_series

__all__ = ["CovType", "OlsResult", "newey_west_lags", "ols"]

INTERCEPT = "const"


class CovType(Enum):
    """Covariance estimator for the coefficients."""

    NONROBUST = "nonrobust"  # classical: homoskedastic, uncorrelated errors
    HC1 = "hc1"  # White (1980), heteroskedasticity-robust, n/(n-k) scaling
    HAC = "hac"  # Newey-West (1987), Bartlett kernel, n/(n-k) scaling


@dataclass(frozen=True)
class OlsResult:
    """Estimates and inference of an OLS regression.

    Attributes
    ----------
    params, std_errors, tvalues, pvalues
        Indexed by regressor name; the intercept, if any, is ``"const"``.
    r_squared, r_squared_adj
        Coefficient of determination and its adjusted version.
    residuals
        Residuals indexed like the observations.
    nobs, df_resid
        Number of observations and residual degrees of freedom.
    cov_type, hac_lags
        Covariance estimator used and, for HAC, the number of lags.
    """

    params: pd.Series
    std_errors: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    r_squared: float
    r_squared_adj: float
    residuals: pd.Series
    nobs: int
    df_resid: int
    cov_type: CovType
    hac_lags: int | None

    def interval(self, confidence: float) -> tuple[pd.Series, pd.Series]:
        """Two-sided Student-t confidence interval (lower, upper) for every coefficient."""
        if not 0.0 < confidence < 1.0:
            raise ValidationError(f"confidence must be in (0, 1), got {confidence}")
        q = float(sps.t.ppf(0.5 + confidence / 2.0, self.df_resid))
        return self.params - q * self.std_errors, self.params + q * self.std_errors


def newey_west_lags(n: int) -> int:
    r"""Rule-of-thumb lag length :math:`\lfloor 4 (n/100)^{2/9} \rfloor` (Newey and West, 1994).

    A documented rule to pass explicitly as ``hac_lags``; it is never applied implicitly.
    """
    if type(n) is not int or n < 1:
        raise ValidationError(f"n must be a positive int, got {n!r}")
    return math.floor(4.0 * float((n / 100.0) ** (2.0 / 9.0)))


def ols(
    y: pd.Series,
    x: pd.DataFrame,
    *,
    add_intercept: bool,
    cov_type: CovType,
    hac_lags: int | None,
) -> OlsResult:
    """Regress ``y`` on the columns of ``x``.

    Parameters
    ----------
    y, x
        Dependent variable and regressors with identical indexes and no NaN.
    add_intercept
        Add a constant named ``"const"``. ``x`` must then not contain a constant column.
    cov_type
        Covariance estimator (see :class:`CovType`).
    hac_lags
        Number of lags; required for ``HAC`` and forbidden otherwise.

    Raises
    ------
    ValidationError
        For misaligned or missing data, too few observations, collinear regressors, a constant
        column together with an intercept, or inconsistent ``hac_lags``.
    """
    if not isinstance(cov_type, CovType):
        raise ValidationError(f"cov_type must be a CovType, got {cov_type!r}")
    _check_lags(cov_type, hac_lags)
    target = validate_series(y, nan_policy=NanPolicy.RAISE, name="y")
    regressors = validate_frame(x, nan_policy=NanPolicy.RAISE, name="x")
    require_same_index(target, regressors)
    if regressors.shape[1] == 0:
        raise ValidationError("at least one regressor is required")
    if add_intercept:
        constant = [c for c in regressors.columns if float(np.ptp(regressors[c].to_numpy())) == 0.0]
        if constant:
            raise ValidationError(f"constant columns {constant} together with an intercept")
        design = sm.add_constant(regressors, has_constant="raise")
    else:
        design = regressors
    n, k = design.shape
    if n <= k:
        raise ValidationError(f"{n} observations for {k} coefficients: need more observations")
    rank = int(np.linalg.matrix_rank(design.to_numpy()))
    if rank < k:
        raise ValidationError(f"regressors are collinear: rank {rank} < {k} coefficients")

    model = sm.OLS(target, design)
    if cov_type is CovType.NONROBUST:
        fit = model.fit(use_t=True)
    elif cov_type is CovType.HC1:
        fit = model.fit(cov_type="HC1", use_t=True)
    else:
        fit = model.fit(
            cov_type="HAC", cov_kwds={"maxlags": hac_lags, "use_correction": True}, use_t=True
        )
    return OlsResult(
        params=pd.Series(fit.params, index=design.columns, name="params"),
        std_errors=pd.Series(fit.bse, index=design.columns, name="std_errors"),
        tvalues=pd.Series(fit.tvalues, index=design.columns, name="tvalues"),
        pvalues=pd.Series(fit.pvalues, index=design.columns, name="pvalues"),
        r_squared=float(fit.rsquared),
        r_squared_adj=float(fit.rsquared_adj),
        residuals=pd.Series(fit.resid, index=target.index, name="residuals"),
        nobs=n,
        df_resid=n - k,
        cov_type=cov_type,
        hac_lags=hac_lags,
    )


def _check_lags(cov_type: CovType, hac_lags: object) -> None:
    if cov_type is CovType.HAC:
        if type(hac_lags) is not int or hac_lags < 0:
            raise ValidationError(f"hac_lags must be a non-negative int for HAC, got {hac_lags!r}")
    elif hac_lags is not None:
        raise ValidationError("hac_lags is only used with CovType.HAC")
