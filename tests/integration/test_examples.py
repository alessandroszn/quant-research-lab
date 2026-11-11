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
    assert "Partecipazioni al" in html  # look-through of the synthetic holdings file
    assert "Non spiegato dalle partecipazioni" in html  # holdings sum to 99 %
    assert "<script" not in html


@pytest.mark.integration
def test_risk_example_runs_deterministically() -> None:
    runs = [
        subprocess.run(
            [sys.executable, str(EXAMPLES / "risk_models.py")],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        for _ in range(2)
    ]
    assert runs[0].returncode == 0, runs[0].stderr
    assert runs[0].stdout == runs[1].stdout
    out = runs[0].stdout
    assert "Ledoit-Wolf shrinkage intensity" in out
    assert "Effective number of bets" in out
    assert "Cornish-Fisher" in out
    assert "Kupiec p" in out
    assert "not investment advice" in out
    assert "not proof that the model is right" in out
    assert "Stress scenarios on today's weights" in out
    assert "gfc_2008         +0.00%" in out  # synthetic history starts in 2020
    assert "not covered 90%" in out
    assert "equity_minus_30  -17.87%" in out


@pytest.mark.integration
def test_projection_example_runs_deterministically() -> None:
    runs = [
        subprocess.run(
            [sys.executable, str(EXAMPLES / "projection_plan.py")],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        for _ in range(2)
    ]
    assert runs[0].returncode == 0, runs[0].stderr
    assert runs[0].stdout == runs[1].stdout
    out = runs[0].stdout
    assert "not forecasts or investment advice" in out
    assert "block bootstrap (12)" in out
    assert "P(running out)" in out
    assert "sequence risk" in out
    assert "mean return +1 pp" in out


@pytest.mark.integration
def test_construction_example_reports_only_out_of_sample_results() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "portfolio_construction.py")],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "out-of-sample months only" in out
    assert "15 walk-forward splits" in out
    assert "180 out-of-sample months" in out
    assert "hierarchical risk parity" in out
    assert "66/34 -> 65%/35%, traded 2,000 EUR, cost 6.00 EUR" in out
    assert "not evidence" in out


@pytest.mark.integration
def test_backtest_example_shows_gross_and_net() -> None:
    runs = [
        subprocess.run(
            [sys.executable, str(EXAMPLES / "backtest_strategies.py")],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        for _ in range(2)
    ]
    assert runs[0].returncode == 0, runs[0].stderr
    assert runs[0].stdout == runs[1].stdout
    out = runs[0].stdout
    assert "lag 1 month" in out
    assert "gross ann." in out
    assert "net ann." in out
    assert "cross-sectional momentum" in out
    assert "One path is not evidence" in out


@pytest.mark.integration
def test_attribution_example_adds_up() -> None:
    runs = [
        subprocess.run(
            [sys.executable, str(EXAMPLES / "attribution_example.py")],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        for _ in range(2)
    ]
    assert runs[0].returncode == 0, runs[0].stderr
    assert runs[0].stdout == runs[1].stdout
    out = runs[0].stdout
    assert "Carino-linked" in out
    assert "not evidence of skill" in out
    assert "residual below 1e-12: True" in out
    assert "Currency attribution of one month" in out
