"""The risk-free rows of the portfolio report's summary (design 8.5)."""

from __future__ import annotations

from qrlab.core.calendar import Frequency
from qrlab.metrics.performance import SharpeEstimate, SharpeSE
from qrlab.reporting import Language, RiskFreeSummary, render_html
from support.report import toy_report

SHARPE = SharpeEstimate(0.8512, 0.4033, 24, SharpeSE.IID_NON_NORMAL)


def test_rows_in_english_and_italian() -> None:
    risk_free = RiskFreeSummary("€STR (ECB)", 0.0712, SHARPE)
    english = render_html(
        toy_report(Language.EN, return_frequency=(Frequency.MONTHLY, 12.0), risk_free=risk_free)
    )
    assert "Risk-free return over the period (€STR (ECB))" in english
    assert "0.85 ± 0.40 (n = 24)" in english
    italian = render_html(
        toy_report(Language.IT, return_frequency=(Frequency.MONTHLY, 12.0), risk_free=risk_free)
    )
    assert "Sharpe ratio (TWR in eccesso rispetto al tasso privo di rischio" in italian
    assert "0,85 ± 0,40 (n = 24)" in italian


def test_a_missing_sharpe_ratio_says_why() -> None:
    risk_free = RiskFreeSummary("€STR (ECB)", 0.01, None, "too few returns")
    page = render_html(
        toy_report(Language.EN, return_frequency=(Frequency.MONTHLY, 12.0), risk_free=risk_free)
    )
    assert "The Sharpe ratio is not shown: too few returns" in page


def test_without_a_risk_free_series_there_is_no_sharpe_row() -> None:
    assert "Sharpe ratio" not in render_html(toy_report(Language.EN))


def test_tax_section_dichiarativo_with_a_flagged_fund_and_no_losses() -> None:
    from datetime import date
    from decimal import Decimal

    from qrlab.tax import Category, Regime, TaxEvent, TaxPosition, italian_tax_report
    from support.portfolio import X

    event = TaxEvent(
        date(2026, 2, 27), "main", X.code, Category.NOT_COMPUTED, Decimal(100), Decimal(0),
        Decimal(0), Decimal(0), None, Decimal(0),
    )  # fmt: skip
    position = TaxPosition(date(2026, 3, 31), Regime.DICHIARATIVO, (event,), (), (X.code,))
    page = render_html(toy_report(Language.EN, tax=italian_tax_report(position)))
    assert "the tax shown is an estimate to declare" in page
    assert "Not computed: Example World Equity UCITS ETF" in page
    assert "Losses balance" not in page
