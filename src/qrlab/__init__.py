"""Quant Research Lab: a framework for reproducible quantitative financial research.

Layering (lower layers never import higher ones; enforced by ``tests/unit/test_architecture.py``)::

    core  ->  data, stats, metrics  ->  validation  ->  backtest  ->  reporting
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("quant-research-lab")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
