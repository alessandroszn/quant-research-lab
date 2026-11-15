"""Portfolio folders of a workspace (design 8.8b): rows of text, checked and written."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.provenance import Provenance
from qrlab.experiments.portfolios import (
    INSTRUMENTS_FILE,
    NATIVE_COLUMNS,
    TRANSACTION_KINDS,
    TRANSACTIONS_FILE,
    PortfolioProblem,
    check_portfolio,
    import_downloaded_file,
    kind_columns,
    read_portfolio,
    write_portfolio,
)
from qrlab.instruments import load_instruments
from qrlab.portfolio import parse_native_csv
from qrlab.portfolio.transactions import TransactionKind

NOW = datetime(2026, 2, 1, tzinfo=UTC)
X = "IE0000000012"
INSTRUMENT = {
    "isin": X,
    "name": "Example World Equity UCITS ETF",
    "instrument_type": "etf",
    "asset_class": "equity",
    "currency": "EUR",
    "as_of": "2026-01-02",
    "domicile": "unknown",
    "replication": "unknown",
    "distribution": "unknown",
    "ter": "unknown",
    "benchmark": "unknown",
    "hedged_to": "none",
    "inception": "unknown",
    "fund_size": "unknown",
    "source": "synthetic example",
}


def _row(**cells: str) -> dict[str, str]:
    row = dict.fromkeys(NATIVE_COLUMNS, "")
    row |= {"account": "main", "fees": "0", "fees_currency": "EUR", "taxes": "0"}
    row |= {"taxes_currency": "EUR"}
    return row | cells


SALE = _row(
    id="s", trade_date="2026-01-30", kind="sell", isin=X, quantity="50", price="55",
    price_currency="EUR",
)  # fmt: skip
TRANSFER = _row(
    id="i", trade_date="2026-01-02", kind="transfer_in", isin=X, quantity="100", price="50",
    price_currency="EUR", cost="40", cost_currency="EUR",
)  # fmt: skip
DEPOSIT = _row(
    id="d", trade_date="2026-01-02", kind="deposit", amount="1000", amount_currency="EUR"
)


def test_kinds_and_their_columns() -> None:
    assert tuple(k.value for k in TransactionKind) == TRANSACTION_KINDS
    assert "cost" in kind_columns("transfer_in")
    assert kind_columns("nonsense") == ("id", "kind")


def test_rows_typed_out_of_order_are_written_sorted(tmp_path: Path) -> None:
    rows = [SALE, DEPOSIT, TRANSFER]
    assert check_portfolio(rows, [INSTRUMENT], now=lambda: NOW) is None
    write_portfolio(tmp_path / "p", rows, [INSTRUMENT], now=lambda: NOW)
    content = (tmp_path / "p" / TRANSACTIONS_FILE).read_bytes()
    read = parse_native_csv(content, _provenance()).transactions
    assert [t.id for t in read] == ["d", "i", "s"]  # by date, the same-day tie kept
    assert [i.isin.code for i in load_instruments(tmp_path / "p" / INSTRUMENTS_FILE)] == [X]
    transactions, instruments = read_portfolio(tmp_path / "p")
    assert [r["id"] for r in transactions] == ["d", "i", "s"]
    assert instruments == [INSTRUMENT]
    assert read_portfolio(tmp_path / "missing") == ([], [])


@pytest.mark.parametrize(
    ("transactions", "instruments", "expected"),
    [
        ([DEPOSIT], [INSTRUMENT | {"as_of": "x"}], ("instruments", 0, "invalid")),
        ([DEPOSIT], [INSTRUMENT, INSTRUMENT], ("instruments", 1, "duplicate_isin")),
        ([], [INSTRUMENT], ("transactions", None, "no_transactions")),
        ([SALE, DEPOSIT | {"amount": "x"}], [INSTRUMENT], ("transactions", 1, "invalid")),
        (
            [SALE, DEPOSIT | {"trade_date": "02/01/2026"}],
            [INSTRUMENT],
            ("transactions", 1, "invalid"),
        ),
        (
            [DEPOSIT, TRANSFER | {"isin": "US0000000044"}],
            [INSTRUMENT],
            ("transactions", 1, "unknown_isin"),
        ),
        ([DEPOSIT, SALE], [INSTRUMENT], ("transactions", 1, "invalid")),
        ([DEPOSIT, DEPOSIT], [INSTRUMENT], ("transactions", None, "invalid")),
    ],
)
def test_problems_name_the_table_and_row(
    tmp_path: Path,
    transactions: list[dict[str, str]],
    instruments: list[dict[str, str]],
    expected: tuple[str, int | None, str],
) -> None:
    problem = check_portfolio(transactions, instruments, now=lambda: NOW)
    assert isinstance(problem, PortfolioProblem)
    assert (problem.table, problem.row, problem.reason) == expected
    with pytest.raises(ValidationError):
        write_portfolio(tmp_path / "p", transactions, instruments, now=lambda: NOW)
    assert not (tmp_path / "p").exists()


def test_a_wrong_header_is_refused(tmp_path: Path) -> None:
    (tmp_path / TRANSACTIONS_FILE).write_text("a,b\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="the header must be exactly"):
        read_portfolio(tmp_path)


def test_a_downloaded_file_goes_into_the_raw_store_unchanged(tmp_path: Path) -> None:
    download = tmp_path / "nav.csv"
    download.write_bytes(b"Date,NAV\n2026-01-02,50\n")
    stored = import_downloaded_file(tmp_path / "ws", download, dataset="nav-world", now=lambda: NOW)
    assert stored.read_bytes() == download.read_bytes()
    assert stored.is_relative_to(tmp_path / "ws" / "data" / "raw" / "user" / "nav-world")


def _provenance() -> Provenance:
    return Provenance(
        source="test",
        dataset="transactions",
        url="file:transactions.csv",
        retrieved_at=NOW,
        sha256="0" * 64,
        size_bytes=0,
        terms="synthetic",
    )
