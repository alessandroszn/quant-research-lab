"""User-supplied price CSVs with an explicit mapping. All files here are synthetic.

Hand calculations:

- ``01/12/2026;1.234,56;99,5`` with decimal ``,`` and thousands ``.`` -> 2026-12-01: 1234.56, 99.5
- ``1.5`` in a file whose decimal separator is ``,`` is ambiguous -> error, never 1.5 or 15
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance, Unit
from qrlab.data.sheets import FileFormat
from qrlab.data.store import RawStore
from qrlab.data.user_csv import (
    ColumnSpec,
    CsvMapping,
    PriceType,
    import_local_file,
    load_csv_mapping,
    parse_price_csv,
)

EXAMPLE_CONFIG = Path(__file__).parents[3] / "configs" / "csv_mappings" / "example_prices.toml"

CSV = (
    "Data;Chiusura ETF A;NAV ETF B;Note\n"
    "01/12/2026;1.234,56;99,5;x\n"
    "02/12/2026;1.240,00;;y\n"
    "03/12/2026;1.250,10;100,25;z\n"
)


def _mapping(**changes: object) -> CsvMapping:
    base = CsvMapping(
        date_column="Data",
        date_format="%d/%m/%Y",
        delimiter=";",
        decimal_separator=",",
        thousands_separator=".",
        encoding="utf-8",
        currency=Currency("EUR"),
        frequency=Frequency.DAILY,
        columns={
            "Chiusura ETF A": ColumnSpec("EXAMPLE_ETF_A", PriceType.PRICE),
            "NAV ETF B": ColumnSpec("EXAMPLE_ETF_B", PriceType.NAV),
        },
        file_format=FileFormat.CSV,
        sheet=None,
        skip_rows=0,
        value_affixes=(),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def _prov(content: bytes) -> Provenance:
    return Provenance(
        source="user",
        dataset="prices",
        url="file:prices.csv",
        retrieved_at=datetime(2026, 12, 4, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="user-supplied",
    )


def _parse(text: str, mapping: CsvMapping | None = None, encoding: str = "utf-8"):  # type: ignore[no-untyped-def]
    content = text.encode(encoding)
    return parse_price_csv(content, _prov(content), mapping or _mapping())


# --------------------------------------------------------------------------- hand examples
def test_italian_number_format_hand_example() -> None:
    result = _parse(CSV)
    data = result.dataset.data
    assert list(data.columns) == ["EXAMPLE_ETF_A", "EXAMPLE_ETF_B"]
    assert data.loc["2026-12-01"].tolist() == [1234.56, 99.5]
    assert np.isnan(data.loc["2026-12-02", "EXAMPLE_ETF_B"])  # empty cell: missing, not filled
    assert result.price_types == {
        "EXAMPLE_ETF_A": PriceType.PRICE,
        "EXAMPLE_ETF_B": PriceType.NAV,
    }


def test_metadata() -> None:
    ds = _parse(CSV).dataset
    assert ds.unit is Unit.PRICE
    assert ds.currency == Currency("EUR")
    assert ds.return_kind is None
    assert any("EXAMPLE_ETF_A: price" in note for note in ds.notes)
    assert any("Note" in note for note in ds.notes)  # ignored columns are reported


def test_descending_file_is_reversed_and_noted() -> None:
    lines = CSV.splitlines()
    text = "\n".join([lines[0], *reversed(lines[1:])]) + "\n"
    ds = _parse(text).dataset
    assert ds.data.index.is_monotonic_increasing
    assert any("reversed" in note for note in ds.notes)


def test_point_decimal_without_thousands() -> None:
    text = "Date,A\n2026-12-01,1234.5\n2026-12-02,1240\n"
    mapping = _mapping(
        date_column="Date",
        date_format="%Y-%m-%d",
        delimiter=",",
        decimal_separator=".",
        thousands_separator=None,
        columns={"A": ColumnSpec("X", PriceType.TOTAL_RETURN)},
    )
    assert _parse(text, mapping).dataset.data["X"].tolist() == [1234.5, 1240.0]


def test_windows_encoding() -> None:
    text = "Data;Prezzo €\n01/12/2026;1,5\n02/12/2026;1,6\n"
    mapping = _mapping(encoding="cp1252", columns={"Prezzo €": ColumnSpec("X", PriceType.PRICE)})
    assert _parse(text, mapping, encoding="cp1252").dataset.data["X"].tolist() == [1.5, 1.6]


# --------------------------------------------------------------------------- strictness
@pytest.mark.parametrize(
    ("value", "match"),
    [
        ("1.5", "number"),  # '.' is the thousands separator here: bad grouping, not 1.5
        ("1,2,3", "number"),
        ("12.34,5", "number"),  # bad thousands grouping
        ("abc", "character"),
        ("0", "positive"),
        ("-1,5", "positive"),
    ],
)
def test_ambiguous_or_invalid_numbers_raise(value: str, match: str) -> None:
    text = CSV.replace("1.234,56", value, 1)
    with pytest.raises(ParseError, match=match):
        _parse(text)


def test_dot_in_comma_decimal_file_without_thousands_raises() -> None:
    text = (
        CSV.replace("1.234,56", "1.5", 1)
        .replace("1.240,00", "1240,00")
        .replace("1.250,10", "1250,10")
    )
    with pytest.raises(ParseError, match="character"):
        _parse(text, _mapping(thousands_separator=None))


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (CSV.replace("01/12/2026", "2026-12-01"), "date"),
        (CSV.replace("02/12/2026", "01/12/2026"), "monotonic"),
        (CSV.replace("Chiusura ETF A", "Close"), "Chiusura ETF A"),
        (CSV.replace("Data;", "Date;", 1), "Data"),
        ("Data;Chiusura ETF A;NAV ETF B\n", "no rows"),
        ("", "header"),
        (CSV.replace(";x\n", ";x;extra\n"), "fields"),
    ],
)
def test_file_level_strictness(text: str, match: str) -> None:
    with pytest.raises(ParseError, match=match):
        _parse(text)


def test_undecodable_bytes_raise() -> None:
    content = CSV.encode("utf-8") + b"\xff\xfe"
    with pytest.raises(ParseError, match="decode"):
        parse_price_csv(content, _prov(content), _mapping())


def test_declared_frequency_must_match_data() -> None:
    with pytest.raises(ParseError, match="MONTHLY"):
        _parse(CSV, _mapping(frequency=Frequency.MONTHLY))


# --------------------------------------------------------------------------- mapping validation
@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"decimal_separator": ";"}, "decimal_separator"),
        ({"thousands_separator": ","}, "differ"),
        ({"delimiter": ","}, "decimal separator"),
        ({"columns": {}}, "column"),
        ({"date_format": "%d/%m"}, "date_format"),
        (
            {
                "columns": {
                    "Chiusura ETF A": ColumnSpec("SAME", PriceType.PRICE),
                    "NAV ETF B": ColumnSpec("SAME", PriceType.NAV),
                }
            },
            "unique",
        ),
        ({"encoding": "not-an-encoding"}, "encoding"),
        ({"delimiter": ":"}, "delimiter"),
        ({"thousands_separator": "_"}, "thousands_separator"),
    ],
)
def test_mapping_validation(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _mapping(**changes)


def test_column_spec_validation() -> None:
    with pytest.raises(ValidationError, match="instrument"):
        ColumnSpec("bad id", PriceType.PRICE)
    with pytest.raises(ValidationError, match="price_type"):
        ColumnSpec("OK", "price")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- config and import
def test_example_config_loads() -> None:
    mapping = load_csv_mapping(EXAMPLE_CONFIG)
    assert mapping == _mapping()


def test_config_with_unknown_or_missing_keys_raises(tmp_path: Path) -> None:
    text = EXAMPLE_CONFIG.read_text(encoding="utf-8")
    extra = tmp_path / "extra.toml"
    extra.write_text("unexpected = 1\n" + text, encoding="utf-8")
    with pytest.raises(ValidationError, match="unexpected"):
        load_csv_mapping(extra)
    missing = tmp_path / "missing.toml"
    missing.write_text(text.replace('encoding = "utf-8"\n', ""), encoding="utf-8")
    with pytest.raises(ValidationError, match="encoding"):
        load_csv_mapping(missing)
    bad_type = tmp_path / "bad_type.toml"
    bad_type.write_text(
        text.replace('price_type = "nav"', 'price_type = "dirty"'), encoding="utf-8"
    )
    with pytest.raises(ValidationError, match="price_type"):
        load_csv_mapping(bad_type)
    bad_frequency = tmp_path / "bad_frequency.toml"
    bad_frequency.write_text(text.replace('frequency = "daily"', 'frequency = "hourly"'), "utf-8")
    with pytest.raises(ValidationError, match="frequency"):
        load_csv_mapping(bad_frequency)


def test_import_local_file_records_name_only(tmp_path: Path) -> None:
    source = tmp_path / "sub" / "my prices.csv"
    source.parent.mkdir()
    source.write_bytes(CSV.encode())
    store = RawStore(tmp_path / "data")
    stored = import_local_file(
        source, store, dataset="prices", now=lambda: datetime(2026, 12, 4, tzinfo=UTC)
    )
    assert stored.provenance.url == "file:my prices.csv"  # no machine-specific path
    assert stored.provenance.source == "user"
    assert store.read(stored) == CSV.encode()
    assert stored.path.suffix == ".csv"
    result = parse_price_csv(store.read(stored), stored.provenance, _mapping())
    assert result.dataset.data.shape == (3, 2)


def test_import_rejects_empty_file(tmp_path: Path) -> None:
    source = tmp_path / "empty.csv"
    source.write_bytes(b"")
    with pytest.raises(ValidationError, match="empty"):
        import_local_file(
            source,
            RawStore(tmp_path),
            dataset="prices",
            now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_dataframe_index_is_dates_only() -> None:
    assert _parse(CSV).dataset.data.index.equals(
        pd.DatetimeIndex(["2026-12-01", "2026-12-02", "2026-12-03"])
    )


def test_parse_decimal_is_exact() -> None:
    from decimal import Decimal

    from qrlab.data.user_csv import parse_decimal

    value = parse_decimal("1.234,10", decimal_separator=",", thousands_separator=".", line=1)
    assert value == Decimal("1234.10")
    assert str(value) == "1234.10"
    assert parse_decimal("  ", decimal_separator=",", thousands_separator=".", line=1) is None
    assert parse_decimal(
        "-0,1", decimal_separator=",", thousands_separator=None, line=1
    ) == Decimal("-0.1")
    with pytest.raises(ParseError, match="character"):
        parse_decimal("1.5", decimal_separator=",", thousands_separator=None, line=3)
