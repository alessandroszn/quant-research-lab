"""Statistical inference for financial time series.

Returns are rarely independent, so inference here is explicit about dependence:

- ``regression``: :func:`ols` with classical, White (HC1) and Newey-West (HAC) standard
  errors; lags always explicit (:func:`newey_west_lags` is a documented rule, never implicit).
- ``rolling``: :func:`rolling_ols` on trailing windows only (no look-ahead).
- ``factors``: :func:`factor_exposures` for CAPM, Fama-French 3/5 factors and momentum;
  returns and factors must be excess returns in the same currency.
- ``bootstrap``: :func:`stationary_bootstrap` (Politis-Romano) with a required seeded generator.

- ``multiple_testing``: :func:`adjust_pvalues` with Holm, Benjamini-Hochberg and
  Benjamini-Yekutieli corrections.
- ``panel``: :func:`fixed_effects_ols` with entity fixed effects and cluster-robust errors.

Sharpe-ratio inference (PSR, DSR, tests of differences) is in :mod:`qrlab.metrics`.
"""

from qrlab.stats.bootstrap import (
    BootstrapResult,
    stationary_bootstrap,
    stationary_bootstrap_indices,
)
from qrlab.stats.factors import FactorResult, FactorSet, factor_exposures
from qrlab.stats.multiple_testing import Correction, CorrectionResult, adjust_pvalues
from qrlab.stats.panel import LinearContrast, PanelResult, contrast, fixed_effects_ols
from qrlab.stats.regression import CovType, OlsResult, newey_west_lags, ols
from qrlab.stats.rolling import RollingResult, rolling_ols

__all__ = [
    "BootstrapResult",
    "Correction",
    "CorrectionResult",
    "CovType",
    "FactorResult",
    "FactorSet",
    "LinearContrast",
    "OlsResult",
    "PanelResult",
    "RollingResult",
    "adjust_pvalues",
    "contrast",
    "factor_exposures",
    "fixed_effects_ols",
    "newey_west_lags",
    "ols",
    "rolling_ols",
    "stationary_bootstrap",
    "stationary_bootstrap_indices",
]
