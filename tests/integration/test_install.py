"""Integration check: the package is importable in a clean subprocess interpreter.

Catches packaging mistakes (e.g. wrong wheel target) that in-process imports can mask.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.integration
def test_package_imports_in_fresh_interpreter() -> None:
    code = (
        "import qrlab, qrlab.core, qrlab.data, qrlab.stats, qrlab.validation, "
        "qrlab.metrics, qrlab.backtest, qrlab.reporting; print(qrlab.__version__)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() != "0.0.0+unknown"
