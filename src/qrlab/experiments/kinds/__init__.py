"""The registered experiment kinds."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from qrlab.experiments.kinds import (
    backtest,
    optimisation,
    portfolio_report,
    projection,
    risk_report,
    scenario_analysis,
    study_factor_zoo,
    study_one_over_n,
    study_rebalancing,
    study_volatility_managed,
)
from qrlab.experiments.registry import ExperimentKind

__all__ = ["KINDS"]

KINDS: Mapping[str, ExperimentKind] = MappingProxyType(
    {
        kind.name: kind
        for kind in (
            portfolio_report.KIND,
            backtest.KIND,
            projection.KIND,
            risk_report.KIND,
            scenario_analysis.KIND,
            optimisation.KIND,
            study_volatility_managed.KIND,
            study_one_over_n.KIND,
            study_factor_zoo.KIND,
            study_rebalancing.KIND,
        )
    }
)
"""Every registered kind by name."""
