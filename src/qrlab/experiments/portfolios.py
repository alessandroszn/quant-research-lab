"""Portfolio folders of a workspace (phase 8.8b): read, check and write them with the library.

A portfolio described in the desktop app is a folder ``portfolios/<name>/`` with
``transactions.csv`` (the native qrlab file, :mod:`qrlab.portfolio.native`) and
``instruments.toml``. Here both are handled as rows of text, as a person types them, so that
the app only shows tables.

Checking reads the rows exactly as the ``portfolio_report`` kind will:

- the instruments with :func:`qrlab.instruments.instrument_from_fields`;
- the transactions, sorted by date (ties keep their order), with
  :func:`qrlab.portfolio.parse_native_csv`, then
  :func:`qrlab.portfolio.check_transactions`, which needs no prices or rates.

A problem names its table and its row in the rows given. Writing goes through the library's
writers and only after the check passes. Nothing here computes a number.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from qrlab.core.errors import QrlabError, ValidationError
from qrlab.data.provenance import Provenance
from qrlab.data.store import RawStore
from qrlab.data.user_csv import import_local_file
from qrlab.instruments import (
    INSTRUMENT_FIELDS,
    Instrument,
    instrument_fields,
    instrument_from_fields,
    load_instruments,
    write_instruments_toml,
)
from qrlab.portfolio import (
    NATIVE_COLUMNS,
    Transaction,
    TransactionKind,
    check_transactions,
    parse_native_csv,
    write_native_csv,
)
from qrlab.portfolio import kind_columns as _kind_columns

__all__ = [
    "INSTRUMENTS_FILE",
    "INSTRUMENT_FIELDS",
    "NATIVE_COLUMNS",
    "TRANSACTIONS_FILE",
    "TRANSACTION_KINDS",
    "PortfolioProblem",
    "check_portfolio",
    "import_downloaded_file",
    "kind_columns",
    "read_portfolio",
    "write_portfolio",
]

TRANSACTIONS_FILE = "transactions.csv"
INSTRUMENTS_FILE = "instruments.toml"
TRANSACTION_KINDS = tuple(kind.value for kind in TransactionKind)
"""Every transaction kind, as written in the ``kind`` column."""

Rows = Sequence[Mapping[str, str]]
_LINE = re.compile(r"^line (\d+): ")


@dataclass(frozen=True)
class PortfolioProblem:
    """Why a portfolio's rows cannot be saved.

    ``table`` is ``"transactions"`` or ``"instruments"``; ``row`` is 0-based in the rows given,
    or ``None`` for the table as a whole. ``reason`` is ``"invalid"`` (``detail`` is the
    library's message), ``"duplicate_isin"`` or ``"unknown_isin"`` (``detail`` is the ISIN),
    or ``"no_transactions"``.
    """

    table: str
    row: int | None
    reason: str
    detail: str = ""


def kind_columns(kind: str) -> tuple[str, ...]:
    """Return the native columns a transaction of ``kind`` uses; ``id`` and ``kind`` if unknown."""
    try:
        return _kind_columns(TransactionKind(kind))
    except ValueError:
        return ("id", "kind")


def read_portfolio(folder: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return a portfolio's transactions and instruments as rows of text (missing files: none).

    The transactions are read as text, so a file that does not validate can still be edited;
    its header must be :data:`NATIVE_COLUMNS`.
    """
    transactions: list[dict[str, str]] = []
    instruments: list[dict[str, str]] = []
    csv_path, toml_path = Path(folder) / TRANSACTIONS_FILE, Path(folder) / INSTRUMENTS_FILE
    if csv_path.is_file():
        reader = csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8")))
        if tuple(reader.fieldnames or ()) != NATIVE_COLUMNS:
            raise ValidationError(f"the header must be exactly {','.join(NATIVE_COLUMNS)}")
        transactions = [{c: row[c] or "" for c in NATIVE_COLUMNS} for row in reader]
    if toml_path.is_file():
        instruments = [instrument_fields(i) for i in load_instruments(toml_path)]
    return transactions, instruments


def check_portfolio(
    transactions: Rows, instruments: Rows, *, now: Callable[[], datetime]
) -> PortfolioProblem | None:
    """Check the rows with the library; ``None`` when they can be written.

    ``now`` dates the provenance of the transactions read in memory.
    """
    _, problem = _read(transactions, instruments, now)
    return problem


def write_portfolio(
    folder: Path, transactions: Rows, instruments: Rows, *, now: Callable[[], datetime]
) -> None:
    """Check the rows, then write both files through the library's writers.

    Raises
    ------
    ValidationError
        When :func:`check_portfolio` finds a problem; nothing is written.
    """
    parsed, problem = _read(transactions, instruments, now)
    if problem is not None:
        raise ValidationError(
            f"{problem.table} row {problem.row}: {problem.reason} {problem.detail}"
        )
    assert parsed is not None  # read without a problem
    read_transactions, read_instruments = parsed
    path = Path(folder)
    path.mkdir(parents=True, exist_ok=True)
    (path / INSTRUMENTS_FILE).write_text(
        write_instruments_toml(read_instruments), encoding="utf-8", newline="\n"
    )
    (path / TRANSACTIONS_FILE).write_bytes(write_native_csv(read_transactions))


def import_downloaded_file(
    root: Path, path: Path, *, dataset: str, now: Callable[[], datetime]
) -> Path:
    """Copy a file downloaded by hand into the workspace's raw store, unchanged.

    The provenance names the source ``user``, the ``dataset`` given and only the file's name
    (:func:`qrlab.data.import_local_file`); the stored path is returned.
    """
    return import_local_file(
        Path(path), RawStore(Path(root) / "data"), dataset=dataset, now=now
    ).path


# --------------------------------------------------------------------------- helpers
def _read(
    transactions: Rows, instruments: Rows, now: Callable[[], datetime]
) -> tuple[tuple[list[Transaction], list[Instrument]] | None, PortfolioProblem | None]:
    read_instruments: list[Instrument] = []
    isins: list[str] = []
    for row, fields in enumerate(instruments):
        try:
            instrument = instrument_from_fields(fields)
        except QrlabError as exc:
            return None, PortfolioProblem("instruments", row, "invalid", str(exc))
        if instrument.isin.code in isins:
            return None, PortfolioProblem(
                "instruments", row, "duplicate_isin", instrument.isin.code
            )
        isins.append(instrument.isin.code)
        read_instruments.append(instrument)
    if not transactions:
        return None, PortfolioProblem("transactions", None, "no_transactions")
    order = _date_order(transactions)
    content = _csv(transactions, order)
    try:
        read = parse_native_csv(content, _provenance(content, now)).transactions
    except QrlabError as exc:
        match = _LINE.match(str(exc))
        at_line = order[int(match.group(1)) - 2] if match else None
        return None, PortfolioProblem("transactions", at_line, "invalid", str(exc))
    for row, cells in enumerate(transactions):
        if cells["isin"] and cells["isin"] not in isins:
            return None, PortfolioProblem("transactions", row, "unknown_isin", cells["isin"])
    try:
        check_transactions(read)
    except QrlabError as exc:
        ids = [cells["id"] for cells in transactions]
        prefix = str(exc).split(":", 1)[0]
        at_id = ids.index(prefix) if prefix in ids else None
        return None, PortfolioProblem("transactions", at_id, "invalid", str(exc))
    return (list(read), read_instruments), None


def _date_order(transactions: Rows) -> list[int]:
    """Rows by date, ties in the given order; the given order when a date is not ISO yet.

    The native file must be in date order, so rows typed out of order are sorted; a row with a
    wrong date keeps its place, so the library's error names it.
    """
    rows = range(len(transactions))
    try:
        days = [date.fromisoformat(transactions[i]["trade_date"]) for i in rows]
    except ValueError:
        return list(rows)
    return sorted(rows, key=lambda i: days[i])


def _csv(transactions: Rows, order: Sequence[int]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(NATIVE_COLUMNS)
    writer.writerows([transactions[i][c] for c in NATIVE_COLUMNS] for i in order)
    return buffer.getvalue().encode("utf-8")


def _provenance(content: bytes, now: Callable[[], datetime]) -> Provenance:
    return Provenance(
        source="user",
        dataset="transactions",
        url=f"file:{TRANSACTIONS_FILE}",
        retrieved_at=now(),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="user-supplied file; stays in the workspace",
    )
