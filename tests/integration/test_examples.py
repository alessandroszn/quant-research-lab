"""Every example runs end to end in a fresh interpreter, offline and deterministically."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parents[2] / "examples"


@pytest.mark.integration
def test_m1_example_runs_and_labels_its_output() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "m1_analytics_core.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "time-weighted" in out
    assert "In-sample" in out
    assert "not investment advice" in out
    assert "Sharpe" in out
    assert "120 months" in out


@pytest.mark.integration
def test_m1_example_is_deterministic() -> None:
    runs = [
        subprocess.run(
            [sys.executable, str(EXAMPLES / "m1_analytics_core.py")],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
