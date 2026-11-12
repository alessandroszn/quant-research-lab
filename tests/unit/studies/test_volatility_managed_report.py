"""Report of study 1: structure, missing values and empty inputs."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.reporting.html import render_html
from qrlab.studies.volatility_managed import (
    BootstrapSettings,
    in_sample_spanning,
    in_sample_table,
    out_of_sample_comparison,
    out_of_sample_table,
)
from qrlab.studies.volatility_managed_report import build_volatility_managed_report


def _tables(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.date_range("2000-01-31", periods=120, freq="ME")
    factor = pd.Series(rng.normal(0.005, 0.04, 120), index=months)
    signal = pd.Series(rng.uniform(100.0, 900.0, 120), index=months)
    in_sample = in_sample_table(
        {"Mkt-RF": in_sample_spanning(factor, signal, hac_lags=3, periods_per_year=12)},
        significance=0.05,
    )
    out = out_of_sample_comparison(
        factor,
        signal,
        burn_in=36,
        cap=math.inf,
        cost_per_unit=0.001,
        hac_lags=3,
        periods_per_year=12,
        bootstrap=BootstrapSettings(mean_block_length=2.0, n_resamples=100, confidence=0.9),
        rng=rng,
    )
    return in_sample, out_of_sample_table([("Mkt-RF", out)], significance=0.05)


def test_report_sections_and_missing_values(rng: np.random.Generator) -> None:
    in_sample, out = _tables(rng)
    in_sample.loc["Mkt-RF", "alpha_annual"] = np.nan
    in_sample.loc["Mkt-RF", "alpha_t"] = np.inf
    report = build_volatility_managed_report(
        title="Study",
        hypothesis="H",
        facts=(("Data", "synthetic"),),
        in_sample=in_sample,
        out_of_sample=out,
        deflated=None,
        significance=0.05,
    )
    titles = [s.title for s in report.sections]
    assert titles == [
        "In sample: spanning regressions",
        "Out of sample: no cap, cost 10 bp per unit traded",
        "Selection across variants",
    ]
    html = render_html(report)
    assert html.count("n/a") == 2
    assert "future information" in html
    assert report.facts[0] == ("Hypothesis", "H")


def test_report_needs_both_tables(rng: np.random.Generator) -> None:
    in_sample, out = _tables(rng)
    for a, b in ((in_sample.iloc[0:0], out), (in_sample, out.iloc[0:0])):
        with pytest.raises(ValidationError, match="in-sample and out-of-sample"):
            build_volatility_managed_report(
                title="S",
                hypothesis="H",
                facts=(),
                in_sample=a,
                out_of_sample=b,
                deflated=None,
                significance=0.05,
            )
