"""User-supplied price files, read through an explicit mapping.

Nothing about the file is guessed: date format, delimiter, decimal and thousands separators,
encoding, currency, frequency and the meaning of each price column (total return, price or NAV)
come from a :class:`CsvMapping`, normally a TOML file in ``configs/``. The price files themselves
belong in the git-ignored ``data/`` folder.

Ambiguity raises :class:`~qrlab.data.errors.ParseError`. For example ``1.5`` in a file whose
decimal separator is ``,`` is rejected rather than read as 1.5 or 15.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import re
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

import numpy as np
import pandas as pd

from qrlab.core.calendar import Frequency, infer_frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.sheets import (
    FileFormat,
    check_affixes,
    read_spreadsheetml_rows,
    read_xlsx_rows,
    strip_affixes,
)
from qrlab.data.store import RawStore, StoredFile

__all__ = [
    "ColumnSpec",
    "CsvMapping",
    "PriceData",
    "PriceType",
    "import_local_file",
    "load_csv_mapping",
    "parse_decimal",
    "parse_number",
    "parse_price_csv",
]

_INSTRUMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_DELIMITERS = frozenset({",", ";", "\t", "|"})
_DECIMALS = frozenset({".", ","})
_THOUSANDS = frozenset({".", ",", " ", "'"})
_MONTHS = {
    name: f"{number:02d}"
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
        start=1,
    )
}
_WORD = re.compile(r"[A-Za-z]+")


class PriceType(Enum):
    """What a price column measures; required because dividends change returns."""

    TOTAL_RETURN = "total_return"  # dividends reinvested
    PRICE = "price"  # dividends excluded
    NAV = "nav"  # fund net asset value per share


_PRICE_TYPE_TEXT = {
    PriceType.TOTAL_RETURN: "total return (dividends reinvested)",
    PriceType.PRICE: "price (dividends excluded)",
    PriceType.NAV: "net asset value per share",
}


@dataclass(frozen=True)
class ColumnSpec:
    """Meaning of one price column: the instrument identifier and the price type."""

    instrument: str
    price_type: PriceType

    def __post_init__(self) -> None:
        """Validate the identifier and type."""
        if not _is_instrument_id(self.instrument):
            raise ValidationError(f"instrument id {self.instrument!r} is not a valid identifier")
        if not isinstance(self.price_type, PriceType):
            raise ValidationError(f"price_type must be a PriceType, got {self.price_type!r}")


@dataclass(frozen=True)
class CsvMapping:
    """How to read a user price file. Every field is required.

    Parameters
    ----------
    date_column
        Header of the date column.
    date_format
        :func:`datetime.strptime` format, e.g. ``"%d/%m/%Y"``; must contain day, month, year.
        ``%b`` is an English month abbreviation (Jan-Dec), read the same on every machine.
    delimiter
        Field separator: ``,``, ``;``, tab or ``|``; ``None`` for an xlsx file.
    decimal_separator
        ``.`` or ``,``.
    thousands_separator
        ``.``, ``,``, space, apostrophe or ``None``; must differ from the decimal separator.
    encoding
        Text encoding, e.g. ``"utf-8"``, ``"utf-8-sig"`` or ``"cp1252"``; ``None`` for xlsx.
    currency
        Currency of every mapped column (use one file and mapping per currency).
    frequency
        Declared sampling frequency; checked against the dates.
    columns
        Header of each price column mapped to its :class:`ColumnSpec`. Unmapped columns are
        ignored and listed in the dataset notes.
    file_format
        CSV or xlsx (phase 8.2b), or an XML spreadsheet (SpreadsheetML, phase 8.2c).
    sheet
        Name of the sheet to read in an xlsx file; ``None`` for a CSV file.
    skip_rows
        Lines (rows of the sheet) before the header, such as an issuer's preamble.
    value_affixes
        Symbols written next to numbers and removed before reading them, e.g. ``("$",)``; any
        other character still raises.
    missing_tokens
        Cell values that mean "no price", besides an empty cell (always missing), e.g.
        ``("--",)`` (phase 8.2c). They become NaN, never filled.
    """

    date_column: str
    date_format: str
    delimiter: str | None
    decimal_separator: str
    thousands_separator: str | None
    encoding: str | None
    currency: Currency
    frequency: Frequency
    columns: Mapping[str, ColumnSpec]
    file_format: FileFormat
    sheet: str | None
    skip_rows: int
    value_affixes: tuple[str, ...]
    missing_tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the mapping as a whole."""
        if not isinstance(self.file_format, FileFormat):
            raise ValidationError(f"file_format must be a FileFormat, got {self.file_format!r}")
        if type(self.skip_rows) is not int or self.skip_rows < 0:
            raise ValidationError(f"skip_rows must be a non-negative int, got {self.skip_rows!r}")
        check_affixes(self.value_affixes)
        tokens: object = self.missing_tokens
        if not isinstance(tokens, tuple) or not all(isinstance(t, str) for t in tokens):
            raise ValidationError(f"missing_tokens must be a list of text, got {tokens!r}")
        if self.decimal_separator not in _DECIMALS:
            raise ValidationError(
                f"decimal_separator must be '.' or ',', got {self.decimal_separator!r}"
            )
        if self.file_format is not FileFormat.CSV:
            if not isinstance(self.sheet, str) or self.delimiter is not None or self.encoding:
                raise ValidationError(
                    "an xlsx or spreadsheetml mapping needs a sheet and no delimiter or encoding"
                )
        else:
            if self.sheet is not None:
                raise ValidationError("a CSV mapping has no sheet")
            self._check_csv()
        if self.thousands_separator is not None:
            if self.thousands_separator not in _THOUSANDS:
                raise ValidationError(
                    f"thousands_separator {self.thousands_separator!r} is not supported"
                )
            if self.thousands_separator == self.decimal_separator:
                raise ValidationError("decimal and thousands separators must differ")
        if (
            "%d" not in self.date_format
            or not ("%m" in self.date_format or "%b" in self.date_format)
            or not ("%Y" in self.date_format or "%y" in self.date_format)
        ):
            raise ValidationError(
                f"date_format {self.date_format!r} needs %d, %m or %b, and %Y or %y"
            )
        if not self.columns:
            raise ValidationError("at least one price column must be mapped")
        instruments = [spec.instrument for spec in self.columns.values()]
        if len(set(instruments)) != len(instruments):
            raise ValidationError("instrument identifiers must be unique")

    def _check_csv(self) -> None:
        if self.delimiter not in _DELIMITERS:
            raise ValidationError(f"delimiter {self.delimiter!r} not in {sorted(_DELIMITERS)}")
        # A thousands separator equal to the delimiter is fine when numbers are quoted
        # ("1,234.50"); an unquoted one changes the field count and is rejected per row.
        if self.delimiter == self.decimal_separator:
            raise ValidationError("delimiter must differ from the decimal separator")
        try:
            codecs.lookup(str(self.encoding))
        except LookupError:
            raise ValidationError(f"unknown encoding {self.encoding!r}") from None


@dataclass(frozen=True)
class PriceData:
    """Parsed prices and the price type of each instrument column."""

    dataset: Dataset
    price_types: Mapping[str, PriceType]


def parse_price_csv(content: bytes, provenance: Provenance, mapping: CsvMapping) -> PriceData:
    """Parse a user price file, CSV or xlsx as its mapping declares, one column per instrument.

    The ``skip_rows`` lines before the header are ignored. Empty cells are missing values (NaN)
    and are not filled. Dates must be strictly increasing or strictly decreasing; a decreasing
    file is reversed and the reversal is noted.
    """
    numbered = _price_rows(content, mapping)
    header = [_cell(value).strip() for value in numbered[0][1]]
    for required in (mapping.date_column, *mapping.columns):
        if required not in header:
            raise ParseError(f"column {required!r} not found in header {header}")
    date_position = header.index(mapping.date_column)
    positions = {name: header.index(name) for name in mapping.columns}

    dates: list[pd.Timestamp] = []
    values: list[list[float]] = []
    for line, row in numbered[1:]:
        if len(row) != len(header):
            raise ParseError(f"line {line}: expected {len(header)} fields, got {len(row)}")
        dates.append(_row_date(row[date_position], mapping.date_format, line))
        values.append(
            [_parse_price(row[positions[name]], mapping, line) for name in mapping.columns]
        )
    if not values:
        raise ParseError("file has no rows")

    notes: list[str] = []
    index = pd.DatetimeIndex(dates)
    frame = pd.DataFrame(
        np.array(values, dtype=np.float64),
        index=index,
        columns=[spec.instrument for spec in mapping.columns.values()],
    )
    if index.is_monotonic_decreasing and not index.has_duplicates and len(index) > 1:
        frame = frame.iloc[::-1]
        notes.append("Rows reversed from the file's newest-first order.")
    elif not (index.is_monotonic_increasing and not index.has_duplicates):
        raise ParseError("dates must be strictly monotonic (no duplicates, no mixed order)")
    inferred = infer_frequency(pd.DatetimeIndex(frame.index))
    if inferred is not None and inferred is not mapping.frequency:
        raise ParseError(
            f"declared frequency {mapping.frequency.name} but the dates look {inferred.name}"
        )

    notes.extend(
        f"{spec.instrument}: {_PRICE_TYPE_TEXT[spec.price_type]}; source column {name!r}."
        for name, spec in mapping.columns.items()
    )
    ignored = [h for h in header if h != mapping.date_column and h not in mapping.columns]
    if ignored:
        notes.append(f"Ignored columns: {ignored}.")
    notes.append("Empty cells kept as NaN; no forward fill.")
    if mapping.file_format is FileFormat.XLSX:
        notes.append(f"Read sheet {mapping.sheet!r} of an xlsx workbook.")
    elif mapping.file_format is FileFormat.SPREADSHEETML:
        notes.append(f"Read sheet {mapping.sheet!r} of an XML spreadsheet (SpreadsheetML).")
    if mapping.value_affixes:
        notes.append(f"Symbols removed from numbers: {list(mapping.value_affixes)}.")
    if mapping.missing_tokens:
        notes.append(f"Cells equal to {list(mapping.missing_tokens)} treated as unknown.")
    dataset = Dataset(
        data=frame,
        provenance=provenance,
        frequency=mapping.frequency,
        unit=Unit.PRICE,
        return_kind=None,
        currency=mapping.currency,
        availability="User-supplied; each value is assumed known at the end of its date.",
        notes=tuple(notes),
    )
    price_types = {spec.instrument: spec.price_type for spec in mapping.columns.values()}
    return PriceData(dataset=dataset, price_types=price_types)


def load_csv_mapping(path: Path) -> CsvMapping:
    """Load a :class:`CsvMapping` from a TOML file (see ``configs/csv_mappings/``).

    ``thousands_separator = ""`` means no thousands separator. Unknown or missing keys raise.
    """
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    if "file_format" not in raw:
        raise ValidationError(f"{path}: missing keys ['file_format']")
    try:
        file_format = FileFormat(raw["file_format"])
    except ValueError:
        raise ValidationError(f"{path}: unknown file_format {raw['file_format']!r}") from None
    expected = {
        "file_format", "skip_rows", "value_affixes", "missing_tokens", "date_column", "date_format",
        "decimal_separator", "thousands_separator", "currency", "frequency", "columns",
    }  # fmt: skip
    expected |= {"delimiter", "encoding"} if file_format is FileFormat.CSV else {"sheet"}
    _check_keys(raw, expected, str(path))
    columns: dict[str, ColumnSpec] = {}
    for name, spec in raw["columns"].items():
        _check_keys(spec, {"instrument", "price_type"}, f"column {name!r}")
        try:
            price_type = PriceType(spec["price_type"])
        except ValueError:
            raise ValidationError(
                f"column {name!r}: unknown price_type {spec['price_type']!r}"
            ) from None
        columns[name] = ColumnSpec(spec["instrument"], price_type)
    try:
        frequency = Frequency[str(raw["frequency"]).upper()]
    except KeyError:
        raise ValidationError(f"unknown frequency {raw['frequency']!r}") from None
    return CsvMapping(
        date_column=raw["date_column"],
        date_format=raw["date_format"],
        delimiter=raw.get("delimiter"),
        decimal_separator=raw["decimal_separator"],
        thousands_separator=raw["thousands_separator"] or None,
        encoding=raw.get("encoding"),
        currency=Currency(raw["currency"]),
        frequency=frequency,
        columns=columns,
        file_format=file_format,
        sheet=raw.get("sheet"),
        skip_rows=raw["skip_rows"],
        value_affixes=check_affixes(raw["value_affixes"]),
        missing_tokens=tuple(raw["missing_tokens"])
        if isinstance(raw["missing_tokens"], list)
        else raw["missing_tokens"],
    )


def import_local_file(
    path: Path,
    store: RawStore,
    *,
    dataset: str,
    now: Callable[[], datetime],
    source: str = "user",
) -> StoredFile:
    """Copy a local file byte-for-byte into the raw store with provenance.

    Only the file *name* is recorded (``file:<name>``), never its directory, so no
    machine-specific path ends up in provenance records.
    """
    path = Path(path)
    content = path.read_bytes()
    if not content:
        raise ValidationError(f"{path.name} is empty; nothing imported")
    provenance = Provenance(
        source=source,
        dataset=dataset,
        url=f"file:{path.name}",
        retrieved_at=now(),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="user-supplied file; stays in the git-ignored data folder",
    )
    return store.put(content, provenance)


# --------------------------------------------------------------------------- helpers
def _price_rows(content: bytes, mapping: CsvMapping) -> list[tuple[int, list[object]]]:
    """Return the header and the non-empty rows after the preamble, with their line numbers."""
    if mapping.file_format is FileFormat.XLSX:
        body = read_xlsx_rows(content, sheet=str(mapping.sheet), skip_rows=mapping.skip_rows)
    elif mapping.file_format is FileFormat.SPREADSHEETML:
        body = read_spreadsheetml_rows(
            content, sheet=str(mapping.sheet), skip_rows=mapping.skip_rows
        )
    else:
        try:
            text = content.decode(str(mapping.encoding))
        except UnicodeDecodeError as exc:
            raise ParseError(f"cannot decode the file with encoding {mapping.encoding!r}") from exc
        lines = list(csv.reader(io.StringIO(text), delimiter=str(mapping.delimiter)))
        if len(lines) <= mapping.skip_rows:
            raise ParseError(f"file has no header after skipping {mapping.skip_rows} line(s)")
        body = [list[object](row) for row in lines[mapping.skip_rows :]]
    rows = [
        (line, row)
        for line, row in enumerate(body, start=mapping.skip_rows + 1)
        if any(_cell(value).strip() for value in row)
    ]
    if not rows:
        raise ParseError("file has no header")
    return rows


def _cell(value: object) -> str:
    """Return a cell as text (``None`` is empty)."""
    return "" if value is None else str(value)


def _row_date(value: object, fmt: str, line: int) -> pd.Timestamp:
    """Read a date cell: a date of an xlsx sheet as it is, text with the declared format."""
    if isinstance(value, date):
        return pd.Timestamp(value).normalize()
    return _parse_date(_cell(value).strip(), fmt, line)


def _parse_date(text: str, fmt: str, line: int) -> pd.Timestamp:
    shown = text
    if "%b" in fmt:  # English month abbreviations, whatever the machine's language
        match = _WORD.search(text)
        if match is None or match.group() not in _MONTHS:
            raise ParseError(f"line {line}: invalid date {shown!r} for format {fmt!r}")
        text = text[: match.start()] + _MONTHS[match.group()] + text[match.end() :]
        fmt = fmt.replace("%b", "%m")
    try:
        return pd.Timestamp(datetime.strptime(text, fmt))
    except ValueError:
        raise ParseError(f"line {line}: invalid date {shown!r} for format {fmt!r}") from None


def parse_number(
    raw: str,
    *,
    decimal_separator: str,
    thousands_separator: str | None,
    line: int,
    affixes: Sequence[str] = (),
) -> float:
    """Parse one number written with declared separators; an empty cell is NaN.

    Only digits, a leading minus, the decimal separator and the thousands separator are
    allowed, and thousands groups must have three digits. Anything else raises, so ``1.5`` in
    a file with decimal ``,`` and thousands ``.`` is an error rather than 1.5 or 15.

    Parameters
    ----------
    raw
        Cell text.
    decimal_separator, thousands_separator
        As declared in the mapping.
    line
        Line number used in error messages.
    affixes
        Declared symbols removed at the start or the end (``$``, ``%`` ...; phase 8.2b).
    """
    text = _normalised(
        strip_affixes(raw, affixes, line), decimal_separator, thousands_separator, line
    )
    return float("nan") if text is None else float(text)


def parse_decimal(
    raw: str, *, decimal_separator: str, thousands_separator: str | None, line: int
) -> Decimal | None:
    """Parse one number exactly as a ``Decimal`` (``None`` for an empty cell).

    Same rules as :func:`parse_number`; used for money and quantities, which must be exact.
    """
    text = _normalised(raw, decimal_separator, thousands_separator, line)
    return None if text is None else Decimal(text)


def _normalised(raw: str, decimal: str, thousands: str | None, line: int) -> str | None:
    """Return the number in plain ``-123.45`` form, ``None`` if empty; raise if ambiguous."""
    text = raw.strip()
    if not text:
        return None
    allowed = set("0123456789-") | {decimal} | ({thousands} if thousands else set())
    for char in text:
        if char not in allowed:
            raise ParseError(f"line {line}: unexpected character {char!r} in {text!r}")
    if thousands and thousands in text:
        grouped = rf"^-?\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+(?:{re.escape(decimal)}\d+)?$"
        if not re.match(grouped, text):
            raise ParseError(f"line {line}: {text!r} is not a number in the declared format")
        text = text.replace(thousands, "")
    normalised = text.replace(decimal, ".")
    if not re.match(r"^-?\d+(?:\.\d+)?$", normalised):
        raise ParseError(f"line {line}: {raw.strip()!r} is not a number in the declared format")
    return normalised


def _parse_price(raw: object, mapping: CsvMapping, line: int) -> float:
    if isinstance(raw, str) and raw.strip() in mapping.missing_tokens:
        return float("nan")
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        value = float(raw)  # a numeric cell of an xlsx sheet
    else:
        value = parse_number(
            _cell(raw),
            decimal_separator=mapping.decimal_separator,
            thousands_separator=mapping.thousands_separator,
            line=line,
            affixes=mapping.value_affixes,
        )
    if value <= 0:
        raise ParseError(f"line {line}: prices must be positive, got {value}")
    return value


def _check_keys(table: Mapping[str, object], expected: set[str], where: str) -> None:
    missing = sorted(expected - set(table))
    unexpected = sorted(set(table) - expected)
    if missing:
        raise ValidationError(f"{where}: missing keys {missing}")
    if unexpected:
        raise ValidationError(f"{where}: unexpected keys {unexpected}")


def _is_instrument_id(value: object) -> bool:
    return isinstance(value, str) and bool(_INSTRUMENT.match(value))
