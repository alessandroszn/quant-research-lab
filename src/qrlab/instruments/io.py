"""Loading instrument master data (TOML) and fund holdings (CSV with an explicit mapping).

Nothing is guessed. Every master-data key must be present, and unknown values are written
explicitly as ``"unknown"``. Holdings files are read through a :class:`HoldingsCsvMapping` that
declares the preamble length, separators, encoding, weight unit, missing-value tokens and the
meaning of each column. Real files belong in the git-ignored ``data/`` folder.
"""

from __future__ import annotations

import codecs
import csv
import io
import tomllib
from collections.abc import Mapping
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
from qrlab.data.user_csv import parse_number
from qrlab.instruments.holdings import HOLDING_COLUMNS, HoldingsSnapshot
from qrlab.instruments.identifiers import Isin
from qrlab.instruments.master import (
    AssetClass,
    Distribution,
    Instrument,
    InstrumentType,
    Replication,
)

__all__ = [
    "HoldingsCsvMapping",
    "WeightUnit",
    "load_holdings_mapping",
    "load_instruments",
    "parse_holdings_csv",
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


# --------------------------------------------------------------------------- holdings
class WeightUnit(Enum):
    """How weights are written in a holdings file."""

    PERCENT = "percent"  # 12.5 means 12.5 %
    DECIMAL = "decimal"  # 0.125 means 12.5 %


@dataclass(frozen=True)
class HoldingsCsvMapping:
    """How to read a holdings file. Every field is required.

    Parameters
    ----------
    skip_rows
        Number of lines before the header (issuer preamble).
    delimiter, decimal_separator, thousands_separator, encoding
        File format, as in :class:`qrlab.data.user_csv.CsvMapping`.
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

    Notes
    -----
    Holdings end at the first blank line; non-empty lines after it (disclaimers) are ignored
    and counted in the snapshot notes.
    """

    skip_rows: int
    delimiter: str
    decimal_separator: str
    thousands_separator: str | None
    encoding: str
    weight_unit: WeightUnit
    missing_tokens: tuple[str, ...]
    columns: Mapping[str, str]
    asset_class: AssetClass | None
    asset_class_values: Mapping[str, AssetClass]

    def __post_init__(self) -> None:
        """Validate the mapping as a whole."""
        if type(self.skip_rows) is not int or self.skip_rows < 0:
            raise ValidationError(f"skip_rows must be a non-negative int, got {self.skip_rows!r}")
        if self.delimiter not in _DELIMITERS:
            raise ValidationError(f"delimiter {self.delimiter!r} not in {sorted(_DELIMITERS)}")
        if self.decimal_separator not in {".", ","}:
            raise ValidationError("decimal_separator must be '.' or ','")
        if self.thousands_separator == self.decimal_separator:
            raise ValidationError("decimal and thousands separators must differ")
        # A thousands separator equal to the delimiter is fine when numbers are quoted
        # ("1,234.50"); an unquoted one changes the field count and is rejected per row.
        if self.delimiter == self.decimal_separator:
            raise ValidationError("delimiter must differ from the decimal separator")
        try:
            codecs.lookup(self.encoding)
        except LookupError:
            raise ValidationError(f"unknown encoding {self.encoding!r}") from None
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
    """Read a holdings file into a validated :class:`HoldingsSnapshot`.

    Weights in percent are divided by 100. A holding without a weight raises. Weights are not
    rescaled; see :func:`~qrlab.instruments.holdings.holdings_issues`.
    """
    try:
        text = content.decode(mapping.encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(f"cannot decode the file with encoding {mapping.encoding!r}") from exc
    lines = text.splitlines()
    if len(lines) <= mapping.skip_rows:
        raise ParseError(f"file has no header after skipping {mapping.skip_rows} line(s)")
    body = list(
        csv.reader(io.StringIO("\n".join(lines[mapping.skip_rows :])), delimiter=mapping.delimiter)
    )
    header = [cell.strip() for cell in body[0]]
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
            trailing += any(cell.strip() for cell in row)
            continue
        if not any(cell.strip() for cell in row):
            ended = True
            continue
        if len(row) != len(header):
            raise ParseError(f"line {offset}: expected {len(header)} fields, got {len(row)}")
        records.append(_holding(row, positions, mapping, offset))
    if not records:
        raise ParseError("file contains no holdings")

    notes = [f"Skipped {mapping.skip_rows} preamble line(s) before the header."]
    if mapping.weight_unit is WeightUnit.PERCENT:
        notes.append("Weights converted from percent to decimal (divided by 100).")
    if trailing:
        notes.append(f"Ignored {trailing} line(s) after the first blank line.")
    ignored = [h for h in header if h not in mapping.columns.values()]
    if ignored:
        notes.append(f"Ignored columns: {ignored}.")
    notes.append(f"Cells equal to {list(mapping.missing_tokens)} treated as unknown.")
    return HoldingsSnapshot(
        fund=fund,
        as_of=as_of,
        holdings=pd.DataFrame(records, columns=list(HOLDING_COLUMNS)),
        provenance=provenance,
        weight_basis=weight_basis,
        sector_taxonomy=sector_taxonomy,
        notes=tuple(notes),
    )


def _holding(
    row: list[str], positions: Mapping[str, int], mapping: HoldingsCsvMapping, line: int
) -> dict[str, object]:
    def cell(field: str) -> str | None:
        if field not in positions:
            return None
        value = row[positions[field]].strip()
        return None if value in mapping.missing_tokens else value

    weight_text = cell("weight")
    if weight_text is None:
        raise ParseError(f"line {line}: weight is missing")
    weight = parse_number(
        weight_text,
        decimal_separator=mapping.decimal_separator,
        thousands_separator=mapping.thousands_separator,
        line=line,
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
        "country": cell("country"),
        "sector": cell("sector"),
        "currency": cell("currency"),
        "asset_class": asset_class,
    }


def load_holdings_mapping(path: Path) -> HoldingsCsvMapping:
    """Load a :class:`HoldingsCsvMapping` from TOML (see ``configs/csv_mappings/``)."""
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    expected = {
        "skip_rows", "delimiter", "decimal_separator", "thousands_separator", "encoding",
        "weight_unit", "missing_tokens", "asset_class", "columns",
    }  # fmt: skip
    optional = {"asset_class_values"}
    _check_keys({k: v for k, v in raw.items() if k not in optional}, expected, Path(path).name)
    fixed = raw["asset_class"]
    values = {
        text: _enum(AssetClass, value, f"asset_class_values[{text!r}]", Path(path).name)
        for text, value in raw.get("asset_class_values", {}).items()
    }
    return HoldingsCsvMapping(
        skip_rows=raw["skip_rows"],
        delimiter=raw["delimiter"],
        decimal_separator=raw["decimal_separator"],
        thousands_separator=raw["thousands_separator"] or None,
        encoding=raw["encoding"],
        weight_unit=_enum(WeightUnit, raw["weight_unit"], "weight_unit", Path(path).name),
        missing_tokens=tuple(raw["missing_tokens"]),
        columns=dict(raw["columns"]),
        asset_class=None
        if fixed == "column"
        else _enum(AssetClass, fixed, "asset_class", Path(path).name),
        asset_class_values=values,
    )


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
