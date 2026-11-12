"""The registered experiment kinds."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from qrlab.experiments.kinds import (
    backtest,
    portfolio_report,
    projection,
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
            study_volatility_managed.KIND,
        )
    }
)
"""Every registered kind by name."""
