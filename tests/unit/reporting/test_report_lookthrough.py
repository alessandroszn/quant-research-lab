"""The look-through section of the portfolio report (synthetic holdings, toy portfolio)."""

from __future__ import annotations

import html
import re
from datetime import date, timedelta

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data.user_csv import PriceType
from qrlab.instruments.identifiers import Isin
from qrlab.lookthrough import (
    LookThroughInputs,
    TrackingSeries,
    WeightTreatment,
    look_through,
)
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from support.checks import B
from support.lookthrough import X, Y, Z, holding, security, snapshot
from support.portfolio import D2, D3
from support.portfolio import X as FUND
from support.report import toy_instrument, toy_report

EUR = Currency("EUR")


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def _series(start: date, end: date, first: float, last: float, kind: PriceType) -> TrackingSeries:
    index = pd.DatetimeIndex([pd.Timestamp(start), pd.Timestamp(end)])
    return TrackingSeries(pd.Series([first, last], index=index), kind, EUR, None)


def _inputs(
    treatment: WeightTreatment = WeightTreatment.AS_REPORTED, as_of: date = D3
) -> LookThroughInputs:
    snaps = {
        FUND: snapshot(
            FUND,
            [
                holding("Alpha", 0.5, isin=X, country="US", sector="Tech", currency="USD"),
                holding("Beta", 0.3, isin=Y, country="JP", sector="Industry", currency="JPY"),
                holding("Unnamed", 0.18),
            ],
            as_of=date(2026, 3, 1),
        ),
        B: snapshot(
            B,
            [holding("Alpha", 0.6, isin=X), holding("Gamma", 0.4, isin=Z)],
            as_of=date(2026, 2, 1),
        ),
    }
    exposures = look_through(
        as_of=as_of,
        position_weights={FUND: 0.6, B: 0.2},
        cash_weights={EUR: 0.2},
        instruments={FUND: toy_instrument()},
        snapshots=snaps,
        treatment=treatment,
        issuers=None,
    )
    start = D3 - timedelta(days=365)
    tracking = {
        FUND: (
            _series(start, D3, 100.0, 109.8, PriceType.NAV),
            _series(start, D3, 100.0, 110.0, PriceType.TOTAL_RETURN),
        ),
        B: (
            _series(D2, D3, 100.0, 101.0, PriceType.TOTAL_RETURN),
            _series(D2, D3, 100.0, 101.0, PriceType.TOTAL_RETURN),
        ),
    }
    return LookThroughInputs(exposures, snaps, tracking)


def test_section_without_lookthrough_says_so() -> None:
    text = _text(render_html(toy_report(Language.EN)))
    assert "Look-through of fund holdings was not done for this report." in text


def test_section_with_holdings_overlap_and_tracking() -> None:
    text = _text(render_html(toy_report(Language.EN, lookthrough=_inputs())))
    assert "Fund holdings are used as reported" in text
    assert "No issuer map was given" in text
    assert "IE0000000012 Example World Equity UCITS ETF 2026-03-01 30" in text
    assert f"{B.code} {B.code} 2026-02-01 58" in text  # no master data: ISIN as name
    # 0.6 x 0.5 = 30 % US; 0.6 x 0.18 + 0.2 x 1.0 (B has no countries) = 30.80 % unknown
    assert "Country Country Weight US 30.00% JP 18.00% Unknown 30.80% Cash 20.00%" in text
    assert "Not explained by the holdings 1.20%" in text  # 0.6 x (1 - 0.98)
    assert "Alpha (" + X + ") 42.00%" in text  # 0.6 x 0.5 + 0.2 x 0.6
    assert "Unnamed 10.80%" in text
    # min(0.5, 0.6) by ISIN; nothing by name (the unlisted holdings of A match no name in B);
    # 0.18 of A has no ISIN.
    assert f"IE0000000012 {B.code} 50.00% 0.00% 18.00% / 0.00%" in text
    assert "Matches by name are approximate." in text
    assert "NAV -0.20% -0.20% 0.20% 0.00%" in text
    assert "Total return 0.00% n/a n/a n/a" in text  # B: short period, no master data


def test_normalised_weights_and_italian_labels() -> None:
    text = _text(
        render_html(toy_report(Language.IT, lookthrough=_inputs(WeightTreatment.NORMALISED)))
    )
    assert "Le partecipazioni sono riscalate per sommare al 100 %" in text
    assert "Sconosciuto" in text
    assert "Non spiegato" not in text
    assert "Sovrapposizione tra fondi" in text


def test_long_exposure_tables_are_cut_with_a_note() -> None:
    weights = {f"C{n:02d}": 0.04 for n in range(1, 26)}
    rows = [
        holding(f"Corp {n}", 0.04, isin=security("US", 100 + n), country="US") for n in range(1, 26)
    ]
    snaps = {FUND: snapshot(FUND, rows, as_of=date(2026, 3, 1))}
    exposures = look_through(
        as_of=D3, position_weights={FUND: 1.0}, cash_weights={}, instruments={},
        snapshots=snaps, treatment=WeightTreatment.AS_REPORTED, issuers=None,
    )  # fmt: skip
    assert len(weights) == 25
    text = _text(
        render_html(toy_report(Language.EN, lookthrough=LookThroughInputs(exposures, snaps, {})))
    )
    assert "15 smaller entries not shown." in text
    assert "Overlap between funds" not in text
    assert "Tracking difference ISIN" not in text


def test_lookthrough_for_another_date_raises() -> None:
    with pytest.raises(ValidationError, match="look-through is as of"):
        toy_report(lookthrough=_inputs(as_of=D3 + timedelta(days=1)))


def test_an_issuer_map_removes_the_note() -> None:
    snaps = {FUND: snapshot(FUND, [holding("Alpha", 1.0, isin=X)], as_of=date(2026, 3, 1))}
    exposures = look_through(
        as_of=D3,
        position_weights={FUND: 1.0},
        cash_weights={},
        instruments={},
        snapshots=snaps,
        treatment=WeightTreatment.AS_REPORTED,
        issuers={Isin(X): "Alpha group"},
    )
    report = toy_report(Language.EN, lookthrough=LookThroughInputs(exposures, snaps, {}))
    assert "No issuer map was given" not in _text(render_html(report))


def test_no_holdings_at_all_shows_only_the_buckets() -> None:
    exposures = look_through(
        as_of=D3,
        position_weights={FUND: 0.8},
        cash_weights={EUR: 0.2},
        instruments={},
        snapshots={},
        treatment=WeightTreatment.AS_REPORTED,
        issuers=None,
    )
    report = toy_report(Language.EN, lookthrough=LookThroughInputs(exposures, {}, {}))
    text = _text(render_html(report))
    assert "Holdings dates" not in text
    assert "Funds without holdings data 80.00%" in text
