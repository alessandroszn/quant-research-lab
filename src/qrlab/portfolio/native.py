"""The native qrlab transactions file: one fixed CSV layout, read without a mapping (8.8a).

The file the app writes when a portfolio is described by hand, and that anyone can write:

- UTF-8, comma-delimited, with exactly the header :data:`NATIVE_COLUMNS`;
- ISO dates (``2026-01-02``), rows in ascending date order (ties keep their order);
- dot decimals with no thousands separator, numbers as in the library: never negative;
- ``kind`` is the :class:`~qrlab.portfolio.transactions.TransactionKind` value (``buy``,
  ``transfer_in``, ...);
- ``fees`` and ``taxes`` are always written, with their currency (``0`` for none), so no
  currency is ever assumed;
- cells a kind does not use are empty.

Reading goes through :func:`~qrlab.portfolio.broker_import.parse_broker_csv` with
:data:`NATIVE_MAPPING`, the same validated path as a broker export.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from decimal import Decimal

from qrlab.core.money import Currency, Money
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.portfolio.broker_import import BrokerImport, BrokerMapping, parse_broker_csv
from qrlab.portfolio.transactions import Transaction, TransactionKind

__all__ = ["NATIVE_COLUMNS", "NATIVE_MAPPING", "parse_native_csv", "write_native_csv"]

NATIVE_COLUMNS = (
    "id", "trade_date", "kind", "account", "isin", "quantity", "price", "price_currency",
    "cost", "cost_currency", "amount", "amount_currency", "fees", "fees_currency", "taxes",
    "taxes_currency", "fx_counter", "fx_counter_currency", "note",
)  # fmt: skip
"""The header of a native file, in order."""

NATIVE_MAPPING = BrokerMapping(
    delimiter=",",
    decimal_separator=".",
    thousands_separator=None,
    encoding="utf-8",
    date_format="%Y-%m-%d",
    date_order="ascending",
    amount_sign="absolute",
    # Never used: fees and taxes are required cells in a native file (checked before reading).
    zero_charge_currency=Currency("EUR"),
    columns={column: column for column in NATIVE_COLUMNS},
    kinds={kind.value: kind for kind in TransactionKind},
)
"""The :class:`~qrlab.portfolio.broker_import.BrokerMapping` of the native layout."""

_REQUIRED_CELLS = ("fees", "fees_currency", "taxes", "taxes_currency")


def parse_native_csv(content: bytes, provenance: Provenance) -> BrokerImport:
    """Read a native transactions file into validated transactions, in date order.

    Raises
    ------
    ParseError
        A header other than :data:`NATIVE_COLUMNS`, a missing fee or tax cell, or anything
        :func:`~qrlab.portfolio.broker_import.parse_broker_csv` refuses.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("a native transactions file must be UTF-8") from exc
    rows = [row for row in csv.reader(io.StringIO(text)) if any(c.strip() for c in row)]
    if not rows or tuple(cell.strip() for cell in rows[0]) != NATIVE_COLUMNS:
        raise ParseError(f"the header must be exactly {','.join(NATIVE_COLUMNS)}")
    for line, row in enumerate(rows[1:], start=2):
        if len(row) != len(NATIVE_COLUMNS):
            continue  # reported with its line by parse_broker_csv
        for name in _REQUIRED_CELLS:
            if not row[NATIVE_COLUMNS.index(name)].strip():
                raise ParseError(f"line {line}: {name} must be written (0 for none)")
    imported = parse_broker_csv(content, provenance, NATIVE_MAPPING)
    return BrokerImport(imported.transactions, (), provenance)


def write_native_csv(transactions: Iterable[Transaction]) -> bytes:
    """Write transactions as a native file, sorted by date (a stable sort: ties keep order)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(NATIVE_COLUMNS)
    for t in sorted(transactions, key=lambda t: t.trade_date):
        writer.writerow(
            [
                t.id,
                t.trade_date.isoformat(),
                t.kind.value,
                t.account,
                "" if t.isin is None else t.isin.code,
                _number(t.quantity),
                *_money(t.price),
                *_money(t.cost),
                *_money(t.amount),
                *_money(t.fees),
                *_money(t.taxes),
                *_money(t.fx_counter),
                t.note,
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _number(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _money(value: Money | None) -> tuple[str, str]:
    return ("", "") if value is None else (_number(value.amount), value.currency.code)
