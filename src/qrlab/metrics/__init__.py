"""Performance, risk and benchmark-relative metrics of simple-return series.

Conventions (see ``docs/design/1.4-metrics.md``):

- inputs are **simple** returns in decimals, without NaN (gaps are the caller's decision);
- ``periods_per_year`` is always an explicit argument;
- Sharpe, Sortino and CAPM take **excess** returns computed with
  :func:`qrlab.core.returns.excess_returns`;
- VaR and ES are positive one-period losses;
- portfolio and benchmark must share the index; same currency and return type is the
  caller's responsibility;
- undefined results raise :class:`UndefinedMetricError` instead of returning NaN.

Modules: ``performance``, ``drawdown``, ``moments``, ``risk``, ``relative``.
"""

from qrlab.metrics.drawdown import (
    calmar_ratio,
    drawdown_episodes,
    drawdown_series,
    max_drawdown,
    ulcer_index,
)
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.moments import excess_kurtosis, skewness
from qrlab.metrics.performance import (
    SharpeEstimate,
    SharpeSE,
    annualised_arithmetic_return,
    annualised_geometric_return,
    annualised_volatility,
    downside_deviation,
    gain_loss_ratio,
    hit_rate,
    sharpe_ratio,
    sortino_ratio,
)
from qrlab.metrics.relative import (
    CapmEstimate,
    active_share,
    capm_regression,
    down_capture,
    information_ratio,
    tracking_error,
    up_capture,
)
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var

__all__ = [
    "CapmEstimate",
    "SharpeEstimate",
    "SharpeSE",
    "UndefinedMetricError",
    "active_share",
    "annualised_arithmetic_return",
    "annualised_geometric_return",
    "annualised_volatility",
    "calmar_ratio",
    "capm_regression",
    "down_capture",
    "downside_deviation",
    "drawdown_episodes",
    "drawdown_series",
    "excess_kurtosis",
    "gain_loss_ratio",
    "historical_es",
    "historical_var",
    "hit_rate",
    "information_ratio",
    "max_drawdown",
    "parametric_es",
    "parametric_var",
    "sharpe_ratio",
    "skewness",
    "sortino_ratio",
    "tracking_error",
    "ulcer_index",
    "up_capture",
]
