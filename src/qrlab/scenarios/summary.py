"""Risk numbers and stress results bundled for the portfolio report.

The report computes nothing new: the caller runs :mod:`qrlab.risk` and :func:`run_scenario`
and passes the results here, with the window and frequency they were estimated on.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from qrlab.core.errors import ValidationError
from qrlab.risk.decomposition import RiskContributions
from qrlab.scenarios.engine import ScenarioResult

__all__ = ["RiskSummary"]


@dataclass(frozen=True)
class RiskSummary:
    """Risk and stress-test results of one portfolio on ``as_of``.

    Parameters
    ----------
    as_of
        Date of the weights the risk and scenarios apply to.
    frequency
        Frequency of the returns, e.g. ``"monthly"`` (figures are one period of it).
    window_start, window_end, n_obs
        Estimation window of the risk numbers.
    confidence
        Confidence of the VaR and ES figures.
    volatility
        Volatility contributions (:func:`qrlab.risk.volatility_contributions`).
    var_es
        ``(VaR, ES)`` as positive losses by method name, in display order.
    scenarios
        Results of :func:`qrlab.scenarios.run_scenario`, in display order.
    """

    as_of: date
    frequency: str
    window_start: date
    window_end: date
    n_obs: int
    confidence: float
    volatility: RiskContributions
    var_es: Mapping[str, tuple[float, float]]
    scenarios: tuple[ScenarioResult, ...]

    def __post_init__(self) -> None:
        """Validate the window, the confidence and the figures."""
        if not self.frequency.strip():
            raise ValidationError("frequency must be named")
        if self.window_end < self.window_start:
            raise ValidationError("window_end is before window_start")
        if self.window_end > self.as_of:
            raise ValidationError("the estimation window ends after as_of (look-ahead)")
        if type(self.n_obs) is not int or self.n_obs < 2:
            raise ValidationError("n_obs must be an int >= 2")
        if not 0.0 < self.confidence < 1.0:
            raise ValidationError("confidence must be strictly between 0 and 1")
        for method, (var, es) in self.var_es.items():
            if not (math.isfinite(var) and math.isfinite(es)):
                raise ValidationError(f"{method}: VaR and ES must be finite")
