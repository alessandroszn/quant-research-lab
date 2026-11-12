"""Report of study 2: sections, the no-DSR case and empty inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.reporting.html import render_html
from qrlab.studies.one_over_n import (
    BootstrapSettings,
    compare,
    comparison_table,
    performance,
    performance_table,
)
from qrlab.studies.one_over_n_report import build_one_over_n_report

BOOT = BootstrapSettings(mean_block_length=2.0, n_resamples=100, confidence=0.9)


def _tables(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.date_range("2000-01-31", periods=60, freq="ME")
    ew = pd.Series(rng.normal(0.006, 0.04, 60), index=months)
    hrp = pd.Series(rng.normal(0.007, 0.035, 60), index=months)
    perf = performance_table(
        {
            ("D", 36, 0.0, name): performance(s, turnover=0.02, ceq_risk_aversion=1.0, fallbacks=0)
            for name, s in (("ew", ew), ("hrp", hrp))
        }
    )
    tests = comparison_table(
        {
            ("D", 36, 0.0, "hrp"): compare(
                hrp, ew, hac_lags=2, bootstrap=BOOT, rng=rng, ceq_risk_aversion=1.0
            )
        },
        significance=0.05,
    )
    return perf, tests


def test_report_without_pairs_or_deflated_sharpe(rng: np.random.Generator) -> None:
    perf, tests = _tables(rng)
    perf.loc[1, "max_drawdown"] = np.nan
    report = build_one_over_n_report(
        title="Study 2",
        hypothesis="H",
        facts=(("Data", "synthetic"),),
        performance=perf,
        comparisons=tests,
        pairs=None,
        deflated=None,
        significance=0.05,
    )
    assert [s.title for s in report.sections] == [
        "D, window 36 months, cost 0 bp",
        "Selection across variants",
    ]
    html = render_html(report)
    assert "Deflated Sharpe ratio not computed" in html
    assert "n/a" in html


def test_report_and_tables_need_content(rng: np.random.Generator) -> None:
    perf, tests = _tables(rng)
    with pytest.raises(ValidationError, match="performance and comparison"):
        build_one_over_n_report(
            title="S",
            hypothesis="H",
            facts=(),
            performance=perf.iloc[0:0],
            comparisons=tests,
            pairs=None,
            deflated=None,
            significance=0.05,
        )
    with pytest.raises(ValidationError, match="at least one performance"):
        performance_table({})
