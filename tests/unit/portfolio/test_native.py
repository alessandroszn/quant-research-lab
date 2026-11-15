"""The native qrlab transactions file (design 8.8a), by hand.

A deposit of 1,000 EUR, a buy of 10 X at 50.00 with a 2.00 fee (cost basis 502.00) and a
transfer in of 5 X at a market price of 52 with an original cost of 40.5 per unit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from qrlab.core.money import Money
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.native import NATIVE_COLUMNS, parse_native_csv, write_native_csv
from qrlab.portfolio.transactions import TransactionKind
from support.portfolio import D0, D1, EUR, X, eur_only, money, tx

K = TransactionKind
PROVENANCE = Provenance(
    source="test",
    dataset="transactions",
    url="file:transactions.csv",
    retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
    sha256="0" * 64,
    size_bytes=0,
    terms="synthetic",
)
HEADER = (
    "id,trade_date,kind,account,isin,quantity,price,price_currency,cost,cost_currency,amount,"
    "amount_currency,fees,fees_currency,taxes,taxes_currency,fx_counter,fx_counter_currency,note\n"
)
TRANSACTIONS = [
    tx("d1", D0, K.DEPOSIT, amount=money(1000)),
    tx(
        "b1",
        D0,
        K.BUY,
        isin=X,
        quantity="10",
        price=money("50.00"),
        fees=money("2.00"),
        note="first buy, test",
    ),
    tx("t1", D1, K.TRANSFER_IN, isin=X, quantity="5", price=money(52), cost=money("40.5")),
]
FILE = (
    HEADER
    + "d1,2026-01-02,deposit,main,,,,,,,1000,EUR,0,EUR,0,EUR,,,\n"
    + 'b1,2026-01-02,buy,main,IE0000000012,10,50.00,EUR,,,,,2.00,EUR,0,EUR,,,"first buy, test"\n'
    + "t1,2026-01-30,transfer_in,main,IE0000000012,5,52,EUR,40.5,EUR,,,0,EUR,0,EUR,,,\n"
).encode()


def test_the_columns() -> None:
    assert ",".join(NATIVE_COLUMNS) + "\n" == HEADER


def test_the_written_bytes_are_pinned() -> None:
    assert write_native_csv(TRANSACTIONS) == FILE


def test_round_trip_and_the_cost_basis() -> None:
    imported = parse_native_csv(FILE, PROVENANCE)
    assert list(imported.transactions) == TRANSACTIONS
    assert imported.notes == ()
    assert imported.provenance == PROVENANCE
    position = replay(imported.transactions, base=EUR, to_base=eur_only).state_on(D0).positions
    assert position[("main", X)].cost_base == Decimal("502.00")


def test_rows_are_written_in_date_order_keeping_ties() -> None:
    later, first, second = TRANSACTIONS[2], TRANSACTIONS[0], TRANSACTIONS[1]
    assert write_native_csv([later, first, second]) == FILE


def test_numbers_are_written_without_exponents() -> None:
    deposit = tx("d1", D0, K.DEPOSIT, amount=Money(Decimal("1E+3"), EUR))
    assert b",1000,EUR," in write_native_csv([deposit])


@pytest.mark.parametrize(
    ("content", "match"),
    [
        (b"", "header"),
        (FILE.replace(b"first buy", "première".encode("latin-1")), "UTF-8"),
        (FILE.replace(b",,,\n", b",,\n", 1), "expected 19 fields"),
        (HEADER.replace("note", "notes").encode(), "header"),
        (HEADER.encode(), "no transactions"),
        (FILE.replace(b"1000,EUR,0,EUR,0,EUR", b"1000,EUR,,,0,EUR"), "fees"),
        (FILE.replace(b"1000,EUR,0,EUR,0,EUR", b"1000,EUR,0,EUR,,"), "taxes"),
        (FILE.replace(b",50.00,", b',"50,00",'), "50,00"),
        (FILE.replace(b"2026-01-30", b"30/01/2026"), "date"),
        (FILE.replace(b"t1,2026-01-30", b"t1,2025-12-31"), "ascending"),
        (FILE.replace(b",buy,", b",purchase,"), "purchase"),
        (FILE.replace(b",10,50.00,", b",-10,50.00,"), "negative"),
    ],
)
def test_wrong_files_raise(content: bytes, match: str) -> None:
    with pytest.raises(ParseError, match=match):
        parse_native_csv(content, PROVENANCE)
