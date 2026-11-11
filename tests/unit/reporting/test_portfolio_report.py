"""HTML rendering and the portfolio report. All data synthetic (the toy portfolio).

Hand values (docs/design/2.1-portfolio.md): end value 15,480, P&L 480 = realised 185 +
unrealised 195 + income 100, residual 0, TWR 3.17 %, MWR 15.73 %.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.portfolio.performance import FlowTiming
from qrlab.reporting.figures import AxisFormat, line_figure
from qrlab.reporting.formatting import IT, Language
from qrlab.reporting.html import Figure, Report, Section, render_html, write_report
from qrlab.reporting.tables import Table
from support.portfolio import D0, D1, D2, D3, EUR, X, eur_only, price_series, toy_setup
from support.report import toy_instrument, toy_report

_report = toy_report
_instrument = toy_instrument


class _Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.h2: list[str] = []
        self.images: list[str] = []
        self._in_h2 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "h2":
            self._in_h2 = True
        if tag == "img":
            self.images.append(dict(attrs).get("src") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_h2 = False

    def handle_data(self, data: str) -> None:
        if self._in_h2:
            self.h2.append(data.strip())


def _parse(html: str) -> _Structure:
    parser = _Structure()
    parser.feed(html)
    return parser


# --------------------------------------------------------------------------- toy report
def test_toy_report_shows_the_hand_values_in_italian() -> None:
    html = render_html(_report(Language.IT))
    for text in (
        "15.480,00 EUR",
        "480,00 EUR",
        "185,00 EUR",
        "195,00 EUR",
        "100,00 EUR",
        "3,17 %",
        "15,73 %",
        "Analisi, non consulenza finanziaria.",
        "TWR e MWR misurano cose diverse e non sono confrontabili.",
        "Example World Equity UCITS ETF",
        "31/03/2026",
    ):
        assert text in html, text


def test_toy_report_in_english() -> None:
    html = render_html(_report(Language.EN))
    for text in (
        "EUR 15,480.00",
        "3.17%",
        "15.73%",
        "Analytics, not investment advice.",
        "2026-03-31",
    ):
        assert text in html, text
    assert '<html lang="en">' in html


def test_sections_and_figures_structure() -> None:
    structure = _parse(render_html(_report(Language.EN)))
    assert structure.h2 == [
        "Summary",
        "Positions",
        "Cash",
        "Profit and loss breakdown",
        "Income and costs",
        "Charts",
        "Look-through",
        "Risk and stress tests",
        "Health checks",
        "Data and assumptions",
    ]
    assert len(structure.images) == 3
    assert all(src.startswith("data:image/png;base64,") for src in structure.images)
    assert "script" not in structure.tags


def test_short_period_is_not_annualised_and_volatility_omitted() -> None:
    html = render_html(_report(Language.EN))
    assert "Not annualised: the period is shorter than one year." in html
    assert "Volatility is omitted" in html


def test_volatility_shown_when_frequency_declared() -> None:
    html = render_html(_report(Language.EN, return_frequency=(Frequency.MONTHLY, 12)))
    assert "Volatility, annualised" in html
    assert "Volatility is omitted" not in html


def test_no_warnings_for_clean_toy() -> None:
    assert _report().warnings == ()


def test_warnings_are_listed() -> None:
    report = _report(Language.EN, instruments={})
    assert any("No master data for IE0000000012" in w for w in report.warnings)
    html = render_html(report)
    assert 'class="warnings"' in html


def test_stale_price_warning() -> None:
    history, _ = toy_setup()
    from qrlab.portfolio.valuation import value_portfolio

    later = date(2026, 4, 2)
    prices = {X: price_series({D0: 50.0, D1: 55.0, D2: 52.0, D3: 54.0})}
    stale_valuation = value_portfolio(
        history, prices, eur_only, dates=[D0, D1, D2, D3, later], max_price_age_days=5
    )
    report = _report(Language.EN, valuation=stale_valuation, max_price_age_days=5, prices=prices)
    assert any(
        "Price of IE0000000012 for 2026-04-02 taken from 2026-03-31." in w for w in report.warnings
    )


def test_untrusted_text_is_escaped() -> None:
    html = render_html(_report(instruments={X: _instrument("<script>alert(1)</script>")}))
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_report_is_self_contained() -> None:
    html = render_html(_report())
    assert not re.search(r"(src|href)\s*=\s*\"https?:", html)
    assert "<link" not in html
    assert "@import" not in html


def test_report_is_deterministic() -> None:
    assert render_html(_report()) == render_html(_report())


def test_generated_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="generated_at"):
        _report(generated_at=datetime(2026, 4, 1, 9, 30))


def test_single_valuation_date_has_no_returns() -> None:
    from qrlab.portfolio.ledger import replay
    from qrlab.portfolio.valuation import value_portfolio
    from support.portfolio import toy_transactions

    history = replay(toy_transactions()[:2], base=EUR, to_base=eur_only)  # deposit and buy on D0
    prices = {X: price_series({D0: 50.0})}
    valuation = value_portfolio(history, prices, eur_only, dates=[D0], max_price_age_days=0)
    # With end-of-day flows the only date has no starting capital, so there is no return.
    html = render_html(
        _report(
            Language.EN,
            history=history,
            valuation=valuation,
            prices=prices,
            flow_timing=FlowTiming.END_OF_DAY,
        )
    )
    assert "Not enough valuation dates to compute returns." in html
    assert "n/a" in html  # MWR undefined: all flows on one date


# --------------------------------------------------------------------------- html primitives
def _minimal_report() -> Report:
    png = line_figure(
        [("v", pd.Series([1.0, 2.0], index=pd.DatetimeIndex([D0, D1])))],
        title="t",
        y_label="y",
        axis=AxisFormat.NUMBER,
        style=IT,
    )
    return Report(
        title="T",
        language=Language.EN,
        facts=(("Base currency", "EUR"),),
        warnings=("careful",),
        sections=(
            Section(
                title="S",
                paragraphs=("p & q",),
                tables=(
                    Table(
                        title="tbl", columns=("a",), rows=(("1",),), align=("right",), notes=("n",)
                    ),
                ),
                figures=(Figure(title="f", png=png),),
            ),
        ),
        footer=("foot",),
    )


def test_render_escapes_every_field() -> None:
    html = render_html(_minimal_report())
    assert "p &amp; q" in html
    assert '<td class="right">1</td>' in html


def test_figure_must_be_png() -> None:
    with pytest.raises(ValidationError, match="PNG"):
        Figure(title="f", png=b"not a png")


def test_write_report_refuses_to_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "report.html"
    write_report(_minimal_report(), path, overwrite=False)
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    with pytest.raises(ValidationError, match="exists"):
        write_report(_minimal_report(), path, overwrite=False)
    write_report(_minimal_report(), path, overwrite=True)


# --------------------------------------------------------------------------- remaining branches
def test_long_period_is_annualised() -> None:
    from qrlab.portfolio.ledger import replay
    from qrlab.portfolio.transactions import TransactionKind
    from qrlab.portfolio.valuation import value_portfolio
    from support.portfolio import money, tx

    start, end = date(2024, 1, 2), date(2026, 1, 1)  # 730 days
    history = replay(
        [
            tx("a", start, TransactionKind.DEPOSIT, amount=money(1000)),
            tx("b", start, TransactionKind.BUY, isin=X, quantity="10", price=money(100)),
            tx("c", end, TransactionKind.FEE, amount=money(5)),
        ],
        base=EUR,
        to_base=eur_only,
        allow_negative_cash=True,
    )
    prices = {X: price_series({start: 100.0, end: 121.0})}
    valuation = value_portfolio(history, prices, eur_only, dates=[start, end], max_price_age_days=0)
    report = _report(Language.EN, history=history, valuation=valuation, prices=prices)
    html = render_html(report)
    # TWR = (1,210 - 5) / 1,000 - 1 = 20.5 %; annualised over 730 days: 1.205^(365/730) - 1
    assert "20.50%" in html
    assert f"{(1.205**0.5 - 1) * 100:.2f}%" in html
    assert "Fee" in html  # the cost is listed


def test_stale_fx_and_wrong_converter_warnings() -> None:
    from qrlab.core.money import Money
    from qrlab.portfolio.valuation import EcbConverter
    from support.portfolio import USD, FixedRates, Y, multi_currency_setup, synthetic_fx

    history, valuation, _ = multi_currency_setup()
    prices = {Y: price_series({D0: 50.0, D3: 60.0}, currency=USD)}
    # A converter different from the one used for the ledger and valuation: the P&L no longer
    # reconciles and the residual warning must appear.
    wrong = FixedRates({D0: "1.25"})
    report = _report(
        Language.EN,
        history=history,
        valuation=valuation,
        to_base=wrong,
        prices=prices,
        instruments={},
    )
    assert any("residual" in w for w in report.warnings)
    # A converter that carried a rate forward is reported.
    stale = EcbConverter(synthetic_fx({D0: {"USD": 1.25}}), base=EUR, max_age_days=400)
    stale(Money.of(1, "USD"), D3)
    report = _report(
        Language.EN,
        history=history,
        valuation=valuation,
        to_base=stale,
        prices=prices,
        instruments={},
    )
    assert any("USD rate for 2026-03-31 taken from 2026-01-02." in w for w in report.warnings)


def test_missing_price_series_raises() -> None:
    from qrlab.data.errors import DataNotFoundError

    with pytest.raises(DataNotFoundError, match="IE0000000012"):
        _report(prices={})


def test_mwr_with_several_roots_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    import qrlab.reporting.portfolio_report as module
    from qrlab.portfolio.performance import XirrResult

    monkeypatch.setattr(
        module, "money_weighted_return", lambda *a, **k: XirrResult(0.1, 2, (0.1, 0.2))
    )
    report = _report(Language.EN)
    assert any("candidate rates 10.00%, 20.00%" in w for w in report.warnings)


def test_skipped_dates_after_the_start_warn() -> None:
    from qrlab.portfolio.ledger import replay
    from qrlab.portfolio.transactions import TransactionKind
    from qrlab.portfolio.valuation import value_portfolio
    from support.portfolio import money, tx

    history = replay(
        [
            tx("a", D0, TransactionKind.DEPOSIT, amount=money(1000)),
            tx("b", D1, TransactionKind.WITHDRAWAL, amount=money(1000)),
            tx("c", D2, TransactionKind.DEPOSIT, amount=money(500)),
        ],
        base=EUR,
        to_base=eur_only,
    )
    valuation = value_portfolio(history, {}, eur_only, dates=[D0, D1, D2], max_price_age_days=0)
    report = _report(
        Language.EN,
        history=history,
        valuation=valuation,
        prices={},
        flow_timing=FlowTiming.END_OF_DAY,
    )
    assert any("No TWR for 2026-02-27" in w for w in report.warnings)


def test_empty_valuation_raises() -> None:
    _, valuation = toy_setup()
    from dataclasses import replace

    with pytest.raises(ValidationError, match="no dates"):
        _report(valuation=replace(valuation, totals={}, positions={}, cash={}))


def test_kinds_are_translated_and_titles_not_repeated() -> None:
    html = render_html(_report(Language.IT))
    assert "Dividendo" in html
    assert ">dividend<" not in html
    assert "<h3>Riepilogo</h3>" not in html  # the table title equals the section title


def test_every_transaction_kind_has_a_label() -> None:
    from qrlab.portfolio.transactions import TransactionKind
    from qrlab.reporting.labels import label

    for language in Language:
        for kind in TransactionKind:
            assert label(f"kind_{kind.value}", language)
