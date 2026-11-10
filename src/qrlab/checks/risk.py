"""Risk checks on the portfolio return series (``CheckContext.portfolio_returns``).

The series must be at a regular frequency (e.g. monthly TWR) matching the ``periods_per_year``
given in the config. Without a series, or with too few observations, the checks are not
applicable. Beta uses returns (not excess returns) against ``benchmark_returns``.
"""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.checks.context import CheckContext
from qrlab.checks.framework import Direction, Measurement, MeasureUnit, NotApplicable, spec
from qrlab.core.errors import ValidationError
from qrlab.metrics.drawdown import max_drawdown as _max_drawdown
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.moments import skewness as _skewness
from qrlab.metrics.performance import annualised_volatility
from qrlab.metrics.relative import capm_regression
from qrlab.metrics.risk import historical_es

__all__ = ["CHECKS"]

_NO_SERIES = NotApplicable("no portfolio return series given")


def volatility(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Annualised volatility of portfolio returns."""
    if ctx.portfolio_returns is None:
        return _NO_SERIES
    periods = params["periods_per_year"]
    if isinstance(periods, bool) or not isinstance(periods, int | float):
        raise ValidationError("risk.volatility: periods_per_year must be a number")
    try:
        value = annualised_volatility(ctx.portfolio_returns, periods_per_year=float(periods))
    except UndefinedMetricError as exc:
        return NotApplicable(str(exc))
    return [Measurement("portfolio", value)]


def max_drawdown(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Maximum drawdown of the portfolio return path (a negative number)."""
    if ctx.portfolio_returns is None:
        return _NO_SERIES
    try:
        return [Measurement("portfolio", _max_drawdown(ctx.portfolio_returns))]
    except UndefinedMetricError as exc:
        return NotApplicable(str(exc))


def expected_shortfall(
    ctx: CheckContext, params: Mapping[str, object]
) -> list[Measurement] | NotApplicable:
    """Historical one-period expected shortfall (positive loss) at ``confidence``."""
    if ctx.portfolio_returns is None:
        return _NO_SERIES
    confidence = params["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, float):
        raise ValidationError("risk.expected_shortfall: confidence must be a number in (0, 1)")
    try:
        return [
            Measurement("portfolio", historical_es(ctx.portfolio_returns, confidence=confidence))
        ]
    except UndefinedMetricError as exc:
        return NotApplicable(str(exc))


def beta(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """OLS beta of portfolio returns on benchmark returns."""
    if ctx.portfolio_returns is None:
        return _NO_SERIES
    if ctx.benchmark_returns is None:
        return NotApplicable("no benchmark given")
    try:
        fit = capm_regression(ctx.portfolio_returns, ctx.benchmark_returns, periods_per_year=1)
    except UndefinedMetricError as exc:
        return NotApplicable(str(exc))
    return [Measurement("portfolio", fit.beta, {"r_squared": f"{fit.r_squared:.4f}"})]


def skewness(ctx: CheckContext, params: Mapping[str, object]) -> list[Measurement] | NotApplicable:
    """Skewness of portfolio returns (negative values mean a fatter left tail)."""
    if ctx.portfolio_returns is None:
        return _NO_SERIES
    try:
        return [Measurement("portfolio", _skewness(ctx.portfolio_returns))]
    except UndefinedMetricError as exc:
        return NotApplicable(str(exc))


CHECKS = (
    spec("risk.volatility", Direction.ABOVE, MeasureUnit.FRACTION, volatility, "periods_per_year"),
    spec("risk.max_drawdown", Direction.BELOW, MeasureUnit.FRACTION, max_drawdown),
    spec(
        "risk.expected_shortfall",
        Direction.ABOVE,
        MeasureUnit.FRACTION,
        expected_shortfall,
        "confidence",
    ),
    spec("risk.beta", Direction.ABOVE, MeasureUnit.RATIO, beta),
    spec("risk.skewness", Direction.BELOW, MeasureUnit.RATIO, skewness),
)
