"""The risk and stress-test section of the portfolio report (synthetic results)."""

from __future__ import annotations

import html
import re
from datetime import date, timedelta

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from qrlab.risk import CovarianceEstimate, volatility_contributions
from qrlab.scenarios import (
    HistoricalScenario,
    HypotheticalScenario,
    MarketData,
    PositionSeries,
    RiskSummary,
    StressPortfolio,
    run_scenario,
)
from support.checks import B
from support.portfolio import D0, D3, X
from support.report import toy_report

EUR, USD = Currency("EUR"), Currency("USD")


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def _summary(as_of: date = D3) -> RiskSummary:
    names = [X.code, B.code]
    covariance = CovarianceEstimate(
        pd.DataFrame([[0.04, 0.01], [0.01, 0.01]], index=names, columns=names), "sample", 36, 0
    )
    volatility = volatility_contributions(covariance, pd.Series({X.code: 0.5, B.code: 0.5}))
    portfolio = StressPortfolio(
        as_of=D3,
        value=Money.of("10000", "EUR"),
        position_weights={X: 0.6, B: 0.25},
        cash_weights={EUR: 0.15},
        exposure_currencies={X: EUR, B: USD},
    )
    index = pd.DatetimeIndex(pd.to_datetime(["2019-12-31", "2020-01-31", "2020-02-29"]))
    market = MarketData({X: PositionSeries(pd.Series([0.0, 0.0, -0.3], index=index), EUR)},
                        pd.DataFrame(), None, {})  # fmt: skip
    crash = HistoricalScenario("crash", "Synthetic crash", date(2020, 1, 31), date(2020, 2, 29))
    usd = HypotheticalScenario("usd", "US dollar -10 %", {}, {}, {USD: -0.10})
    return RiskSummary(
        as_of=as_of,
        frequency="monthly",
        window_start=date(2023, 4, 30),
        window_end=D3,
        n_obs=36,
        confidence=0.95,
        volatility=volatility,
        var_es={"historical": (0.05, 0.07), "normal": (0.045, 0.06)},
        scenarios=(run_scenario(crash, portfolio, market), run_scenario(usd, portfolio, market)),
    )


def test_section_without_risk_says_so() -> None:
    text = _text(render_html(toy_report(Language.EN)))
    assert "Risk numbers and stress tests were not computed for this report." in text


def test_section_with_risk_and_scenarios() -> None:
    text = _text(render_html(toy_report(Language.EN, risk=_summary())))
    assert "Risk figures are one monthly period, estimated on 36 returns from 2023-04-30" in text
    assert "not forecasts or probabilities" in text
    # sigma_p = 13.23 %; contributions 9.45 % and 3.78 % (design note 3.1 hand example)
    assert "Example World Equity UCITS ETF 9.45% 71.43%" in text
    assert f"{B.code} 3.78% 28.57%" in text
    assert "Total 13.23% 100.00%" in text
    assert "Value at risk and expected shortfall at 95.00%" in text
    assert "historical 5.00% 7.00%" in text
    # crash: 0.6 x -30 % = -18 %, B (25 %) not covered; P&L on 10,000 EUR
    assert "Synthetic crash Historical 2020-02-29 - 2020-02-29 -18.00% EUR -1,800.00 25.00%" in text
    assert "US dollar -10 % Hypothetical n/a -2.50% EUR -250.00 0.00%" in text
    assert "crash Example World Equity UCITS ETF Own history -30.00% -18.00%" in text
    assert f"crash {B.code} Not covered n/a n/a" in text
    assert "usd Cash EUR Cash 0.00% 0.00%" in text
    assert "never assumed to lose nothing" in text


def test_section_in_italian_and_without_optional_tables() -> None:
    summary = _summary()
    bare = RiskSummary(
        summary.as_of, "mensile", summary.window_start, summary.window_end, 36, 0.95,
        summary.volatility, {}, (),
    )  # fmt: skip
    text = _text(render_html(toy_report(Language.IT, risk=bare)))
    assert "Rischio e stress test" in text
    assert "su un periodo (mensile)" in text
    assert "Value at risk" not in text
    assert "Scenari di stress" not in text


def test_risk_for_another_date_raises() -> None:
    with pytest.raises(ValidationError, match="risk is as of"):
        toy_report(risk=_summary(as_of=D3 + timedelta(days=1)))


def test_summary_is_validated() -> None:
    good = _summary()
    for changes, match in (
        ({"frequency": " "}, "frequency"),
        ({"window_start": date(2026, 4, 1), "window_end": date(2026, 3, 1)}, "before"),
        ({"window_end": date(2026, 4, 2)}, "look-ahead"),
        ({"n_obs": 1}, "n_obs"),
        ({"confidence": 1.0}, "confidence"),
        ({"var_es": {"x": (float("nan"), 0.1)}}, "finite"),
    ):
        fields = {**good.__dict__, **changes}
        with pytest.raises(ValidationError, match=match):
            RiskSummary(**fields)
    assert good.window_end > D0
