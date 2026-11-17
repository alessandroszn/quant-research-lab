"""Loading instrument master data (TOML) and fund holdings (CSV or xlsx, with an explicit mapping).

Nothing is guessed. Every master-data key must be present, and unknown values are written
explicitly as ``"unknown"``. Holdings files are read through a :class:`HoldingsCsvMapping` that
declares the preamble length, separators, encoding, weight unit, missing-value tokens and the
meaning of each column. Real files belong in the git-ignored ``data/`` folder.
"""

from __future__ import annotations

import codecs
import csv
import io
import json
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.data.sheets import check_affixes, read_spreadsheetml_rows, read_xlsx_rows
from qrlab.data.user_csv import parse_number
from qrlab.instruments.countries import country_code, country_code_it
from qrlab.instruments.holdings import HOLDING_COLUMNS, HoldingsSnapshot
from qrlab.instruments.identifiers import COUNTRIES, Isin, validate_country
from qrlab.instruments.master import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Replication,
)

__all__ = [
    "INSTRUMENT_FIELDS",
    "CountryFormat",
    "HoldingsCsvMapping",
    "HoldingsFileFormat",
    "WeightUnit",
    "instrument_fields",
    "instrument_from_fields",
    "load_holdings_mapping",
    "load_instruments",
    "load_issuer_map",
    "parse_holdings_csv",
    "parse_holdings_file",
    "write_instruments_toml",
]

_E = TypeVar("_E", bound=Enum)
_UNKNOWN = "unknown"
_INSTRUMENT_KEYS = frozenset(
    {
        "name", "instrument_type", "asset_class", "currency", "as_of", "domicile",
        "replication", "distribution", "ter", "benchmark", "hedged_to", "inception", "fund_size",
        "source",
    }
)  # fmt: skip
_DELIMITERS = frozenset({",", ";", "\t", "|"})
INSTRUMENT_FIELDS = (
    "isin", "name", "instrument_type", "asset_class", "currency", "as_of", "domicile",
    "replication", "distribution", "ter", "benchmark", "hedged_to", "inception", "fund_size",
    "source",
)  # fmt: skip
"""An instrument as text fields (phase 8.8): the ISIN, then the TOML keys in file order."""


# --------------------------------------------------------------------------- master data
def load_instruments(path: Path) -> list[Instrument]:
    """Load instrument master data from a TOML file with one table per ISIN.

    See ``configs/instruments/example.toml``. ``"unknown"`` becomes ``None`` for domicile,
    replication, distribution, TER, benchmark, inception and fund size; ``hedged_to`` is a
    currency or ``"none"``. The TER must be a quoted decimal fraction (``"0.0020"``).
    """
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    if not raw:
        raise ValidationError(f"{Path(path).name}: no instruments defined")
    return [_instrument(code, table) for code, table in raw.items()]


def _instrument(code: str, table: Mapping[str, Any]) -> Instrument:
    _check_keys(table, set(_INSTRUMENT_KEYS), code)
    hedged = table["hedged_to"]
    if hedged == _UNKNOWN:
        raise ValidationError(f"{code}: hedged_to must be a currency or 'none', not 'unknown'")
    return Instrument(
        isin=Isin(code),
        name=table["name"],
        instrument_type=_enum(InstrumentType, table["instrument_type"], "instrument_type", code),
        asset_class=_enum(AssetClass, table["asset_class"], "asset_class", code),
        currency=Currency(table["currency"]),
        as_of=_toml_date(table["as_of"], "as_of", code, allow_unknown=False),  # type: ignore[arg-type]
        domicile=_optional(table["domicile"]),
        replication=_optional_enum(Replication, table["replication"], "replication", code),
        distribution=_optional_enum(Distribution, table["distribution"], "distribution", code),
        ter=_ter(table["ter"], code),
        benchmark=_optional(table["benchmark"]),
        hedged_to=None if hedged == "none" else Currency(hedged),
        inception=_toml_date(table["inception"], "inception", code, allow_unknown=True),
        fund_size=_fund_size(table["fund_size"], code),
        source=table["source"],
    )


def instrument_from_fields(fields: Mapping[str, str]) -> Instrument:
    """Read an instrument from text fields, with the rules of :func:`load_instruments`.

    The fields are :data:`INSTRUMENT_FIELDS`, all text, as a person types them: dates as
    ``2026-01-02`` (``inception`` may be ``"unknown"``), ``ter`` as a decimal fraction
    (``0.0020``), and ``fund_size`` as ``"unknown"`` or an amount and a currency
    (``1500000000 EUR``). ``"unknown"`` and ``"none"`` mean what they mean in the TOML file.
    """
    code = fields.get("isin", "")
    _check_keys(fields, set(INSTRUMENT_FIELDS), code or "instrument")
    table: dict[str, object] = {k: v for k, v in fields.items() if k != "isin"}
    for name in ("as_of", "inception"):
        text = fields[name]
        if name == "inception" and text == _UNKNOWN:
            continue
        try:
            table[name] = date.fromisoformat(text)
        except ValueError:
            raise ValidationError(f"{code}: {name} must be a date such as 2026-10-01") from None
    size = fields["fund_size"]
    if size != _UNKNOWN:
        parts = size.split()
        if len(parts) != 2:
            raise ValidationError(
                f'{code}: fund_size must be "unknown" or an amount and a currency, "1500000000 EUR"'
            )
        table["fund_size"] = {"amount": parts[0], "currency": parts[1]}
    return _instrument(code, table)


def instrument_fields(instrument: Instrument) -> dict[str, str]:
    """Return an instrument as text fields, the inverse of :func:`instrument_from_fields`."""
    size = instrument.fund_size
    return {
        "isin": instrument.isin.code,
        "name": instrument.name,
        "instrument_type": instrument.instrument_type.value,
        "asset_class": instrument.asset_class.value,
        "currency": instrument.currency.code,
        "as_of": instrument.as_of.isoformat(),
        "domicile": _known(instrument.domicile),
        "replication": _UNKNOWN if instrument.replication is None else instrument.replication.value,
        "distribution": (
            _UNKNOWN if instrument.distribution is None else instrument.distribution.value
        ),
        "ter": _UNKNOWN if instrument.ter is None else format(instrument.ter, "f"),
        "benchmark": _known(instrument.benchmark),
        "hedged_to": "none" if instrument.hedged_to is None else instrument.hedged_to.code,
        "inception": _UNKNOWN if instrument.inception is None else instrument.inception.isoformat(),
        "fund_size": _UNKNOWN
        if size is None
        else f"{format(size.amount, 'f')} {size.currency.code}",
        "source": instrument.source,
    }


def write_instruments_toml(instruments: Sequence[Instrument]) -> str:
    """Write instruments as the TOML file :func:`load_instruments` reads, in the given order."""
    blocks = []
    for instrument in instruments:
        fields = instrument_fields(instrument)
        lines = [f"[{fields.pop('isin')}]"]
        for name, text in fields.items():
            if name == "as_of" or (name == "inception" and text != _UNKNOWN):
                value = text
            elif name == "fund_size" and text != _UNKNOWN:
                amount, currency = text.split()
                value = f"{{ amount = {_quoted(amount)}, currency = {_quoted(currency)} }}"
            else:
                value = _quoted(text)
            lines.append(f"{name} = {value}")
        blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)


def _known(value: str | None) -> str:
    return _UNKNOWN if value is None else value


def _quoted(text: str) -> str:
    """Return a TOML basic string (JSON's escapes are valid TOML escapes)."""
    return json.dumps(text, ensure_ascii=False)


# --------------------------------------------------------------------------- holdings
class WeightUnit(Enum):
    """How weights are written in a holdings file."""

    PERCENT = "percent"  # 12.5 means 12.5 %
    DECIMAL = "decimal"  # 0.125 means 12.5 %


class HoldingsFileFormat(Enum):
    """The kind of file an issuer publishes."""

    CSV = "csv"
    XLSX = "xlsx"  # an Excel workbook, read with openpyxl
    SPREADSHEETML = "spreadsheetml"  # an XML Spreadsheet 2003 (phase 8.2c)


class CountryFormat(Enum):
    """How the country column is written."""

    ISO_ALPHA2 = "iso_alpha2"  # "US"
    NAME = "name"  # "United States", converted with qrlab.instruments.countries
    NAME_IT = "name_it"  # "Stati Uniti", converted with CLDR's Italian names (11.5)


@dataclass(frozen=True)
class HoldingsCsvMapping:
    """How to read a holdings file (CSV or Excel). Every field is required.

    Parameters
    ----------
    skip_rows
        Number of lines (rows of the sheet) before the header (issuer preamble).
    delimiter, encoding
        CSV only, as in :class:`qrlab.data.user_csv.CsvMapping`; ``None`` for an xlsx file.
    decimal_separator, thousands_separator
        How numbers written as text are read (in an xlsx file, numeric cells are read as they
        are).
    weight_unit
        Percent or decimal weights.
    missing_tokens
        Cell values that mean "unknown" (e.g. ``""`` and ``"-"``).
    columns
        Canonical field (from :data:`~qrlab.instruments.holdings.HOLDING_COLUMNS`) to file header.
        ``name`` and ``weight`` are required; unmapped optional fields are unknown.
    asset_class
        Fixed asset class for every holding, used only when ``asset_class`` is not a mapped
        column. Exactly one of the two must be given.
    asset_class_values
        File wording to asset class (e.g. ``{"Equity": AssetClass.EQUITY}``); required when the
        ``asset_class`` column is mapped, empty otherwise.
    file_format
        CSV or xlsx.
    sheet
        Name of the sheet to read in an xlsx file; ``None`` for a CSV file.
    country_format
        Whether the country column holds ISO 3166-1 alpha-2 codes or country names.
    country_values
        The file's own wording mapped to a code, or to ``None`` for "no country" (e.g. a
        supranational issuer or a cash line). Checked before the codes or the built-in names.
    value_affixes
        Symbols written next to weights and removed before reading them, e.g. ``("%",)``
        (phase 8.2b); any other character still raises.

    Notes
    -----
    Holdings end at the first blank line; non-empty lines after it (disclaimers) are ignored
    and counted in the snapshot notes.
    """

    skip_rows: int
    delimiter: str | None
    decimal_separator: str
    thousands_separator: str | None
    encoding: str | None
    weight_unit: WeightUnit
    missing_tokens: tuple[str, ...]
    columns: Mapping[str, str]
    asset_class: AssetClass | None
    asset_class_values: Mapping[str, AssetClass]
    file_format: HoldingsFileFormat
    sheet: str | None
    country_format: CountryFormat
    country_values: Mapping[str, str | None]
    value_affixes: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the mapping as a whole."""
        check_affixes(self.value_affixes)
        if not isinstance(self.file_format, HoldingsFileFormat):
            raise ValidationError(
                f"file_format must be a HoldingsFileFormat, got {self.file_format!r}"
            )
        if type(self.skip_rows) is not int or self.skip_rows < 0:
            raise ValidationError(f"skip_rows must be a non-negative int, got {self.skip_rows!r}")
        if self.decimal_separator not in {".", ","}:
            raise ValidationError("decimal_separator must be '.' or ','")
        if self.thousands_separator == self.decimal_separator:
            raise ValidationError("decimal and thousands separators must differ")
        if self.file_format is HoldingsFileFormat.CSV:
            self._check_csv()
        else:
            if not isinstance(self.sheet, str) or not self.sheet.strip():
                raise ValidationError("an xlsx or spreadsheetml mapping needs a sheet name")
            if self.delimiter is not None or self.encoding is not None:
                raise ValidationError("delimiter and encoding are only for csv files")
        if not isinstance(self.weight_unit, WeightUnit):
            raise ValidationError(f"weight_unit must be a WeightUnit, got {self.weight_unit!r}")
        unknown = sorted(set(self.columns) - set(HOLDING_COLUMNS))
        if unknown:
            raise ValidationError(f"unknown canonical fields {unknown}")
        for required in ("name", "weight"):
            if required not in self.columns:
                raise ValidationError(f"column mapping must include {required!r}")
        has_column = "asset_class" in self.columns
        if has_column == (self.asset_class is not None):
            raise ValidationError(
                "give exactly one of an asset_class column or a fixed asset_class"
            )
        if has_column != bool(self.asset_class_values):
            raise ValidationError(
                "asset_class_values is required with an asset_class column, and only then"
            )
        if not isinstance(self.country_format, CountryFormat):
            raise ValidationError(
                f"country_format must be a CountryFormat, got {self.country_format!r}"
            )
        for text, code in self.country_values.items():
            if not str(text).strip():
                raise ValidationError("country_values keys must be non-empty text")
            if code is not None and code not in COUNTRIES:
                raise ValidationError(
                    f"country_values[{text!r}]: {code!r} is not an ISO 3166-1 alpha-2 code "
                    "(or 'unknown')"
                )

    def _check_csv(self) -> None:
        if self.sheet is not None:
            raise ValidationError("sheet is only for xlsx files")
        if self.delimiter not in _DELIMITERS:
            raise ValidationError(f"delimiter {self.delimiter!r} not in {sorted(_DELIMITERS)}")
        # A thousands or decimal separator equal to the delimiter is fine when numbers are
        # quoted ("1,234.50", or iShares' Italian "5,82" with a comma delimiter, phase 8.2c);
        # an unquoted one changes the field count and is rejected per row.
        if not isinstance(self.encoding, str):
            raise ValidationError(f"unknown encoding {self.encoding!r}")
        try:
            codecs.lookup(self.encoding)
        except LookupError:
            raise ValidationError(f"unknown encoding {self.encoding!r}") from None


def parse_holdings_file(
    content: bytes,
    provenance: Provenance,
    mapping: HoldingsCsvMapping,
    *,
    fund: Isin,
    as_of: date,
    weight_basis: str,
    sector_taxonomy: str | None,
) -> HoldingsSnapshot:
    """Read a holdings file, CSV or xlsx as its mapping declares, into a snapshot.

    Weights in percent are divided by 100. A holding without a weight raises. Weights are not
    rescaled; see :func:`~qrlab.instruments.holdings.holdings_issues`. Country names are
    converted with :func:`qrlab.instruments.countries.country_code` when the mapping declares
    names; an unknown name raises with its line.
    """
    if mapping.file_format is HoldingsFileFormat.XLSX:
        body = _xlsx_rows(content, mapping)
        source = f"Read sheet {mapping.sheet!r} of an xlsx workbook."
    elif mapping.file_format is HoldingsFileFormat.SPREADSHEETML:
        body = read_spreadsheetml_rows(
            content, sheet=str(mapping.sheet), skip_rows=mapping.skip_rows
        )
        source = f"Read sheet {mapping.sheet!r} of an XML spreadsheet (SpreadsheetML)."
    else:
        body = _csv_rows(content, mapping)
        source = None
    header = [_text(cell).strip() for cell in body[0]]
    positions: dict[str, int] = {}
    for field, column in mapping.columns.items():
        if column not in header:
            raise ParseError(f"column {column!r} (for {field}) not found in header {header}")
        positions[field] = header.index(column)

    records: list[dict[str, object]] = []
    trailing = 0
    ended = False
    for offset, row in enumerate(body[1:], start=mapping.skip_rows + 2):
        if ended:
            trailing += any(_text(cell).strip() for cell in row)
            continue
        if not any(_text(cell).strip() for cell in row):
            ended = True
            continue
        if len(row) != len(header):
            raise ParseError(f"line {offset}: expected {len(header)} fields, got {len(row)}")
        records.append(_holding(row, positions, mapping, offset))
    if not records:
        raise ParseError("file contains no holdings")

    notes = [] if source is None else [source]
    notes.append(f"Skipped {mapping.skip_rows} preamble line(s) before the header.")
    if mapping.weight_unit is WeightUnit.PERCENT:
        notes.append("Weights converted from percent to decimal (divided by 100).")
    if mapping.country_format is CountryFormat.NAME and "country" in mapping.columns:
        notes.append("Country names converted to ISO 3166-1 alpha-2 codes.")
    if mapping.country_format is CountryFormat.NAME_IT and "country" in mapping.columns:
        notes.append(
            "Italian country names converted to ISO 3166-1 alpha-2 codes (Unicode CLDR 49.0.0)."
        )
    if trailing:
        notes.append(f"Ignored {trailing} line(s) after the first blank line.")
    ignored = [h for h in header if h not in mapping.columns.values()]
    if ignored:
        notes.append(f"Ignored columns: {ignored}.")
    notes.append(f"Cells equal to {list(mapping.missing_tokens)} treated as unknown.")
    if mapping.value_affixes:
        notes.append(f"Symbols removed from numbers: {list(mapping.value_affixes)}.")
    return HoldingsSnapshot(
        fund=fund,
        as_of=as_of,
        holdings=pd.DataFrame(records, columns=list(HOLDING_COLUMNS)),
        provenance=provenance,
        weight_basis=weight_basis,
        sector_taxonomy=sector_taxonomy,
        notes=tuple(notes),
    )


def parse_holdings_csv(
    content: bytes,
    provenance: Provenance,
    mapping: HoldingsCsvMapping,
    *,
    fund: Isin,
    as_of: date,
    weight_basis: str,
    sector_taxonomy: str | None,
) -> HoldingsSnapshot:
    """Read a CSV holdings file; see :func:`parse_holdings_file`, which also reads xlsx."""
    if mapping.file_format is not HoldingsFileFormat.CSV:
        raise ValidationError(
            "this mapping reads an xlsx or XML spreadsheet: use parse_holdings_file"
        )
    return parse_holdings_file(
        content,
        provenance,
        mapping,
        fund=fund,
        as_of=as_of,
        weight_basis=weight_basis,
        sector_taxonomy=sector_taxonomy,
    )


def _csv_rows(content: bytes, mapping: HoldingsCsvMapping) -> list[list[object]]:
    """Return the header and the rows after the preamble of a CSV file."""
    assert mapping.encoding is not None  # checked by the mapping
    assert mapping.delimiter is not None
    try:
        text = content.decode(mapping.encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(f"cannot decode the file with encoding {mapping.encoding!r}") from exc
    lines = text.splitlines()
    if len(lines) <= mapping.skip_rows:
        raise ParseError(f"file has no header after skipping {mapping.skip_rows} line(s)")
    reader = csv.reader(
        io.StringIO("\n".join(lines[mapping.skip_rows :])), delimiter=mapping.delimiter
    )
    return [list(row) for row in reader]


def _xlsx_rows(content: bytes, mapping: HoldingsCsvMapping) -> list[list[object]]:
    """Return the header and the rows after the preamble (:func:`qrlab.data.read_xlsx_rows`)."""
    return read_xlsx_rows(content, sheet=str(mapping.sheet), skip_rows=mapping.skip_rows)


def _text(value: object) -> str:
    """Return a cell as text (``None`` is empty)."""
    return "" if value is None else str(value)


def _holding(
    row: list[object], positions: Mapping[str, int], mapping: HoldingsCsvMapping, line: int
) -> dict[str, object]:
    def cell(field: str) -> str | None:
        if field not in positions:
            return None
        value = _text(row[positions[field]]).strip()
        return None if value in mapping.missing_tokens else value

    raw_weight = row[positions["weight"]]
    if isinstance(raw_weight, int | float) and not isinstance(raw_weight, bool):
        weight = float(raw_weight)  # a numeric cell of an xlsx sheet
    else:
        weight_text = cell("weight")
        if weight_text is None:
            raise ParseError(f"line {line}: weight is missing")
        weight = parse_number(
            weight_text,
            decimal_separator=mapping.decimal_separator,
            thousands_separator=mapping.thousands_separator,
            line=line,
            affixes=mapping.value_affixes,
        )
    if mapping.weight_unit is WeightUnit.PERCENT:
        weight /= 100.0
    if mapping.asset_class is not None:
        asset_class = mapping.asset_class.value
    else:
        raw = cell("asset_class")
        if raw is None or raw not in mapping.asset_class_values:
            raise ParseError(f"line {line}: unknown asset class value {raw!r}")
        asset_class = mapping.asset_class_values[raw].value
    return {
        "name": cell("name"),
        "isin": cell("isin"),
        "weight": weight,
        "country": _country(cell("country"), mapping, line),
        "sector": cell("sector"),
        "currency": cell("currency"),
        "asset_class": asset_class,
    }


def _country(value: str | None, mapping: HoldingsCsvMapping, line: int) -> str | None:
    """Return the ISO code of a country cell: the mapping's own wording first."""
    if value is None:
        return None
    if value in mapping.country_values:
        return mapping.country_values[value]
    try:
        if mapping.country_format is CountryFormat.NAME:
            return country_code(value)
        if mapping.country_format is CountryFormat.NAME_IT:
            return country_code_it(value)
        return validate_country(value)
    except ValidationError as exc:
        raise ParseError(f"line {line}: {exc}") from exc


def load_holdings_mapping(path: Path) -> HoldingsCsvMapping:
    """Load a :class:`HoldingsCsvMapping` from TOML (see ``configs/csv_mappings/``)."""
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    where = Path(path).name
    if "file_format" not in raw:
        raise ValidationError(f"{where}: missing keys ['file_format']")
    file_format = _enum(HoldingsFileFormat, raw["file_format"], "file_format", where)
    expected = {
        "file_format", "skip_rows", "decimal_separator", "thousands_separator", "weight_unit",
        "missing_tokens", "asset_class", "columns", "country_format", "value_affixes",
    }  # fmt: skip
    expected |= {"delimiter", "encoding"} if file_format is HoldingsFileFormat.CSV else {"sheet"}
    optional = {"asset_class_values", "country_values"}
    _check_keys({k: v for k, v in raw.items() if k not in optional}, expected, where)
    fixed = raw["asset_class"]
    values = {
        text: _enum(AssetClass, value, f"asset_class_values[{text!r}]", where)
        for text, value in raw.get("asset_class_values", {}).items()
    }
    countries = {
        str(text): None if value == _UNKNOWN else str(value)
        for text, value in raw.get("country_values", {}).items()
    }
    return HoldingsCsvMapping(
        skip_rows=raw["skip_rows"],
        delimiter=raw.get("delimiter"),
        decimal_separator=raw["decimal_separator"],
        thousands_separator=raw["thousands_separator"] or None,
        encoding=raw.get("encoding"),
        weight_unit=_enum(WeightUnit, raw["weight_unit"], "weight_unit", where),
        missing_tokens=tuple(raw["missing_tokens"]),
        columns=dict(raw["columns"]),
        asset_class=None if fixed == "column" else _enum(AssetClass, fixed, "asset_class", where),
        asset_class_values=values,
        file_format=file_format,
        sheet=raw.get("sheet"),
        country_format=_enum(CountryFormat, raw["country_format"], "country_format", where),
        country_values=countries,
        value_affixes=check_affixes(raw["value_affixes"]),
    )


def load_issuer_map(path: Path) -> dict[Isin, str]:
    """Load a map from security ISIN to issuer name.

    The file is UTF-8 CSV (a byte-order mark is accepted) with exactly the header
    ``isin,issuer``. Invalid ISINs, an ISIN listed twice and empty issuers raise; blank lines
    are skipped. With it, look-through groups the securities of one issuer (e.g. two share
    classes of one company) in the issuer exposure and its health check.
    """
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    where = Path(path).name
    if not rows or [cell.strip() for cell in rows[0]] != ["isin", "issuer"]:
        raise ValidationError(f"{where}: the header must be exactly 'isin,issuer'")
    issuers: dict[Isin, str] = {}
    for line, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != 2:
            raise ValidationError(f"{where} line {line}: expected 2 fields, got {len(row)}")
        isin, issuer = Isin(row[0].strip()), row[1].strip()
        if not issuer:
            raise ValidationError(f"{where} line {line}: empty issuer")
        if isin in issuers:
            raise ValidationError(f"{where} line {line}: {isin.code} is listed twice")
        issuers[isin] = issuer
    if not issuers:
        raise ValidationError(f"{where}: no rows after the header")
    return issuers


# --------------------------------------------------------------------------- helpers
def _check_keys(table: Mapping[str, object], expected: set[str], where: str) -> None:
    missing = sorted(expected - set(table))
    unexpected = sorted(set(table) - expected)
    if missing:
        raise ValidationError(f"{where}: missing keys {missing}")
    if unexpected:
        raise ValidationError(f"{where}: unexpected keys {unexpected}")


def _enum(kind: type[_E], value: object, field: str, where: str) -> _E:
    try:
        return kind(value)
    except ValueError:
        allowed = [member.value for member in kind]
        raise ValidationError(f"{where}: {field} {value!r} is not one of {allowed}") from None


def _optional_enum(kind: type[_E], value: object, field: str, where: str) -> _E | None:
    return None if value == _UNKNOWN else _enum(kind, value, field, where)


def _optional(value: str) -> str | None:
    return None if value == _UNKNOWN else value


def _ter(value: object, where: str) -> Decimal | None:
    if value == _UNKNOWN:
        return None
    if not isinstance(value, str):
        raise ValidationError(f'{where}: ter must be a quoted decimal string such as "0.0020"')
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValidationError(f"{where}: ter {value!r} is not a decimal number") from None


def _fund_size(value: object, where: str) -> Money | None:
    if value == _UNKNOWN:
        return None
    if not isinstance(value, Mapping) or set(value) != {"amount", "currency"}:
        raise ValidationError(
            f'{where}: fund_size must be "unknown" or {{ amount = "...", currency = "EUR" }}'
        )
    if not isinstance(value["amount"], str):
        raise ValidationError(f"{where}: fund_size amount must be a quoted decimal string")
    return Money.of(value["amount"], value["currency"])


def _toml_date(value: object, field: str, where: str, *, allow_unknown: bool) -> date | None:
    if allow_unknown and value == _UNKNOWN:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValidationError(f"{where}: {field} must be a TOML date such as 2026-10-01")
    return value
