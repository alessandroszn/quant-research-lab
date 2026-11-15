"""Library helpers behind the app's Portfolio screen (design 8.8b): no prices, no rates."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from qrlab.core.errors import QrlabError, ValidationError
from qrlab.experiments import load_config
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.workspace import config_template
from qrlab.instruments import (
    INSTRUMENT_FIELDS,
    instrument_fields,
    instrument_from_fields,
    load_instruments,
    write_instruments_toml,
)
from qrlab.portfolio import check_transactions, kind_columns
from qrlab.portfolio.transactions import TransactionKind
from support.portfolio import D0, D1, X, Y, money, tx

ROOT = Path(__file__).parents[3]
K = TransactionKind
FIELDS = {
    "isin": "IE0000000012",
    "name": 'Example "World" ETF',
    "instrument_type": "etf",
    "asset_class": "equity",
    "currency": "EUR",
    "as_of": "2026-01-02",
    "domicile": "IE",
    "replication": "physical_sampling",
    "distribution": "accumulating",
    "ter": "0.0020",
    "benchmark": "unknown",
    "hedged_to": "none",
    "inception": "2010-05-03",
    "fund_size": "1500000000 EUR",
    "source": "factsheet 2026-01",
}


# --------------------------------------------------------------------------- instruments
def test_the_fields_are_the_toml_keys_with_the_isin_first() -> None:
    assert INSTRUMENT_FIELDS[0] == "isin"
    assert set(FIELDS) == set(INSTRUMENT_FIELDS)


def test_fields_to_instrument_and_back() -> None:
    instrument = instrument_from_fields(FIELDS)
    assert instrument.as_of == date(2026, 1, 2)
    assert instrument.inception == date(2010, 5, 3)
    assert instrument.benchmark is None
    assert instrument.hedged_to is None
    assert instrument.fund_size == money("1500000000")
    assert instrument_fields(instrument) == FIELDS


def test_the_toml_writer_round_trips(tmp_path: Path) -> None:
    for name in ("instruments.toml", "instruments_full.toml"):
        original = load_instruments(ROOT / "examples/data" / name)
        path = tmp_path / name
        path.write_text(write_instruments_toml(original), encoding="utf-8")
        assert load_instruments(path) == original
    quoted = [instrument_from_fields(FIELDS)]
    (tmp_path / "q.toml").write_text(write_instruments_toml(quoted), encoding="utf-8")
    assert load_instruments(tmp_path / "q.toml") == quoted


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"as_of": "02/01/2026"}, "as_of must be a date such as 2026-10-01"),
        ({"inception": "soon"}, "inception must be a date"),
        ({"fund_size": "1500000000"}, "fund_size"),
        ({"ter": "0,20"}, "not a decimal"),
        ({"instrument_type": "share"}, "instrument_type"),
        ({"isin": "IE0000000013"}, "check digit"),
        ({"currency": ""}, "currency"),
    ],
)
def test_wrong_fields_raise(change: dict[str, str], match: str) -> None:
    with pytest.raises(QrlabError, match=match):
        instrument_from_fields(FIELDS | change)


def test_missing_and_unexpected_fields_raise() -> None:
    with pytest.raises(ValidationError, match="missing keys"):
        instrument_from_fields({k: v for k, v in FIELDS.items() if k != "ter"})
    with pytest.raises(ValidationError, match="unexpected keys"):
        instrument_from_fields(FIELDS | {"rating": "AAA"})


# --------------------------------------------------------------------------- transactions
def test_the_columns_each_kind_uses() -> None:
    common = {"id", "trade_date", "kind", "account", "fees", "fees_currency", "taxes"}
    common |= {"taxes_currency", "note"}
    assert set(kind_columns(K.DEPOSIT)) == common | {"amount", "amount_currency"}
    assert set(kind_columns(K.BUY)) == common | {"isin", "quantity", "price", "price_currency"}
    assert set(kind_columns(K.TRANSFER_IN)) == set(kind_columns(K.BUY)) | {
        "cost",
        "cost_currency",
    }
    assert set(kind_columns(K.FX_CONVERSION)) == common | {
        "amount",
        "amount_currency",
        "fx_counter",
        "fx_counter_currency",
    }
    assert set(kind_columns(K.SPLIT)) == common | {"isin", "quantity"}
    assert set(kind_columns(K.DIVIDEND)) == common | {"isin", "amount", "amount_currency"}


def test_check_transactions_needs_no_rates() -> None:
    check_transactions(
        [
            tx("d", D0, K.DEPOSIT, amount=money(100, "USD")),
            tx("b", D0, K.BUY, isin=Y, quantity="1", price=money(50, "USD")),
            tx("i", D0, K.TRANSFER_IN, isin=X, quantity="1", price=money(50), cost=money(40)),
        ]
    )
    with pytest.raises(ValidationError, match="s: cannot remove 2 units"):
        check_transactions(
            [
                tx("i", D0, K.TRANSFER_IN, isin=X, quantity="1", price=money(50)),
                tx("s", D1, K.SELL, isin=X, quantity="2", price=money(50)),
            ]
        )
    with pytest.raises(ValidationError, match="b: negative cash"):
        check_transactions([tx("b", D0, K.BUY, isin=X, quantity="1", price=money(50))])


# --------------------------------------------------------------------------- config template
def test_a_template_with_values(tmp_path: Path) -> None:
    kind = KINDS["portfolio_report"]
    text = config_template(
        kind,
        inputs={"transactions": "../portfolios/p/transactions.csv"},
        parameters={"transactions_format": '"native"'},
    )
    assert 'transactions = "../portfolios/p/transactions.csv"\n' in text
    assert 'transactions_format = "native"\n' in text
    assert "# transactions_format" not in text
    assert '# instruments = "../data/FILL-IN"' not in text  # required inputs stay filled-in
    assert 'instruments = "../data/FILL-IN"' in text
    path = tmp_path / "p.toml"
    path.write_text(text, encoding="utf-8")
    assert load_config(path).inputs["transactions"].name == "transactions.csv"
    assert config_template(kind) == config_template(kind, inputs={}, parameters={})


def test_template_values_must_be_the_kinds() -> None:
    kind = KINDS["portfolio_report"]
    with pytest.raises(ValidationError, match="unknown inputs"):
        config_template(kind, inputs={"trades": "x.csv"})
    with pytest.raises(ValidationError, match="unknown parameters"):
        config_template(kind, parameters={"format": '"native"'})
