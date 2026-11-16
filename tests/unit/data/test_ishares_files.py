"""iShares files as published (design 8.2c), read with the committed mappings, by hand.

Synthetic files with the layout of the Italian website's exports (real files stay in data/):

- **Holdings CSV.** UTF-8 with a BOM; ``Al,"13/11/2026"``, a non-breaking space, the header,
  four made-up holdings with Italian numbers and Italian country names, then a non-breaking
  space. Weights 5,82 / 1,00 / 0,00 / 0,10 % give 0.0582, 0.01, 0 and 0.001; "Stati Uniti" is
  US, "Regno unito" GB, "-" and "Unione Europea" no country; Azionario is equity, Contanti
  cash, Futures other.
- **Fund data (SpreadsheetML).** Two BOMs, then an XML workbook with an "Introduzione" sheet
  and a "Storico" sheet: four days newest first, NAVs as numeric cells (144.368418,
  144.89836, 145.343435) and "--" on the oldest day (missing, as in the real file), one row
  with a sparse cell (``ss:Index``). Read oldest first.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.data.sheets import read_spreadsheetml_rows
from qrlab.data.user_csv import load_csv_mapping, parse_price_csv
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import load_holdings_mapping, parse_holdings_file

MAPPINGS = Path(__file__).parents[3] / "configs" / "csv_mappings"
FUND = "IE0000000012"
NBSP = chr(0xA0)  # a non-breaking space, as in the real file
HEADER = (
    "Ticker dell'emittente,Nome,Settore,Asset Class,Valore di mercato,Ponderazione (%),"
    "Valore nozionale,Nominale,Prezzo,Area Geografica,Cambio,Valuta di mercato"
)
ROWS = (
    '"AAA","ALPHA CORP","IT","Azionario","8.737.131.990,62","5,82","8.737.131.990,62",'
    '"24.523.906,00","356,27","Stati Uniti","NASDAQ","USD"',
    '"BBB","BETA PLC","Finanziari","Azionario","1.500.000,00","1,00","1.500.000,00",'
    '"10.000,00","150,00","Regno unito","London Stock Exchange","GBP"',
    '"ESZ6","S&P500 EMINI DEC 26","Liquidità e/o derivati","Futures","0,00","0,00",'
    '"519.056.350,00","1.369,00","7.583,00","-","Index And Options Market","USD"',
    '"EUR","EUR CASH","Liquidità e/o derivati","Contanti","150.000,00","0,10","150.000,00",'
    '"150.000,00","100,00","Unione Europea","-","EUR"',
)
HOLDINGS = (
    "﻿"
    + "\n".join(['Al,"13/11/2026"', NBSP, HEADER, *ROWS, NBSP])
    + "\n"
).encode("utf-8")  # fmt: skip


def _row(*cells: tuple[str, str] | None, index: int | None = None) -> str:
    parts = []
    for cell in cells:
        if cell is None:
            continue
        kind, value = cell
        parts.append(f'<ss:Cell><ss:Data ss:Type="{kind}">{value}</ss:Data></ss:Cell>')
    if index is not None:  # a sparse last cell, placed in column ``index``
        parts.append(
            f'<ss:Cell ss:Index="{index}"><ss:Data ss:Type="String">--</ss:Data></ss:Cell>'
        )
    return "<ss:Row>" + "".join(parts) + "</ss:Row>"


def _workbook(storico: list[str], extra: str = "") -> bytes:
    text = (
        '<?xml version="1.0"?>\n' + extra
        + '<ss:Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
        + '<ss:Worksheet ss:Name="Introduzione"><ss:Table>'
        + _row(("String", "iShares Example UCITS ETF"))
        + "</ss:Table></ss:Worksheet>"
        + '<ss:Worksheet ss:Name="Storico"><ss:Table>' + "".join(storico)
        + "</ss:Table></ss:Worksheet></ss:Workbook>"
    )  # fmt: skip
    return ("﻿﻿" + text).encode("utf-8")


STORICO = [
    _row(("String", "Al"), ("String", "Currency"), ("String", "NAV"), ("String", "Asset netti")),
    _row(("String", "13/11/2026"), ("String", "USD"), ("Number", "144.368418"), index=4),
    _row(("String", "12/11/2026"), ("String", "USD"), ("Number", "144.89836"), ("Number", "1")),
    _row(("String", "11/11/2026"), ("String", "USD"), ("Number", "145.343435"), ("Number", "2")),
    _row(("String", "10/11/2026"), ("String", "USD"), ("String", "--"), ("String", "--")),
]
FUND_DATA = _workbook(STORICO)


def _provenance(content: bytes) -> Provenance:
    return Provenance(
        source="test",
        dataset="ishares",
        url="file:synthetic",
        retrieved_at=datetime(2026, 11, 16, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic",
    )


# --------------------------------------------------------------------------- holdings
def test_ishares_holdings_by_hand() -> None:
    snapshot = parse_holdings_file(
        HOLDINGS,
        _provenance(HOLDINGS),
        load_holdings_mapping(MAPPINGS / "ishares_holdings_it.toml"),
        fund=Isin(FUND),
        as_of=date(2026, 11, 13),
        weight_basis="market value",
        sector_taxonomy="iShares (GICS, Italian names)",
    )
    frame = snapshot.holdings
    assert frame["name"].tolist() == ["ALPHA CORP", "BETA PLC", "S&P500 EMINI DEC 26", "EUR CASH"]
    assert frame["weight"].tolist() == pytest.approx([0.0582, 0.01, 0.0, 0.001], abs=1e-15)
    assert frame["country"].tolist()[:2] == ["US", "GB"]
    assert frame["country"].iloc[2:].isna().all()
    assert frame["asset_class"].tolist() == ["equity", "equity", "other", "cash"]
    assert frame["currency"].tolist() == ["USD", "GBP", "USD", "EUR"]
    assert "Skipped 2 preamble line(s) before the header." in snapshot.notes


def test_an_unlisted_country_name_raises_with_its_line() -> None:
    content = HOLDINGS.replace(b"Regno unito", b"Atlantide")
    with pytest.raises(ParseError, match="line 5"):
        parse_holdings_file(
            content,
            _provenance(content),
            load_holdings_mapping(MAPPINGS / "ishares_holdings_it.toml"),
            fund=Isin(FUND),
            as_of=date(2026, 11, 13),
            weight_basis="market value",
            sector_taxonomy=None,
        )


# --------------------------------------------------------------------------- NAV history
def test_ishares_nav_history_by_hand() -> None:
    data = parse_price_csv(
        FUND_DATA, _provenance(FUND_DATA), load_csv_mapping(MAPPINGS / "ishares_nav.toml")
    )
    days = pd.DatetimeIndex(["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"])
    assert data.dataset.data.index.equals(days)
    nav = data.dataset.data[FUND].tolist()
    assert math.isnan(nav[0])  # "--": no NAV that day, kept missing, never filled
    assert nav[1:] == [145.343435, 144.89836, 144.368418]
    assert str(data.dataset.currency) == "USD"
    assert data.price_types[FUND].value == "nav"
    notes = " ".join(data.dataset.notes)
    assert "Read sheet 'Storico' of an XML spreadsheet (SpreadsheetML)." in notes
    assert "Cells equal to ['--'] treated as unknown." in notes


def test_missing_tokens_must_be_text(tmp_path: Path) -> None:
    text = (MAPPINGS / "ishares_nav.toml").read_text(encoding="utf-8")
    path = tmp_path / "m.toml"
    path.write_text(
        text.replace('missing_tokens = ["--"]', "missing_tokens = [1]"), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="missing_tokens must be a list of text"):
        load_csv_mapping(path)


def test_the_reader_places_sparse_cells_and_skips_boms() -> None:
    rows = read_spreadsheetml_rows(FUND_DATA, sheet="Storico", skip_rows=0)
    assert rows[0] == ["Al", "Currency", "NAV", "Asset netti"]
    assert rows[1] == ["13/11/2026", "USD", 144.368418, "--"]
    assert rows[2][3] == 1.0
    assert read_spreadsheetml_rows(FUND_DATA, sheet="Storico", skip_rows=2)[0][0] == "12/11/2026"


@pytest.mark.parametrize(
    ("content", "sheet", "skip", "match"),
    [
        (FUND_DATA, "Prezzi", 0, "no sheet 'Prezzi' in the workbook: \\['Introduzione'"),
        (FUND_DATA, "Storico", 9, "no header after skipping 9"),
        (b"not xml at all", "Storico", 0, "not a valid XML spreadsheet"),
        (
            _workbook(STORICO, extra='<!DOCTYPE x [<!ENTITY a "boom">]>\n'),
            "Storico",
            0,
            "DOCTYPE or entity declarations are refused",
        ),
        (b'<?xml version="1.0"?><other/>', "Storico", 0, "not a valid XML spreadsheet"),
    ],
)  # fmt: skip
def test_wrong_files_raise(content: bytes, sheet: str, skip: int, match: str) -> None:
    with pytest.raises(ParseError, match=match):
        read_spreadsheetml_rows(content, sheet=sheet, skip_rows=skip)


def test_a_holdings_sheet_in_spreadsheetml(tmp_path: Path) -> None:
    """The holdings mapping may read the workbook's sheet too, with the same rules."""
    sheet = [
        _row(("String", "Nome"), ("String", "Ponderazione (%)")),
        _row(("String", "ALPHA CORP"), ("Number", "5.82")),
    ]
    content = _workbook(sheet).replace(b'ss:Name="Storico"', b'ss:Name="Partecipazioni"')
    mapping = tmp_path / "m.toml"
    mapping.write_text(
        'file_format = "spreadsheetml"\nsheet = "Partecipazioni"\nskip_rows = 0\n'
        'decimal_separator = "."\nthousands_separator = ""\nvalue_affixes = []\n'
        'weight_unit = "percent"\nmissing_tokens = [""]\nasset_class = "equity"\n'
        'country_format = "iso_alpha2"\n\n[columns]\nname = "Nome"\nweight = "Ponderazione (%)"\n',
        encoding="utf-8",
    )
    snapshot = parse_holdings_file(
        content,
        _provenance(content),
        load_holdings_mapping(mapping),
        fund=Isin(FUND),
        as_of=date(2026, 11, 13),
        weight_basis="market value",
        sector_taxonomy=None,
    )
    assert snapshot.holdings["weight"].tolist() == pytest.approx([0.0582])
    assert "Read sheet 'Partecipazioni' of an XML spreadsheet (SpreadsheetML)." in snapshot.notes


def test_a_cell_without_data_is_empty() -> None:
    row = (
        '<ss:Row><ss:Cell><ss:Data ss:Type="String">x</ss:Data></ss:Cell><ss:Cell/>'
        '<ss:Cell><ss:Data ss:Type="String">y</ss:Data></ss:Cell></ss:Row>'
    )
    rows = read_spreadsheetml_rows(_workbook([row]), sheet="Storico", skip_rows=0)
    assert rows == [["x", None, "y"]]
