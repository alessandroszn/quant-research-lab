"""The projection section of the portfolio report (seeded synthetic projection)."""

from __future__ import annotations

import html
import re
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from qrlab.simulation import (
    MAX_CELLS,
    Flow,
    LogMoments,
    Plan,
    ProjectionResult,
    SimulatedReturns,
    TaxModel,
    normal_returns,
    project,
    sensitivity,
    shifted_moments,
    summarize,
)
from support.portfolio import D3
from support.report import toy_report

EUR = Currency("EUR")
MOMENTS = LogMoments(
    pd.Series([0.004], index=["fund"]),
    pd.DataFrame([[0.04**2]], index=["fund"], columns=["fund"]),
    120,
)


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def _simulate(shift: float, scale: float) -> SimulatedReturns:
    moments = shifted_moments(
        MOMENTS, annual_mean_shift=shift, vol_scale=scale, periods_per_year=12
    )
    return normal_returns(
        moments, n_paths=400, n_periods=24, rng=np.random.default_rng(3), max_cells=MAX_CELLS
    )


def _result(rebalance: int | None = None, with_sensitivity: bool = True) -> ProjectionResult:
    plan = Plan(
        initial_wealth=15480.0,
        currency=EUR,
        weights=pd.Series([1.0], index=["fund"]),
        periods_per_year=12,
        flows=(Flow("contribution", 200.0, 0, 23, True), Flow("withdrawal", 100.0, 12, 23, False)),
        flow_timing="start",
        rebalance_every=rebalance,
        annual_cost=0.005,
        inflation=0.02,
        taxes=TaxModel(0.26, 0.002),
    )
    returns = _simulate(0.0, 1.0)
    summary = summarize(
        project(plan, returns),
        returns,
        start=D3,
        goal_real=18_000.0,
        percentiles=(5, 50, 95),
        early_periods=12,
    )
    rows = sensitivity(plan, _simulate, goal_real=18_000.0) if with_sensitivity else ()
    return ProjectionResult(summary, rows)


def test_section_without_projection_says_so() -> None:
    text = _text(render_html(toy_report(Language.EN)))
    assert "No projection was computed for this report." in text


def test_section_with_a_projection() -> None:
    result = _result()
    page = render_html(toy_report(Language.EN, projection=result))
    text = _text(page)
    assert "not forecasts or advice" in text
    assert "Return engine normal" in text
    assert "Simulated paths 400" in text
    assert "Horizon 2.0 years" in text
    assert "contribution EUR 200.00 in periods 1-24 (indexed to inflation)" in text
    assert "net withdrawal EUR 100.00 in periods 13-24 (fixed)" in text
    assert "Rebalancing Never (buy and hold)" in text
    assert "Capital-gains tax 26.00%" in text
    summary = result.summary
    median = f"{summary.terminal_real[1]:,.2f}"
    assert f"P50 EUR {median}" in text
    odds = f"{summary.p_goal:.2%} ± {summary.p_goal_se:.2%}"
    assert f"Probability of reaching EUR 18,000.00 (real) {odds}" in text
    assert "worst 10 % of the first 12 periods" in text
    assert "Costs -0.5 points" in text
    assert "Volatility x1.2" in text
    assert "same random numbers as the base case" in text
    assert page.count("data:image/png;base64,") == 4  # three portfolio charts plus the fan chart


def test_section_in_italian_with_rebalancing() -> None:
    text = _text(
        render_html(
            toy_report(Language.IT, projection=_result(rebalance=12, with_sensitivity=False))
        )
    )
    assert "Proiezione" in text
    assert "Ribilanciamento Ogni 12 periodi" in text
    assert "Sensibilità alle ipotesi" not in text


def test_projection_must_start_on_the_report_date() -> None:
    result = _result(with_sensitivity=False)
    moved = ProjectionResult(
        type(result.summary)(
            **{
                **result.summary.__dict__,
                "dates": (D3 + timedelta(days=1), *result.summary.dates[1:]),
            }
        ),
        (),
    )
    with pytest.raises(ValidationError, match="projection starts on"):
        toy_report(projection=moved)
