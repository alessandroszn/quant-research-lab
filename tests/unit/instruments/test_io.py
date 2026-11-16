"""Loading master data (TOML) and holdings (CSV + explicit mapping). All content is synthetic.

Hand calculation: a holdings row ``Alpha Corp,US0378331005,"1,234.5"`` is not a weight; a row
with ``Weight (%)`` = ``60.00`` and unit ``percent`` becomes weight 0.60.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.io import (
    HoldingsCsvMapping,
    WeightUnit,
    load_holdings_mapping,
    load_instruments,
    parse_holdings_csv,
)
from qrlab.instruments.master import AssetClass, Distribution, InstrumentType, Replication

CONFIGS = Path(__file__).parents[3] / "configs"
INSTRUMENTS = CONFIGS / "instruments" / "example.toml"
HOLDINGS_MAPPING = CONFIGS / "csv_mappings" / "example_holdings.toml"

HOLDINGS_CSV = (
    "Example World Equity UCITS ETF\n"
    "Holdings as of 31 Oct 2026\n"
    "Name,ISIN,Weight (%),Country Code,Sector,Currency,Asset Class,Price\n"
    'Alpha Corp,US0378331005,60.00,US,Information Technology,USD,Equity,"1,234.50"\n'
    "Beta Corp,LU0274208692,39.50,LU,Financials,EUR,Equity,10.00\n"
    "Cash USD,-,0.50,-,-,USD,Cash,-\n"
    "\n"
    "The content of this file is provided for information only.\n"
)


# --------------------------------------------------------------------------- master data
def test_example_instruments_load() -> None:
    records = {r.isin.code: r for r in load_instruments(INSTRUMENTS)}
    etf = records["IE0000000012"]
    assert etf.instrument_type is InstrumentType.ETF
    assert etf.replication is Replication.PHYSICAL_SAMPLING
    assert etf.distribution is Distribution.ACCUMULATING
    assert etf.ter == Decimal("0.0020")
    assert etf.as_of == date(2026, 10, 1)
    assert etf.hedged_to is None
    assert etf.fund_size == Money.of("85000000000", "USD")
    hedged = records["LU0000000025"]
    assert hedged.hedged_to == Currency("EUR")
    assert hedged.benchmark is None
    assert hedged.inception is None
    stock = records["US0000000044"]
    assert stock.ter is None
    assert stock.replication is None


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "instruments.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ('ter = "0.0020"', "ter = 0.0020", "quoted"),
        ('ter = "0.0020"', 'ter = "0.20"', "TER"),
        ('domicile = "IE"\n', "", "missing"),
        ('source = "KID dated 2026-03"', 'source = "KID"\ncolour = "blue"', "unexpected"),
        ('replication = "physical_sampling"', 'replication = "physical"', "replication"),
        (
            'hedged_to = "none"\ninception = 2009',
            'hedged_to = "unknown"\ninception = 2009',
            "hedged_to",
        ),
        ("as_of = 2026-10-01", 'as_of = "unknown"', "as_of"),
        ("[IE0000000012]", "[IE0000000013]", "ISIN"),
        ("as_of = 2026-10-01", "as_of = 2026-10-01T10:00:00", "as_of"),
        (
            'fund_size = { amount = "85000000000", currency = "USD" }',
            "fund_size = 85000000000",
            "fund_size",
        ),
        (
            'fund_size = { amount = "85000000000", currency = "USD" }',
            'fund_size = { amount = 1, currency = "USD" }',
            "quoted",
        ),
    ],
)
def test_instrument_file_strictness(tmp_path: Path, old: str, new: str, match: str) -> None:
    text = INSTRUMENTS.read_text(encoding="utf-8")
    assert old in text
    with pytest.raises(ValidationError, match=match):
        load_instruments(_write(tmp_path, text.replace(old, new, 1)))


def test_empty_instrument_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="no instruments"):
        load_instruments(_write(tmp_path, "# nothing\n"))


# --------------------------------------------------------------------------- holdings
def _prov(content: bytes) -> Provenance:
    return Provenance(
        source="user",
        dataset="holdings_ie0000000012",
        url="file:holdings.csv",
        retrieved_at=datetime(2026, 11, 3, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic",
    )


def _parse(text: str = HOLDINGS_CSV, mapping: HoldingsCsvMapping | None = None):  # type: ignore[no-untyped-def]
    content = text.encode("utf-8")
    return parse_holdings_csv(
        content,
        _prov(content),
        mapping or load_holdings_mapping(HOLDINGS_MAPPING),
        fund=Isin("IE0000000012"),
        as_of=date(2026, 10, 31),
        weight_basis="market value, % of NAV",
        sector_taxonomy="GICS",
    )


def test_holdings_hand_example() -> None:
    snapshot = _parse()
    table = snapshot.holdings
    assert table["weight"].tolist() == pytest.approx([0.60, 0.395, 0.005])
    assert table["name"].tolist() == ["Alpha Corp", "Beta Corp", "Cash USD"]
    assert table.loc[2, "isin"] is None
    assert table.loc[2, "country"] is None
    assert table["asset_class"].tolist() == ["equity", "equity", "cash"]
    assert any("percent" in note for note in snapshot.notes)
    assert any("1 line" in note and "after" in note for note in snapshot.notes)
    assert any("Price" in note for note in snapshot.notes)


def test_fixed_asset_class_when_no_column() -> None:
    mapping = load_holdings_mapping(HOLDINGS_MAPPING)
    columns = {k: v for k, v in mapping.columns.items() if k != "asset_class"}
    fixed = replace(mapping, columns=columns, asset_class=AssetClass.EQUITY, asset_class_values={})
    assert set(_parse(mapping=fixed).holdings["asset_class"]) == {"equity"}


def test_decimal_weights() -> None:
    mapping = replace(load_holdings_mapping(HOLDINGS_MAPPING), weight_unit=WeightUnit.DECIMAL)
    text = (
        HOLDINGS_CSV.replace("60.00", "0.6").replace("39.50", "0.395").replace(",0.50,", ",0.005,")
    )
    assert _parse(text, mapping).holdings["weight"].tolist() == pytest.approx([0.6, 0.395, 0.005])


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("Weight (%)", "Weight", "Weight \\(%\\)"),
        (",Equity,", ",Stocks,", "asset class"),
        ("60.00", "-", "weight"),
        ("60.00", "sixty", "character"),
        ("Cash USD,-,0.50", "Cash USD,-,0.50,extra", "fields"),
        ('"1,234.50"', "1,234.50", "fields"),  # unquoted thousands separator = delimiter
        (",US,Information", ",United States,Information", "country"),
    ],
)
def test_holdings_strictness(old: str, new: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _parse(HOLDINGS_CSV.replace(old, new, 1))


def test_holdings_without_rows_raise() -> None:
    text = "\n".join(HOLDINGS_CSV.splitlines()[:3]) + "\n"
    with pytest.raises(ParseError, match="no holdings"):
        _parse(text)


def test_holdings_with_too_few_lines_for_the_header_raise() -> None:
    with pytest.raises(ParseError, match="header"):
        _parse("only one line\n")


def test_holdings_undecodable_raise() -> None:
    content = HOLDINGS_CSV.encode("utf-8") + b"\xff"
    with pytest.raises(ParseError, match="decode"):
        parse_holdings_csv(
            content,
            _prov(content),
            load_holdings_mapping(HOLDINGS_MAPPING),
            fund=Isin("IE0000000012"),
            as_of=date(2026, 10, 31),
            weight_basis="market value",
            sector_taxonomy="GICS",
        )


# --------------------------------------------------------------------------- mapping validation
def test_example_holdings_mapping_loads() -> None:
    mapping = load_holdings_mapping(HOLDINGS_MAPPING)
    assert mapping.skip_rows == 2
    assert mapping.weight_unit is WeightUnit.PERCENT
    assert mapping.missing_tokens == ("", "-")
    assert mapping.asset_class is None
    assert mapping.asset_class_values["Money Market"] is AssetClass.MONEY_MARKET


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"columns": {"name": "Name"}}, "weight"),
        ({"columns": {"name": "Name", "weight": "W", "ticker": "T"}}, "ticker"),
        ({"asset_class": AssetClass.EQUITY}, "exactly one"),
        ({"asset_class_values": {}}, "asset_class_values"),
        ({"skip_rows": -1}, "skip_rows"),
        ({"delimiter": ":"}, "delimiter"),
        ({"decimal_separator": ","}, "differ"),
        ({"encoding": "nope"}, "encoding"),
    ],
)
def test_holdings_mapping_validation(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        replace(load_holdings_mapping(HOLDINGS_MAPPING), **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ('weight_unit = "percent"', 'weight_unit = "basis_points"', "weight_unit"),
        ('asset_class = "column"', 'asset_class = "stocks"', "asset_class"),
        ('"Cash" = "cash"', '"Cash" = "money"', "Cash"),
        ("skip_rows = 2", "skip_rows = 2\nextra = 1", "unexpected"),
    ],
)
def test_holdings_mapping_file_strictness(tmp_path: Path, old: str, new: str, match: str) -> None:
    text = HOLDINGS_MAPPING.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "mapping.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        load_holdings_mapping(path)


def test_minimal_file_without_trailer_or_extra_columns() -> None:
    mapping = replace(
        load_holdings_mapping(HOLDINGS_MAPPING),
        skip_rows=0,
        weight_unit=WeightUnit.DECIMAL,
        columns={"name": "Name", "weight": "Weight"},
        asset_class=AssetClass.EQUITY,
        asset_class_values={},
    )
    content = b"Name,Weight\nAlpha Corp,0.6\nBeta Corp,0.4\n"
    snapshot = parse_holdings_csv(
        content,
        _prov(content),
        mapping,
        fund=Isin("IE0000000012"),
        as_of=date(2026, 10, 31),
        weight_basis="market value",
        sector_taxonomy=None,
    )
    assert snapshot.holdings["sector"].isna().all()
    assert not any("Ignored" in note for note in snapshot.notes)
    assert not any("percent" in note for note in snapshot.notes)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"decimal_separator": ";"}, "decimal_separator"),
        ({"delimiter": ";", "decimal_separator": ",", "thousands_separator": "."}, None),
        # A comma delimiter with comma decimals is allowed since 8.2c: numbers are quoted, and
        # an unquoted one changes the field count, which is rejected per row.
        ({"delimiter": ",", "decimal_separator": ",", "thousands_separator": "."}, None),
        ({"weight_unit": "percent"}, "WeightUnit"),
    ],
)
def test_more_mapping_validation(changes: dict[str, object], match: str | None) -> None:
    base = load_holdings_mapping(HOLDINGS_MAPPING)
    if match is None:
        assert replace(base, **changes).delimiter == changes["delimiter"]  # type: ignore[arg-type]
    else:
        with pytest.raises(ValidationError, match=match):
            replace(base, **changes)  # type: ignore[arg-type]


def test_non_numeric_ter_string_raises(tmp_path: Path) -> None:
    text = INSTRUMENTS.read_text(encoding="utf-8").replace('ter = "0.0020"', 'ter = "low"', 1)
    with pytest.raises(ValidationError, match="decimal number"):
        load_instruments(_write(tmp_path, text))
