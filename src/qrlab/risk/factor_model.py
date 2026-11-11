r"""A time-series factor risk model.

Each asset is regressed by OLS on the factors with an intercept,
:math:`r_i = a_i + B_i^\top f + e_i`. The covariance of asset returns is
:math:`\Sigma = B\Sigma_f B^\top + D`, with :math:`\Sigma_f` from a covariance estimator the caller
chooses and :math:`D` the diagonal of residual variances (``ddof = 1 + number of factors``).

Portfolio volatility splits into factor and specific parts:
:math:`\sigma_p = \sum_k (B^\top w)_k (\Sigma_f B^\top w)_k/\sigma_p + \sum_i w_i^2 D_i/\sigma_p`.

Asset and factor returns must share the same index. When the factors are excess returns, the
asset returns passed in must be excess returns too.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy, require_same_index, validate_frame
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.risk._inputs import asset_returns, portfolio_weights
from qrlab.risk.covariance import CovarianceEstimate
from qrlab.stats.regression import CovType, ols

__all__ = ["FactorModel", "FactorRiskContributions", "factor_contributions", "fit_factor_model"]


@dataclass(frozen=True)
class FactorModel:
    """Estimated factor model.

    Attributes
    ----------
    betas
        Assets by factors.
    alphas
        Intercept per asset (per period).
    specific_variance
        Residual variance per asset.
    r_squared
        :math:`R^2` per asset.
    factor_covariance
        Covariance of the factors.
    n_obs, dropped_rows
        Observations used and dates removed for missing values.
    """

    betas: pd.DataFrame
    alphas: pd.Series
    specific_variance: pd.Series
    r_squared: pd.Series
    factor_covariance: CovarianceEstimate
    n_obs: int
    dropped_rows: int

    def covariance(self) -> CovarianceEstimate:
        r"""Return the model-implied asset covariance :math:`B\Sigma_f B^\top + D`."""
        b = self.betas.to_numpy()
        matrix = b @ self.factor_covariance.matrix.to_numpy() @ b.T
        matrix = matrix + np.diag(self.specific_variance.to_numpy())
        matrix = (matrix + matrix.T) / 2.0
        frame = pd.DataFrame(matrix, index=self.betas.index, columns=self.betas.index)
        return CovarianceEstimate(frame, "factor_model", self.n_obs, self.dropped_rows)


@dataclass(frozen=True)
class FactorRiskContributions:
    """Factor and specific contributions to portfolio volatility; they sum to ``total``."""

    total: float
    factor: pd.Series
    specific: pd.Series
    exposures: pd.Series


def fit_factor_model(
    returns: pd.DataFrame,
    factors: pd.DataFrame,
    *,
    kind: ReturnKind,
    missing: NanPolicy,
    factor_covariance: Callable[[pd.DataFrame], CovarianceEstimate],
) -> FactorModel:
    """Estimate betas by OLS per asset and combine them with a factor covariance.

    Parameters
    ----------
    returns, factors
        Simple asset and factor returns on the same dates.
    kind, missing
        Return kind (simple only) and the missing-value policy, applied to assets and factors
        together.
    factor_covariance
        Estimator for the factors, e.g.
        ``lambda f: sample_covariance(f, kind=ReturnKind.SIMPLE, missing=NanPolicy.RAISE)``.
    """
    factor_frame = validate_frame(factors, nan_policy=NanPolicy.KEEP, name="factors")
    require_same_index(returns, factor_frame)
    overlap = set(map(str, returns.columns)) & set(map(str, factor_frame.columns))
    if overlap:
        raise ValidationError(f"asset and factor names overlap: {sorted(overlap)}")
    joint, dropped = asset_returns(
        pd.concat([returns, factor_frame], axis=1),
        kind=kind,
        missing=missing,
        min_obs=factor_frame.shape[1] + 3,
    )
    assets = joint[returns.columns]
    f = joint[factor_frame.columns]
    betas, alphas, specific, r2 = {}, {}, {}, {}
    for asset in assets.columns:
        fit = ols(assets[asset], f, add_intercept=True, cov_type=CovType.NONROBUST, hac_lags=None)
        betas[asset] = fit.params.drop("const")
        alphas[asset] = float(fit.params["const"])
        specific[asset] = float(np.sum(fit.residuals.to_numpy() ** 2)) / fit.df_resid
        r2[asset] = fit.r_squared
    return FactorModel(
        betas=pd.DataFrame(betas).T.loc[assets.columns, f.columns],
        alphas=pd.Series(alphas),
        specific_variance=pd.Series(specific),
        r_squared=pd.Series(r2),
        factor_covariance=factor_covariance(f),
        n_obs=len(joint),
        dropped_rows=dropped,
    )


def factor_contributions(model: FactorModel, weights: pd.Series) -> FactorRiskContributions:
    """Split portfolio volatility into factor and specific contributions."""
    w = portfolio_weights(weights, model.betas.index)
    b = model.betas.to_numpy()
    sigma_f = model.factor_covariance.matrix.to_numpy()
    exposures = b.T @ w
    factor_var = sigma_f @ exposures
    specific_var = w**2 * model.specific_variance.to_numpy()
    variance = float(exposures @ factor_var) + float(specific_var.sum())
    if not variance > 0.0:
        raise UndefinedMetricError("portfolio volatility is zero: contributions are undefined")
    vol = math.sqrt(variance)
    return FactorRiskContributions(
        total=vol,
        factor=pd.Series(exposures * factor_var / vol, index=model.betas.columns),
        specific=pd.Series(specific_var / vol, index=model.betas.index),
        exposures=pd.Series(exposures, index=model.betas.columns),
    )
