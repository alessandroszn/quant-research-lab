"""Vanguard files as published (design 8.2b), read with the committed mappings, by hand.

Synthetic workbooks with the layout of Vanguard's exports (real files stay in data/):

- **Holdings:** six preamble rows, the header, three made-up holdings, a blank row and a
  disclaimer. Weights are text with a percent sign: 4.7436 %, 0.25 % and 1.00 % give 0.047436,
  0.0025 and 0.01. The second has no ticker, the third no region.
- **Prices:** eight preamble rows, the header, four days newest first. The NAV is in USD
  (``$``) and the market price in EUR (``€``), empty on the first day. Read oldest first: NAV
  186.00, 187.50, 188.6596, 187.9772; EUR NaN, 170.91, 171.36, 169.874.
"""

from __future__ import annotations

import hashlib
import io
import math
from datetime import UTC, date, datetime
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.data.sheets import FileFormat
from qrlab.data.user_csv import (
    load_csv_mapping,
    parse_number,
    parse_price_csv,
)
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import load_holdings_mapping, parse_holdings_file

MAPPINGS = Path(__file__).parents[3] / "configs" / "csv_mappings"
FUND = "IE0000000012"  # the synthetic ISIN in the committed price mappings


def _workbook(sheet: str, rows: list[tuple[object, ...]]) -> bytes:
    book = openpyxl.Workbook()
    ws = book.active
    assert ws is not None
    ws.title = sheet
    for row in rows:
        ws.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _provenance(content: bytes) -> Provenance:
    return Provenance(
        source="test",
        dataset="vanguard",
        url="file:synthetic.xlsx",
        retrieved_at=datetime(2026, 11, 15, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic",
    )


HOLDINGS = _workbook(
    "Holdings details",
    [
        ("This file was downloaded on 15 Nov 2026",),
        (None,),
        ("Holdings details",),
        ("Example All-World UCITS ETF",),
        ("As at 31 Oct 2026",),
        (None,),
        ("Ticker", "Holding name", "% of market value", "Sector", "Region", "Market value",
         "Shares"),
        ("AAA", "Alpha Corp", "4.7436%", "Technology", "US", "$4,239,627,231.84", "12,301,968"),
        (None, "Beta PLC", "0.25%", None, "GB", "$0.02", "1,651"),
        ("CCC", "Gamma SA", "1.00%", "Financials", None, "$5.00", "5"),
        (None,),
        ("Total allocation percentages may not equal 100%.",),
    ],
)  # fmt: skip

PRICES = _workbook(
    "Historical Prices",
    [
        ("This file was downloaded on 15 Nov 2026",),
        ("Historical Prices",),
        (None,),
        ("Example All-World UCITS ETF",),
        (None,),
        ("Inception date", "23 Jul 2019"),
        ("Listing date", "11 Nov 2026"),
        (None,),
        ("Date", "NAV (USD)", "Market price (EUR)"),
        ("13 Nov 2026", "$187.9772", "€169.8740"),
        ("12 Nov 2026", "$188.6596", "€171.3600"),
        ("11 Nov 2026", "$187.5000", "€170.9100"),
        ("10 Nov 2026", "$186.0000", None),
    ],
)


def _snapshot(content: bytes = HOLDINGS):  # type: ignore[no-untyped-def]
    return parse_holdings_file(
        content,
        _provenance(content),
        load_holdings_mapping(MAPPINGS / "vanguard_holdings.toml"),
        fund=Isin(FUND),
        as_of=date(2026, 10, 31),
        weight_basis="market value",
        sector_taxonomy="Vanguard (ICB)",
    )


# --------------------------------------------------------------------------- holdings
def test_vanguard_holdings_by_hand() -> None:
    frame = _snapshot().holdings
    assert frame["name"].tolist() == ["Alpha Corp", "Beta PLC", "Gamma SA"]
    assert frame["weight"].tolist() == pytest.approx([0.047436, 0.0025, 0.01], abs=1e-15)
    assert frame["country"].tolist()[:2] == ["US", "GB"]
    assert pd.isna(frame["country"].iloc[2])
    assert pd.isna(frame["sector"].iloc[1])
    assert set(frame["asset_class"]) == {"equity"}
    notes = " ".join(_snapshot().notes)
    assert "xlsx" in notes


def test_a_symbol_that_is_not_declared_raises() -> None:
    content = HOLDINGS  # the same workbook, rebuilt with a dollar weight
    book = openpyxl.load_workbook(io.BytesIO(content))
    book.active["C8"] = "$4.7436"  # type: ignore[index]
    buffer = io.BytesIO()
    book.save(buffer)
    with pytest.raises(ParseError, match="unexpected character '\\$'"):
        _snapshot(buffer.getvalue())


# --------------------------------------------------------------------------- prices
def test_vanguard_prices_in_both_currencies_by_hand() -> None:
    eur = parse_price_csv(
        PRICES, _provenance(PRICES), load_csv_mapping(MAPPINGS / "vanguard_prices_market_eur.toml")
    )
    usd = parse_price_csv(
        PRICES, _provenance(PRICES), load_csv_mapping(MAPPINGS / "vanguard_prices_nav_usd.toml")
    )
    days = pd.DatetimeIndex(["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"])
    assert eur.dataset.data.index.equals(days)
    assert usd.dataset.data.index.equals(days)
    nav = usd.dataset.data[FUND].tolist()
    assert nav == pytest.approx([186.0, 187.5, 188.6596, 187.9772], abs=1e-12)
    market = eur.dataset.data[FUND].tolist()
    assert math.isnan(market[0])
    assert market[1:] == pytest.approx([170.91, 171.36, 169.874], abs=1e-12)
    assert (str(eur.dataset.currency), str(usd.dataset.currency)) == ("EUR", "USD")
    assert eur.price_types[FUND].value == "price"
    assert usd.price_types[FUND].value == "nav"
    notes = " ".join(eur.dataset.notes)
    assert "Rows reversed" in notes
    assert "NAV (USD)" in notes  # the other currency's column is listed as ignored


def _price_mapping(tmp: Path, **changes: str) -> Path:
    text = (MAPPINGS / "vanguard_prices_nav_usd.toml").read_text(encoding="utf-8")
    for old, new in changes.items():
        assert old in text, old
        text = text.replace(old, new)
    path = tmp / "m.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("changes", "error", "match"),
    [
        ({'value_affixes = ["$"]': "value_affixes = []"}, ParseError, "unexpected character"),
        ({'sheet = "Historical Prices"': 'sheet = "Prices"'}, ParseError, "no sheet 'Prices'"),
        ({"skip_rows = 8": "skip_rows = 40"}, ParseError, "no header after skipping 40"),
        ({"skip_rows = 8": "skip_rows = 9"}, ParseError, "column 'Date' not found"),
    ],
)
def test_wrong_price_mappings_raise(
    tmp_path: Path, changes: dict[str, str], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        parse_price_csv(
            PRICES, _provenance(PRICES), load_csv_mapping(_price_mapping(tmp_path, **changes))
        )


def test_a_blank_row_after_the_preamble_is_skipped(tmp_path: Path) -> None:
    """With skip_rows = 7 the first row read is blank; the header is the next one."""
    mapping = load_csv_mapping(_price_mapping(tmp_path, **{"skip_rows = 8": "skip_rows = 7"}))
    data = parse_price_csv(PRICES, _provenance(PRICES), mapping)
    assert len(data.dataset.data) == 4


def test_english_month_names_only() -> None:
    italian = PRICES
    book = openpyxl.load_workbook(io.BytesIO(italian))
    book.active["A10"] = "13 Dic 2026"  # type: ignore[index]
    buffer = io.BytesIO()
    book.save(buffer)
    mapping = load_csv_mapping(MAPPINGS / "vanguard_prices_nav_usd.toml")
    with pytest.raises(ParseError, match="line 10: invalid date '13 Dic 2026'"):
        parse_price_csv(buffer.getvalue(), _provenance(PRICES), mapping)


# --------------------------------------------------------------------------- parsing rules
@pytest.mark.parametrize(
    ("text", "affixes", "expected"),
    [
        ("$4,239.84", ("$",), 4239.84),
        ("-$5.00", ("$",), -5.0),
        ("4.7436%", ("%",), 4.7436),
        ("€169.8740", ("€", "$"), 169.874),
        ("12", ("%",), 12.0),
    ],
)
def test_declared_affixes_are_removed(text: str, affixes: tuple[str, ...], expected: float) -> None:
    value = parse_number(
        text, decimal_separator=".", thousands_separator=",", line=1, affixes=affixes
    )
    assert value == expected


def test_an_affix_in_the_middle_still_raises() -> None:
    with pytest.raises(ParseError, match="unexpected character"):
        parse_number("4$2", decimal_separator=".", thousands_separator=",", line=1, affixes=("$",))


def test_price_mapping_rules(tmp_path: Path) -> None:
    mapping = load_csv_mapping(MAPPINGS / "vanguard_prices_nav_usd.toml")
    assert mapping.file_format is FileFormat.XLSX
    assert (mapping.sheet, mapping.skip_rows, mapping.value_affixes) == (
        "Historical Prices",
        8,
        ("$",),
    )
    with pytest.raises(ValidationError, match="value_affixes"):
        load_csv_mapping(_price_mapping(tmp_path, **{'["$"]': '["1"]'}))
    with pytest.raises(ValidationError, match="date_format"):
        load_csv_mapping(_price_mapping(tmp_path, **{"%d %b %Y": "%d %Y"}))
    with pytest.raises(ValidationError, match="unexpected keys"):
        load_csv_mapping(
            _price_mapping(tmp_path, **{"skip_rows = 8": 'skip_rows = 8\ndelimiter = ","'})
        )


def test_an_xlsx_with_real_dates_and_numbers(tmp_path: Path) -> None:
    """Date cells and numeric cells, as a hand-made workbook may have them, are read as they are."""
    content = _workbook(
        "Prices",
        [("Date", "NAV"), (datetime(2026, 11, 12), 101.5), (datetime(2026, 11, 13), 102.0)],
    )
    mapping = _price_mapping(
        tmp_path,
        **{
            'sheet = "Historical Prices"': 'sheet = "Prices"',
            "skip_rows = 8": "skip_rows = 0",
            '[columns."NAV (USD)"]': '[columns."NAV"]',
        },
    )
    data = parse_price_csv(content, _provenance(content), load_csv_mapping(mapping))
    assert data.dataset.data.index.equals(pd.DatetimeIndex(["2026-11-12", "2026-11-13"]))
    assert data.dataset.data[FUND].tolist() == [101.5, 102.0]


def test_empty_and_symbol_only_cells(tmp_path: Path) -> None:
    empty = _workbook("Historical Prices", [(None,)] * 10)
    mapping = load_csv_mapping(MAPPINGS / "vanguard_prices_nav_usd.toml")
    with pytest.raises(ParseError, match="file has no header"):
        parse_price_csv(empty, _provenance(empty), mapping)
    with pytest.raises(ParseError, match=r"'\$' has a symbol but no number"):
        parse_number("$", decimal_separator=".", thousands_separator=",", line=3, affixes=("$",))


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({'file_format = "xlsx"\n': ""}, r"missing keys \['file_format'\]"),
        ({'file_format = "xlsx"': 'file_format = "ods"'}, "unknown file_format 'ods'"),
        ({'value_affixes = ["$"]': 'value_affixes = "$"'}, "must be a list of text"),
    ],
)
def test_wrong_price_mapping_files(tmp_path: Path, changes: dict[str, str], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        load_csv_mapping(_price_mapping(tmp_path, **changes))


def test_mapping_fields_are_checked() -> None:
    from dataclasses import replace

    mapping = load_csv_mapping(MAPPINGS / "vanguard_prices_nav_usd.toml")
    with pytest.raises(ValidationError, match="file_format must be a FileFormat"):
        replace(mapping, file_format="xlsx")  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="skip_rows must be a non-negative int"):
        replace(mapping, skip_rows=-1)
    with pytest.raises(ValidationError, match="an xlsx or spreadsheetml mapping needs a sheet"):
        replace(mapping, sheet=None)
    with pytest.raises(ValidationError, match="a CSV mapping has no sheet"):
        replace(mapping, file_format=FileFormat.CSV, delimiter=",", encoding="utf-8")
