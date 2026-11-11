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


@pytest.mark.integration
def test_portfolio_example_reproduces_the_hand_values() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "portfolio_toy.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "3.1656%" in out  # TWR = 11,863 / 374,750
    assert "15.7293%" in out  # XIRR from the design note
    assert "480.00" in out
    assert "185.00" in out
    assert "not investment advice" in out


@pytest.mark.integration
def test_factor_example_recovers_the_synthetic_loadings() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "factor_exposures.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "Newey-West" in out
    assert "Mkt-RF    0.944" in out  # true 0.95
    assert "SMB       0.200" in out  # true 0.20
    assert "No significance claims" in out


@pytest.mark.integration
def test_report_example_writes_a_self_contained_html(tmp_path: Path) -> None:
    output = tmp_path / "report.html"
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "portfolio_report.py"), str(output), "it"],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    html = output.read_text(encoding="utf-8")
    assert "15.480,00 EUR" in html
    assert "3,17 %" in html
    assert "Analisi, non consulenza finanziaria." in html
    assert "Controlli di salute" in html
    assert "Scostamento massimo" in html  # drift from the example targets
    assert "<script" not in html
