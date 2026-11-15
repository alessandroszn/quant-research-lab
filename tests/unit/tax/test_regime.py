"""The common shape of tax analytics (design 9.1): a country renders without new code.

A toy country, defined only here, describes one sentence of each value type and one table
of each column kind, with existing label keys. Its CSV and its report section come out of the
generic code, formatted for each language: a 1,234.50 gain, a 48.08 % share, the year 2027.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments.kinds.portfolio_report import _tax_tables
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import render_html
from qrlab.tax import (
    ITALY,
    REGIMES,
    ColumnKind,
    Holdings,
    LabelRef,
    Paragraph,
    SourcesRef,
    TaxColumn,
    TaxReport,
    TaxTable,
    regime_for,
)
from support.portfolio import X
from support.report import toy_report

COLUMNS = (
    TaxColumn("date", "date", ColumnKind.DATE, "left"),
    TaxColumn("isin", "holding", ColumnKind.HOLDING, "left"),
    TaxColumn("category", "tax_category", ColumnKind.LABEL, "left", prefix="tax_cat_"),
    TaxColumn("result", "tax_result", ColumnKind.MONEY, "right"),
    TaxColumn("share", "tax_public_share", ColumnKind.SHARE, "right"),
    TaxColumn("year", "tax_year", ColumnKind.YEAR, "left"),
    TaxColumn("note", "", ColumnKind.TEXT, "left"),
)
ROWS = (
    (date(2026, 3, 3), X.code, "redditi_diversi", Decimal("1234.50"), Decimal("0.4808"), 2027,
     "ok"),
    (date(2026, 3, 4), X.code, "redditi_diversi", None, Decimal(0), 2027, "none"),
)  # fmt: skip
TOY = TaxReport(
    country="xx",
    as_of=date(2026, 3, 31),
    checked_on=date(2026, 11, 15),
    sources={"en": ("Toy Act, art. 1",), "it": ("Legge giocattolo, art. 1",)},
    paragraphs=(
        Paragraph(
            "tax_intro",
            (("regime", LabelRef("tax_regime_amministrato")), ("checked", date(2026, 11, 15))),
        ),
        Paragraph("tax_flagged", (("names", Holdings((X.code,))),)),
        Paragraph("tax_sources", (("sources", SourcesRef()),)),
        Paragraph("tax_sources", (("sources", "plain text"),)),
    ),
    tables=(
        TaxTable(
            "tax_events", COLUMNS, ROWS, file="toy_events", index="date", note="tax_events_note"
        ),
        TaxTable("tax_losses", COLUMNS, (), file="toy_empty", index="date", shown_when_empty=False),
    ),
    scalars={"toy_total": Decimal("1234.50")},
)


def test_the_csv_tables_come_from_the_description() -> None:
    tables = _tax_tables(TOY)
    assert sorted(tables) == ["toy_empty", "toy_events"]
    frame, empty = tables["toy_events"].value, tables["toy_empty"].value
    assert isinstance(frame, pd.DataFrame)
    assert isinstance(empty, pd.DataFrame)
    assert list(frame.columns) == ["isin", "category", "result", "share", "year", "note"]
    assert frame.index.tolist() == [date(2026, 3, 3), date(2026, 3, 4)]
    assert frame["result"].tolist()[0] == 1234.5
    assert frame["result"].isna().tolist() == [False, True]
    assert frame["share"].tolist() == [0.4808, 0.0]
    assert frame["category"].tolist() == ["redditi_diversi"] * 2
    assert empty.empty


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (
            Language.EN,
            [
                "Rules as checked on 2026-11-15.",
                "Sources: Toy Act, art. 1.",
                "Sources: plain text.",
                "Example World Equity UCITS ETF",
                "Other income",
                "1,234.50",
                "48.08",
                "2027",
                "n/a",
            ],
        ),
        (
            Language.IT,
            [
                "Regole verificate al 15/11/2026.",
                "Fonti: Legge giocattolo, art. 1.",
                "Redditi diversi",
                "1.234,50",
                "48,08",
                "n.d.",
            ],
        ),
    ],
)
def test_the_section_renders_in_each_language(language: Language, expected: list[str]) -> None:
    page = render_html(toy_report(language, tax=TOY))
    for text in expected:
        assert text in page, text
    assert ("Losses balance" if language is Language.EN else "Zainetto") not in page


def test_the_shape_is_checked() -> None:
    with pytest.raises(ValidationError, match="no sources in \\['it'\\]"):
        replace(TOY, sources={"en": ("x",)})
    with pytest.raises(ValidationError, match="CSV names repeat"):
        replace(TOY, tables=(TOY.tables[0], TOY.tables[0]))
    with pytest.raises(ValidationError, match="a row has 1 cells, not 7"):
        TaxTable("t", COLUMNS, (("x",),))
    with pytest.raises(ValidationError, match="index 'day' is not a column"):
        TaxTable("t", COLUMNS, (), file="t", index="day")
    with pytest.raises(ValidationError, match="align"):
        TaxColumn("a", "b", ColumnKind.TEXT, "centre")
    with pytest.raises(ValidationError, match="kind"):
        TaxColumn("a", "b", "text", "left")  # type: ignore[arg-type]


def test_the_countries() -> None:
    assert dict(REGIMES) == {"it": ITALY}
    assert regime_for("it") is ITALY
    with pytest.raises(ValidationError, match="country must be one of \\['it'\\], got 'ch'"):
        regime_for("ch")
    with pytest.raises(ValidationError, match="Italian settings expected"):
        ITALY.report(None, object())  # type: ignore[arg-type]
