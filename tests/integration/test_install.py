"""Integration check: the package is importable in a clean subprocess interpreter.

Catches packaging mistakes (e.g. wrong wheel target) that in-process imports can mask.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_package_imports_in_fresh_interpreter() -> None:
    code = (
        "import qrlab, qrlab.core, qrlab.data, qrlab.instruments, qrlab.portfolio, qrlab.checks, "
        "qrlab.stats, qrlab.validation, qrlab.metrics, qrlab.backtest, qrlab.reporting, "
        "qrlab.experiments, qrlab.cli; "
        "print(qrlab.__version__)"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() != "0.0.0+unknown"


@pytest.mark.integration
def test_qrlab_console_script_lists_the_kinds() -> None:
    script = shutil.which("qrlab", path=str(Path(sys.executable).parent))
    assert script is not None, "the qrlab console script is not installed next to Python"
    result = subprocess.run([script, "kinds"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "portfolio_report" in result.stdout
    assert "projection" in result.stdout
    bad = subprocess.run(
        [script, "validate", "missing.toml"], capture_output=True, text=True, check=False
    )
    assert bad.returncode == 2
