"""Statistical inference for financial time series.

Returns are rarely independent, so inference here is explicit about dependence:

- ``regression``: :func:`ols` with classical, White (HC1) and Newey-West (HAC) standard
  errors; lags always explicit (:func:`newey_west_lags` is a documented rule, never implicit).
- ``rolling``: :func:`rolling_ols` on trailing windows only (no look-ahead).
- ``factors``: :func:`factor_exposures` for CAPM, Fama-French 3/5 factors and momentum;
  returns and factors must be excess returns in the same currency.
- ``bootstrap``: :func:`stationary_bootstrap` (Politis-Romano) with a required seeded generator.

Planned for phase 5.1: multiple-testing corrections and Sharpe-ratio inference.
"""

from qrlab.stats.bootstrap import (
    BootstrapResult,
    stationary_bootstrap,
    stationary_bootstrap_indices,
)
from qrlab.stats.factors import FactorModel, FactorResult, factor_exposures
from qrlab.stats.regression import CovType, OlsResult, newey_west_lags, ols
from qrlab.stats.rolling import RollingResult, rolling_ols

__all__ = [
    "BootstrapResult",
    "CovType",
    "FactorModel",
    "FactorResult",
    "OlsResult",
    "RollingResult",
    "factor_exposures",
    "newey_west_lags",
    "ols",
    "rolling_ols",
    "stationary_bootstrap",
    "stationary_bootstrap_indices",
]
