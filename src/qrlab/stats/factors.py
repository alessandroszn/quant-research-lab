"""Factor exposures: CAPM, Fama-French 3 and 5 factors, with or without momentum.

Inputs are **excess** returns (the portfolio's returns minus the factor file's risk-free
rate) and factor returns **in the same currency** and frequency. Ken French factors are in USD:
convert EUR returns first with :func:`qrlab.core.returns.convert_return_currency`, otherwise
currency moves end up inside the betas. A series cannot carry its currency, so this is the
caller's documented responsibility.

Results report estimates, standard errors, t-statistics and p-values. They never label an
alpha "significant": testing many models or funds needs multiple-testing corrections (5.1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.stats.regression import INTERCEPT, CovType, OlsResult, ols

__all__ = ["FactorModel", "FactorResult", "factor_exposures"]

MOMENTUM = "MOM"


class FactorModel(Enum):
    """Factor sets.

    ``MOM`` stands for the momentum column (``Mom`` in US files, ``WML`` in Developed and
    Europe files), chosen with ``momentum_column``.
    """

    CAPM = ("Mkt-RF",)
    FF3 = ("Mkt-RF", "SMB", "HML")
    FF5 = ("Mkt-RF", "SMB", "HML", "RMW", "CMA")
    FF3_MOM = ("Mkt-RF", "SMB", "HML", MOMENTUM)
    FF5_MOM = ("Mkt-RF", "SMB", "HML", "RMW", "CMA", MOMENTUM)

    @property
    def uses_momentum(self) -> bool:
        """Whether the model includes the momentum factor."""
        return MOMENTUM in self.value


@dataclass(frozen=True)
class FactorResult:
    """Factor regression of excess returns.

    Attributes
    ----------
    model
        Factor set used.
    alpha, alpha_annualised, alpha_se_annualised
        Intercept per period, times periods per year (arithmetic), and its standard error.
    betas, std_errors
        Factor loadings and their standard errors (``MOM`` for momentum).
    tvalues, pvalues
        For the intercept (``const``) and every factor.
    r_squared, nobs
        Fit and number of observations.
    regression
        The underlying :class:`~qrlab.stats.regression.OlsResult`.
    """

    model: FactorModel
    alpha: float
    alpha_annualised: float
    alpha_se_annualised: float
    betas: pd.Series
    std_errors: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    r_squared: float
    nobs: int
    regression: OlsResult


def factor_exposures(
    excess_returns: pd.Series,
    factors: pd.DataFrame,
    *,
    model: FactorModel,
    periods_per_year: float,
    cov_type: CovType,
    hac_lags: int | None,
    momentum_column: str | None,
) -> FactorResult:
    """Regress excess returns on the factors of ``model`` with an intercept.

    Parameters
    ----------
    excess_returns
        Portfolio or fund returns minus the risk-free rate, same currency as ``factors``.
    factors
        Factor returns (extra columns such as ``RF`` are ignored); identical index.
    model
        Factor set.
    periods_per_year
        Used to annualise alpha.
    cov_type, hac_lags
        As in :func:`qrlab.stats.regression.ols`; ``CovType.HAC`` is recommended for returns.
    momentum_column
        Name of the momentum column (``"Mom"`` or ``"WML"``); required when the model uses
        momentum and ``None`` otherwise.
    """
    if not isinstance(model, FactorModel):
        raise ValidationError(f"model must be a FactorModel, got {model!r}")
    if not _positive_number(periods_per_year):
        raise ValidationError(f"periods_per_year must be positive, got {periods_per_year!r}")
    if model.uses_momentum != (momentum_column is not None):
        raise ValidationError(
            "momentum_column is required for models with momentum and must be None otherwise"
        )
    columns = {name: (momentum_column if name == MOMENTUM else name) for name in model.value}
    missing = [source for source in columns.values() if source not in factors.columns]
    if missing:
        raise ValidationError(f"factor columns {missing} not found in {list(factors.columns)}")
    design = factors[[str(source) for source in columns.values()]].copy()
    design.columns = list(columns)
    fit = ols(excess_returns, design, add_intercept=True, cov_type=cov_type, hac_lags=hac_lags)
    alpha = float(fit.params[INTERCEPT])
    return FactorResult(
        model=model,
        alpha=alpha,
        alpha_annualised=alpha * periods_per_year,
        alpha_se_annualised=float(fit.std_errors[INTERCEPT]) * periods_per_year,
        betas=fit.params.drop(INTERCEPT).rename("betas"),
        std_errors=fit.std_errors.drop(INTERCEPT),
        tvalues=fit.tvalues,
        pvalues=fit.pvalues,
        r_squared=fit.r_squared,
        nobs=fit.nobs,
        regression=fit,
    )


def _positive_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
        and value > 0
    )
