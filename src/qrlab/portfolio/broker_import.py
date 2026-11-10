"""Broker transaction exports read through an explicit mapping.

Nothing is guessed. A :class:`BrokerMapping` declares separators, encoding, date format, the
order of rows, how signs are written, the column of every transaction field (or a constant
written ``"=value"``) and the broker's wording for each :class:`TransactionKind`. Unknown wording,
ambiguous numbers, wrong signs and missing currencies raise.

Real exports and mappings that reveal personal details stay in the git-ignored ``data/``.
"""

from __future__ import annotations

import codecs
import csv
import io
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.data.user_csv import parse_decimal
from qrlab.instruments.identifiers import Isin
from qrlab.portfolio.transactions import Transaction, TransactionKind

__all__ = ["BrokerImport", "BrokerMapping", "load_broker_mapping", "parse_broker_csv"]

K = TransactionKind
FIELDS = frozenset(
    {
        "id", "trade_date", "kind", "account", "isin", "quantity", "price", "price_currency",
        "amount", "amount_currency", "fees", "fees_currency", "taxes", "taxes_currency",
        "fx_counter", "fx_counter_currency", "note",
    }
)  # fmt: skip
REQUIRED_FIELDS = ("id", "trade_date", "kind", "account")
_DELIMITERS = frozenset({",", ";", "\t", "|"})
# Expected sign of signed amounts and quantities per kind (+1 inflow, -1 outflow).
_AMOUNT_SIGN = {
    K.DEPOSIT: 1, K.DIVIDEND: 1, K.INTEREST: 1,
    K.WITHDRAWAL: -1, K.FEE: -1, K.TAX: -1, K.FX_CONVERSION: -1,
}  # fmt: skip
_QUANTITY_SIGN = {K.BUY: 1, K.TRANSFER_IN: 1, K.SPLIT: 1, K.SELL: -1, K.TRANSFER_OUT: -1}


@dataclass(frozen=True)
class BrokerMapping:
    """How to read a broker export. Every field is required.

    Parameters
    ----------
    delimiter, decimal_separator, thousands_separator, encoding, date_format
        File format (see :class:`qrlab.data.user_csv.CsvMapping`).
    date_order
        ``"ascending"`` (oldest first) or ``"descending"`` (newest first; the rows are then
        reversed as a whole, which restores chronological order also within a day).
    amount_sign
        ``"signed"``: outflows are negative in the file; signs are checked against each kind and
        then removed. ``"absolute"``: every number must be >= 0.
    zero_charge_currency
        Currency of the zero fee or tax recorded when the cell is empty.
    columns
        Transaction field to column header, or to a constant written ``"=value"``. ``id``,
        ``trade_date``, ``kind`` and ``account`` are required.
    kinds
        Broker wording to transaction kind.
    """

    delimiter: str
    decimal_separator: str
    thousands_separator: str | None
    encoding: str
    date_format: str
    date_order: str
    amount_sign: str
    zero_charge_currency: Currency
    columns: Mapping[str, str]
    kinds: Mapping[str, TransactionKind]

    def __post_init__(self) -> None:
        """Validate the mapping as a whole."""
        if self.delimiter not in _DELIMITERS:
            raise ValidationError(f"delimiter {self.delimiter!r} not in {sorted(_DELIMITERS)}")
        if self.decimal_separator not in {".", ","}:
            raise ValidationError("decimal_separator must be '.' or ','")
        if self.thousands_separator == self.decimal_separator:
            raise ValidationError("decimal and thousands separators must differ")
        if self.delimiter == self.decimal_separator:
            raise ValidationError("delimiter must differ from the decimal separator")
        try:
            codecs.lookup(self.encoding)
        except LookupError:
            raise ValidationError(f"unknown encoding {self.encoding!r}") from None
        if not all(token in self.date_format for token in ("%d", "%m")) or not (
            "%Y" in self.date_format or "%y" in self.date_format
        ):
            raise ValidationError(f"date_format {self.date_format!r} needs %d, %m and %Y or %y")
        if self.date_order not in {"ascending", "descending"}:
            raise ValidationError(
                f"date_order must be 'ascending' or 'descending', not {self.date_order!r}"
            )
        if self.amount_sign not in {"signed", "absolute"}:
            raise ValidationError(
                f"amount_sign must be 'signed' or 'absolute', not {self.amount_sign!r}"
            )
        unknown = sorted(set(self.columns) - FIELDS)
        if unknown:
            raise ValidationError(f"unknown transaction fields {unknown}")
        for required in REQUIRED_FIELDS:
            if required not in self.columns:
                raise ValidationError(f"column mapping must include {required!r}")
        if not self.kinds:
            raise ValidationError("kinds must map at least one broker wording")


@dataclass(frozen=True)
class BrokerImport:
    """Transactions read from a broker export, in chronological order."""

    transactions: tuple[Transaction, ...]
    notes: tuple[str, ...]
    provenance: Provenance


def parse_broker_csv(
    content: bytes, provenance: Provenance, mapping: BrokerMapping
) -> BrokerImport:
    """Read a broker export into validated transactions (see the module docstring)."""
    try:
        text = content.decode(mapping.encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(f"cannot decode the file with encoding {mapping.encoding!r}") from exc
    rows = [
        row
        for row in csv.reader(io.StringIO(text), delimiter=mapping.delimiter)
        if any(c.strip() for c in row)
    ]
    if not rows:
        raise ParseError("file has no header")
    header = [cell.strip() for cell in rows[0]]
    for field, source in mapping.columns.items():
        if not source.startswith("=") and source not in header:
            raise ParseError(f"column {source!r} (for {field}) not found in header {header}")
    reader = _RowReader(header, mapping)
    transactions = [reader.transaction(row, line) for line, row in enumerate(rows[1:], start=2)]
    if not transactions:
        raise ParseError("file contains no transactions")

    ids = [t.id for t in transactions]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        raise ParseError(f"duplicated transaction ids {duplicated}")
    dates = [t.trade_date for t in transactions]
    notes: list[str] = []
    if mapping.date_order == "ascending":
        if any(b < a for a, b in pairwise(dates)):
            raise ParseError("dates are not in ascending order as declared")
    else:
        if any(b > a for a, b in pairwise(dates)):
            raise ParseError("dates are not in descending order as declared")
        transactions.reverse()
        notes.append("File listed newest first; rows reversed as a whole (chronological order).")
    if mapping.amount_sign == "signed":
        notes.append(
            "Amounts were signed in the file; signs checked against each kind and removed."
        )
    notes.append(f"Empty fees and taxes recorded as zero {mapping.zero_charge_currency}.")
    used = {source for source in mapping.columns.values() if not source.startswith("=")}
    ignored = [h for h in header if h not in used]
    if ignored:
        notes.append(f"Ignored columns: {ignored}.")
    return BrokerImport(tuple(transactions), tuple(notes), provenance)


class _RowReader:
    def __init__(self, header: list[str], mapping: BrokerMapping) -> None:
        self.header = header
        self.mapping = mapping

    def cell(self, row: list[str], field: str) -> str | None:
        source = self.mapping.columns.get(field)
        if source is None:
            return None
        if source.startswith("="):
            return source[1:]
        value = row[self.header.index(source)].strip()
        return value or None

    def number(self, row: list[str], field: str, line: int) -> Decimal | None:
        text = self.cell(row, field)
        if text is None:
            return None
        value = parse_decimal(
            text,
            decimal_separator=self.mapping.decimal_separator,
            thousands_separator=self.mapping.thousands_separator,
            line=line,
        )
        if value is not None and value < 0 and self.mapping.amount_sign == "absolute":
            raise ParseError(f"line {line}: negative {field} in a file declared 'absolute'")
        return value

    def signed(
        self, value: Decimal | None, expected: int | None, field: str, line: int
    ) -> Decimal | None:
        if value is None or self.mapping.amount_sign == "absolute":
            return value
        if expected is not None and value != 0 and (value > 0) != (expected > 0):
            word = "positive" if expected > 0 else "negative"
            raise ParseError(f"line {line}: {field} should be {word} for this kind (sign check)")
        return abs(value)

    def money(self, row: list[str], field: str, value: Decimal | None, line: int) -> Money | None:
        if value is None:
            return None
        code = self.cell(row, f"{field}_currency")
        if code is None:
            raise ParseError(f"line {line}: {field} has no currency")
        return Money(value, Currency(code))

    def transaction(self, row: list[str], line: int) -> Transaction:
        if len(row) != len(self.header):
            raise ParseError(f"line {line}: expected {len(self.header)} fields, got {len(row)}")
        wording = self.cell(row, "kind")
        if wording is None or wording not in self.mapping.kinds:
            raise ParseError(f"line {line}: unknown transaction wording {wording!r}")
        kind = self.mapping.kinds[wording]
        date_text = self.cell(row, "trade_date") or ""
        try:
            trade_date: date = datetime.strptime(date_text, self.mapping.date_format).date()
        except ValueError:
            raise ParseError(f"line {line}: invalid date {date_text!r}") from None
        quantity = self.signed(
            self.number(row, "quantity", line), _QUANTITY_SIGN.get(kind), "quantity", line
        )
        amount = self.signed(
            self.number(row, "amount", line), _AMOUNT_SIGN.get(kind), "amount", line
        )
        counter = self.signed(self.number(row, "fx_counter", line), 1, "fx_counter", line)
        price = self.number(row, "price", line)
        charges = {}
        for field in ("fees", "taxes"):
            value = self.number(row, field, line)
            charges[field] = (
                Money(Decimal(0), self.mapping.zero_charge_currency)
                if value is None
                else self.money(row, field, abs(value), line)
            )
        isin_text = self.cell(row, "isin")
        try:
            return Transaction(
                id=self.cell(row, "id") or "",
                trade_date=trade_date,
                kind=kind,
                account=self.cell(row, "account") or "",
                isin=None if isin_text is None else Isin(isin_text),
                quantity=quantity,
                price=self.money(row, "price", price, line),
                amount=self.money(row, "amount", amount, line),
                fees=charges["fees"],  # type: ignore[arg-type]
                taxes=charges["taxes"],  # type: ignore[arg-type]
                fx_counter=self.money(row, "fx_counter", counter, line),
                note=self.cell(row, "note") or "",
            )
        except ValidationError as exc:
            if isinstance(exc, ParseError):
                raise
            raise ParseError(f"line {line}: {exc}") from exc


def load_broker_mapping(path: Path) -> BrokerMapping:
    """Load a :class:`BrokerMapping` from TOML.

    See ``configs/csv_mappings/example_broker.toml`` for an annotated example.
    """
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    expected = {
        "delimiter", "decimal_separator", "thousands_separator", "encoding", "date_format",
        "date_order", "amount_sign", "zero_charge_currency", "columns", "kinds",
    }  # fmt: skip
    missing, unexpected = sorted(expected - set(raw)), sorted(set(raw) - expected)
    if missing or unexpected:
        raise ValidationError(
            f"{Path(path).name}: missing keys {missing}, unexpected keys {unexpected}"
        )
    kinds: dict[str, TransactionKind] = {}
    for wording, value in raw["kinds"].items():
        try:
            kinds[wording] = TransactionKind(value)
        except ValueError:
            raise ValidationError(
                f"kinds[{wording!r}]: {value!r} is not a transaction kind"
            ) from None
    return BrokerMapping(
        delimiter=raw["delimiter"],
        decimal_separator=raw["decimal_separator"],
        thousands_separator=raw["thousands_separator"] or None,
        encoding=raw["encoding"],
        date_format=raw["date_format"],
        date_order=raw["date_order"],
        amount_sign=raw["amount_sign"],
        zero_charge_currency=Currency(raw["zero_charge_currency"]),
        columns=dict(raw["columns"]),
        kinds=kinds,
    )
