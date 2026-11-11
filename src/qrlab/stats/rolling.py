"""Rolling (trailing-window) regressions without look-ahead.

The estimate labelled ``t`` uses observations ``t - window + 1 ... t`` only, so it is known
after ``t``. Dates before the first full window have no estimate and are not returned.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.series import NanPolicy, require_same_index, validate_frame, validate_series
from qrlab.stats.regression import CovType, ols

__all__ = ["RollingResult", "rolling_ols"]


@dataclass(frozen=True)
class RollingResult:
    """Coefficients and standard errors per window, indexed by the window's last date."""

    params: pd.DataFrame
    std_errors: pd.DataFrame
    window: int
    cov_type: CovType
    hac_lags: int | None


def rolling_ols(
    y: pd.Series,
    x: pd.DataFrame,
    *,
    window: int,
    add_intercept: bool,
    cov_type: CovType,
    hac_lags: int | None,
) -> RollingResult:
    """Fit :func:`qrlab.stats.regression.ols` on every trailing window of ``window`` rows.

    ``window`` must be at least the number of coefficients plus 2 and at most the sample size.
    """
    target = validate_series(y, nan_policy=NanPolicy.RAISE, name="y")
    regressors = validate_frame(x, nan_policy=NanPolicy.RAISE, name="x")
    require_same_index(target, regressors)
    k = regressors.shape[1] + int(add_intercept)
    if type(window) is not int or not k + 2 <= window <= len(target):
        raise ValidationError(
            f"window must be an int between {k + 2} and {len(target)}, got {window!r}"
        )
    params: dict[pd.Timestamp, pd.Series] = {}
    errors: dict[pd.Timestamp, pd.Series] = {}
    for end in range(window, len(target) + 1):
        rows = slice(end - window, end)
        fit = ols(
            target.iloc[rows],
            regressors.iloc[rows],
            add_intercept=add_intercept,
            cov_type=cov_type,
            hac_lags=hac_lags,
        )
        label = pd.Timestamp(target.index[end - 1])
        params[label] = fit.params
        errors[label] = fit.std_errors
    return RollingResult(
        params=pd.DataFrame(params).T,
        std_errors=pd.DataFrame(errors).T,
        window=window,
        cov_type=cov_type,
        hac_lags=hac_lags,
    )
