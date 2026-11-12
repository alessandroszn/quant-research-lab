"""The registered experiment kinds (populated in phase 5.2b)."""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.experiments.registry import ExperimentKind

__all__ = ["KINDS"]

KINDS: Mapping[str, ExperimentKind] = {}
"""Every registered kind by name."""
