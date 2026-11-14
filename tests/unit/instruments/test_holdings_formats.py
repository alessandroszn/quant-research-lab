"""Holdings files as issuers publish them (design 8.2): country names and Excel workbooks.

All content is synthetic. Hand calculation for the name-based file below (weights in percent):

- United States: 40.0 + 25.0 = 65.0 % -> US 0.65;
- Japan 20.0 % -> JP 0.20; "Korea (South)" 10.0 % -> KR 0.10;
- "European Union" 4.0 % (a supranational bond) -> declared unknown, 0.04 with no country;
- "Cash and/or Derivatives" 1.0 % -> declared unknown.

The weights sum to 1.00, and 0.05 has no country.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import openpyxl
import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import (
    CountryFormat,
    HoldingsCsvMapping,
    HoldingsFileFormat,
    load_holdings_mapping,
    parse_holdings_csv,
    parse_holdings_file,
)
from qrlab.instruments.master import AssetClass

CONFIGS = Path(__file__).parents[3] / "configs"
EXAMPLE_MAPPING = CONFIGS / "csv_mappings" / "example_holdings.toml"

NAMES_CSV = (
    'Fund Holdings as of,"Oct 31, 2026"\n'
    'Inception Date,"Sep 25, 2009"\n'
    "\n"
    "Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Location,Currency\n"
    'AAA,ALPHA CORP,Information Technology,Equity,"1,234,567.00",40.00,United States,USD\n'
    'BBB,BETA INC,Health Care,Equity,"771,604.38",25.00,United States,USD\n'
    'CCC,GAMMA KK,Industrials,Equity,"617,283.50",20.00,Japan,JPY\n'
    'DDD,DELTA CO LTD,Financials,Equity,"308,641.75",10.00,Korea (South),KRW\n'
    'EU 0 01/01/30,EUROPEAN UNION,Government,Fixed Income,"123,456.70",4.00,European Union,EUR\n'
    'USD,USD CASH,Cash and/or Derivatives,Cash,"30,864.18",1.00,-,USD\n'
    "\n"
    '"Holdings are subject to change."\n'
)
NAMES_MAPPING = """\
file_format = "csv"
skip_rows = 3
delimiter = ","
decimal_separator = "."
thousands_separator = ","
encoding = "utf-8"
weight_unit = "percent"
missing_tokens = ["", "-"]
asset_class = "column"
country_format = "name"

[columns]
name = "Name"
weight = "Weight (%)"
country = "Location"
sector = "Sector"
currency = "Currency"
asset_class = "Asset Class"

[asset_class_values]
"Equity" = "equity"
"Fixed Income" = "fixed_income"
"Cash" = "cash"

[country_values]
"European Union" = "unknown"
"""


def _prov(content: bytes) -> Provenance:
    return Provenance(
        source="user",
        dataset="holdings_ie0000000012",
        url="file:holdings",
        retrieved_at=datetime(2026, 11, 14, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic",
    )


def _mapping(tmp: Path, text: str = NAMES_MAPPING) -> HoldingsCsvMapping:
    path = tmp / "mapping.toml"
    path.write_text(text, encoding="utf-8")
    return load_holdings_mapping(path)


def _parse(content: bytes, mapping: HoldingsCsvMapping):  # type: ignore[no-untyped-def]
    return parse_holdings_file(
        content,
        _prov(content),
        mapping,
        fund=Isin("IE0000000012"),
        as_of=date(2026, 10, 31),
        weight_basis="market value, % of NAV",
        sector_taxonomy="GICS",
    )


def _by_country(snapshot) -> dict[str | None, float]:  # type: ignore[no-untyped-def]
    table = snapshot.holdings
    out: dict[str | None, float] = {}
    for country, weight in zip(table["country"], table["weight"], strict=True):
        key = None if country is None or country != country else country  # NaN -> None
        out[key] = out.get(key, 0.0) + float(weight)
    return out


# ----------------------------------------------------------------------- country names
def test_country_names_by_hand(tmp_path: Path) -> None:
    snapshot = _parse(NAMES_CSV.encode("utf-8"), _mapping(tmp_path))
    countries = _by_country(snapshot)
    assert countries == pytest.approx({"US": 0.65, "JP": 0.20, "KR": 0.10, None: 0.05})
    assert snapshot.holdings["weight"].sum() == pytest.approx(1.0)
    assert "Country names converted to ISO 3166-1 alpha-2 codes." in snapshot.notes


def test_an_unknown_country_name_raises_with_its_line(tmp_path: Path) -> None:
    text = NAMES_CSV.replace("Korea (South)", "Atlantis")
    with pytest.raises(ParseError, match=r"line 8: unknown country name 'Atlantis'"):
        _parse(text.encode("utf-8"), _mapping(tmp_path))


def test_country_values_come_first(tmp_path: Path) -> None:
    mapping = _mapping(tmp_path, NAMES_MAPPING + '"Japan" = "unknown"\n')
    countries = _by_country(_parse(NAMES_CSV.encode("utf-8"), mapping))
    assert countries[None] == pytest.approx(0.25)
    assert "JP" not in countries


def test_iso_codes_still_read_as_before(tmp_path: Path) -> None:
    mapping = load_holdings_mapping(EXAMPLE_MAPPING)
    assert mapping.country_format is CountryFormat.ISO_ALPHA2
    assert mapping.file_format is HoldingsFileFormat.CSV
    text = NAMES_CSV.replace("United States", "US").replace("Korea (South)", "KR")
    text = text.replace("Japan", "JP").replace(",European Union,", ",-,")
    iso = replace(_mapping(tmp_path), country_format=CountryFormat.ISO_ALPHA2)
    assert _by_country(_parse(text.encode("utf-8"), iso)) == pytest.approx(
        {"US": 0.65, "JP": 0.20, "KR": 0.10, None: 0.05}
    )
    with pytest.raises(ParseError, match="line 5"):
        _parse(NAMES_CSV.encode("utf-8"), iso)  # names where codes are declared


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"country_values": {"Somewhere": "XX"}}, "country_values"),
        ({"country_values": {"": "US"}}, "country_values"),
        ({"country_format": "name"}, "CountryFormat"),
        ({"file_format": "csv"}, "HoldingsFileFormat"),
        ({"sheet": "Holdings"}, "sheet"),
        ({"delimiter": None}, "delimiter"),
        ({"encoding": None}, "encoding"),
    ],
)
def test_mapping_validation(tmp_path: Path, changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        replace(_mapping(tmp_path), **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ('country_format = "name"\n', "", "country_format"),
        ('country_format = "name"', 'country_format = "names"', "country_format"),
        ('file_format = "csv"\n', "", "file_format"),
        ('file_format = "csv"', 'file_format = "ods"', "file_format"),
        ('file_format = "csv"', 'file_format = "csv"\nsheet = "x"', "unexpected"),
        ('"European Union" = "unknown"', '"European Union" = "EU"', "country_values"),
    ],
)
def test_mapping_file_strictness(tmp_path: Path, old: str, new: str, match: str) -> None:
    assert old in NAMES_MAPPING
    with pytest.raises(ValidationError, match=match):
        _mapping(tmp_path, NAMES_MAPPING.replace(old, new, 1))


# ----------------------------------------------------------------------- Excel workbooks
XLSX_MAPPING = """\
file_format = "xlsx"
sheet = "Holdings"
skip_rows = 2
decimal_separator = "."
thousands_separator = ","
weight_unit = "percent"
missing_tokens = ["", "-"]
asset_class = "equity"
country_format = "name"

[columns]
name = "Holding name"
weight = "% of market value"
country = "Country"
sector = "Sector"
"""


def _workbook(rows: list[list[object]], sheet: str = "Holdings") -> bytes:
    book = openpyxl.Workbook()
    ws = book.active
    assert ws is not None
    ws.title = sheet
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


XLSX_ROWS: list[list[object]] = [
    ["Example All-World UCITS ETF"],
    ["As at 31 Oct 2026"],
    ["Holding name", "% of market value", "Sector", "Country", "Market value"],
    ["Alpha Corp", 40.0, "Technology", "United States", 1234567.0],
    ["Beta Inc", "25.00", "Health Care", "United States", 771604.38],  # a weight as text
    ["Gamma KK", 20.0, "Industrials", "Japan", 617283.5],
    ["Delta Co Ltd", 15.0, "Financials", "Korea (South)", 462962.6],
    [None, None, None, None, None],
    ["Data as at 31 Oct 2026. Holdings are subject to change."],
]


def test_xlsx_by_hand(tmp_path: Path) -> None:
    """40 + 25 = 65 % US, 20 % JP, 15 % KR; numeric and text weights read alike."""
    snapshot = _parse(_workbook(XLSX_ROWS), _mapping(tmp_path, XLSX_MAPPING))
    assert _by_country(snapshot) == pytest.approx({"US": 0.65, "JP": 0.20, "KR": 0.15})
    assert snapshot.holdings["name"].tolist() == [
        "Alpha Corp",
        "Beta Inc",
        "Gamma KK",
        "Delta Co Ltd",
    ]
    assert set(snapshot.holdings["asset_class"]) == {AssetClass.EQUITY.value}
    assert any("Ignored 1 line(s) after the first blank line" in n for n in snapshot.notes)
    assert any("sheet 'Holdings'" in n for n in snapshot.notes)


def test_xlsx_errors(tmp_path: Path) -> None:
    mapping = _mapping(tmp_path, XLSX_MAPPING)
    with pytest.raises(ParseError, match="no sheet 'Holdings'"):
        _parse(_workbook(XLSX_ROWS, sheet="Other"), mapping)
    with pytest.raises(ParseError, match="not a valid xlsx"):
        _parse(b"not a workbook", mapping)
    bad: list[list[object]] = [
        *XLSX_ROWS[:3],
        ["Alpha Corp", None, "Technology", "United States", 1.0],
    ]
    with pytest.raises(ParseError, match="line 4: weight is missing"):
        _parse(_workbook(bad), mapping)
    extra: list[list[object]] = [
        *XLSX_ROWS[:3],
        ["Alpha Corp", 40.0, "Technology", "United States", 1.0, "x"],
    ]
    with pytest.raises(ParseError, match="line 4: expected 5 fields"):
        _parse(_workbook(extra), mapping)
    with pytest.raises(ParseError, match="no header"):
        _parse(_workbook(XLSX_ROWS[:2]), mapping)
    with pytest.raises(ValidationError, match="parse_holdings_file"):
        parse_holdings_csv(
            b"x",
            _prov(b"x"),
            mapping,
            fund=Isin("IE0000000012"),
            as_of=date(2026, 10, 31),
            weight_basis="w",
            sector_taxonomy=None,
        )


def test_csv_through_the_general_parser_matches_parse_holdings_csv(tmp_path: Path) -> None:
    content = NAMES_CSV.encode("utf-8")
    mapping = _mapping(tmp_path)
    direct = parse_holdings_csv(
        content,
        _prov(content),
        mapping,
        fund=Isin("IE0000000012"),
        as_of=date(2026, 10, 31),
        weight_basis="market value, % of NAV",
        sector_taxonomy="GICS",
    )
    assert direct.holdings.equals(_parse(content, mapping).holdings)
