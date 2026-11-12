r"""Panel regression with entity fixed effects and cluster-robust standard errors.

Model: :math:`y_{it}=\alpha_i+x_{it}^\top\beta+\varepsilon_{it}`. The fixed effects are absorbed
by the within transformation (each variable minus its entity mean), which gives the same
:math:`\hat\beta` and residuals as OLS with one dummy per entity (Frisch-Waugh-Lovell).

Covariance clustered by an explicit grouping :math:`g` (e.g. the month, for cross-sectional
correlation): :math:`\hat V=c\,(\tilde X^\top\tilde X)^{-1}\big(\sum_g \tilde X_g^\top e_g
e_g^\top\tilde X_g\big)(\tilde X^\top\tilde X)^{-1}` with
:math:`c=\frac{G}{G-1}\frac{N-1}{N-K-E}`, where :math:`K` counts the regressors and :math:`E` the
absorbed entity effects, as in statsmodels' OLS with dummies and ``cov_type="cluster"``.
Inference is Student-t with :math:`G-1` degrees of freedom. Rows are observations; the index is
not required to be a time index.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sps

from qrlab.core.errors import ValidationError

__all__ = ["LinearContrast", "PanelResult", "contrast", "fixed_effects_ols"]


@dataclass(frozen=True)
class PanelResult:
    """Fixed-effects estimates with cluster-robust inference."""

    params: pd.Series
    std_errors: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    covariance: pd.DataFrame
    nobs: int
    n_entities: int
    n_clusters: int


@dataclass(frozen=True)
class LinearContrast:
    r"""Test of :math:`w^\top\beta = 0` (two-sided)."""

    estimate: float
    std_error: float
    tvalue: float
    pvalue: float


def fixed_effects_ols(
    y: pd.Series, x: pd.DataFrame, *, entity: pd.Series, cluster: pd.Series
) -> PanelResult:
    """Regress ``y`` on ``x`` with ``entity`` fixed effects; errors clustered by ``cluster``.

    Raises
    ------
    ValidationError
        For misaligned inputs, missing or non-finite values, fewer than two clusters, too few
        observations, or regressors that are constant within every entity (absorbed).
    """
    for name, obj in (("y", y), ("entity", entity), ("cluster", cluster)):
        if not isinstance(obj, pd.Series):
            raise ValidationError(f"{name} must be a pandas Series")
    given: object = x
    if not isinstance(given, pd.DataFrame) or x.shape[1] == 0:
        raise ValidationError("x must be a DataFrame with at least one regressor")
    if not (y.index.equals(x.index) and y.index.equals(entity.index)):
        raise ValidationError("y, x, entity and cluster must share the same index")
    if not y.index.equals(cluster.index):
        raise ValidationError("y, x, entity and cluster must share the same index")
    if entity.isna().any() or cluster.isna().any():
        raise ValidationError("entity and cluster labels must not be missing")
    values_y = y.to_numpy(dtype=np.float64)
    values_x = x.to_numpy(dtype=np.float64)
    if not (np.all(np.isfinite(values_y)) and np.all(np.isfinite(values_x))):
        raise ValidationError("y and x must be finite, without missing values")
    entities = pd.factorize(entity)[0]
    groups = pd.factorize(cluster)[0]
    n, k = values_x.shape
    e_count = int(np.max(entities)) + 1
    g_count = int(np.max(groups)) + 1
    if g_count < 2:
        raise ValidationError("at least two clusters are required")
    if n - k - e_count < 1:
        raise ValidationError(f"{n} observations for {k} regressors and {e_count} entities")
    y_tilde = values_y - _group_means(values_y[:, None], entities)[:, 0]
    x_tilde = values_x - _group_means(values_x, entities)
    xtx = x_tilde.T @ x_tilde
    if np.linalg.matrix_rank(xtx) < k:
        raise ValidationError("regressors are collinear or absorbed by the entity effects")
    bread = np.linalg.inv(xtx)
    beta = bread @ x_tilde.T @ y_tilde
    resid = y_tilde - x_tilde @ beta
    scores = np.zeros((g_count, k))
    np.add.at(scores, groups, x_tilde * resid[:, None])
    correction = g_count / (g_count - 1) * (n - 1) / (n - k - e_count)
    cov = correction * bread @ (scores.T @ scores) @ bread
    se = np.sqrt(np.diag(cov))
    t = beta / se
    p = 2.0 * sps.t.sf(np.abs(t), g_count - 1)
    names = [str(c) for c in x.columns]
    return PanelResult(
        params=pd.Series(beta, index=names, name="params"),
        std_errors=pd.Series(se, index=names, name="std_errors"),
        tvalues=pd.Series(t, index=names, name="tvalues"),
        pvalues=pd.Series(p, index=names, name="pvalues"),
        covariance=pd.DataFrame(cov, index=names, columns=names),
        nobs=n,
        n_entities=e_count,
        n_clusters=g_count,
    )


def contrast(result: PanelResult, weights: pd.Series) -> LinearContrast:
    """Test the linear combination ``weights @ params`` with the clustered covariance."""
    if set(weights.index) != set(result.params.index):
        raise ValidationError("contrast weights must name every coefficient")
    w = weights.reindex(result.params.index).to_numpy(dtype=np.float64)
    estimate = float(w @ result.params.to_numpy())
    variance = float(w @ result.covariance.to_numpy() @ w)
    if not variance > 0:
        raise ValidationError("the contrast has zero variance")
    se = math.sqrt(variance)
    t = estimate / se
    p = float(2.0 * sps.t.sf(abs(t), result.n_clusters - 1))
    return LinearContrast(estimate=estimate, std_error=se, tvalue=t, pvalue=p)


def _group_means(values: np.ndarray, codes: np.ndarray) -> np.ndarray:
    sums = np.zeros((int(np.max(codes)) + 1, values.shape[1]))
    np.add.at(sums, codes, values)
    counts = np.bincount(codes).astype(np.float64)
    means: np.ndarray = (sums / counts[:, None])[codes]
    return means
