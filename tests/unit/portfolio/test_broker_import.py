"""Broker transaction import through an explicit mapping. All files are synthetic.

The example file reproduces the toy portfolio of the design note in an Italian broker format
(newest first, ``;`` delimiter, ``,`` decimals, signed amounts), so the imported transactions
must replay to the same hand values: cash 12,780 and a realised gain of 185.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.data.errors import ParseError
from qrlab.data.provenance import Provenance
from qrlab.portfolio.broker_import import BrokerMapping, load_broker_mapping, parse_broker_csv
from qrlab.portfolio.ledger import replay
from qrlab.portfolio.transactions import TransactionKind
from support.portfolio import EUR, X, eur_only

K = TransactionKind
MAPPING_FILE = Path(__file__).parents[3] / "configs" / "csv_mappings" / "example_broker.toml"

HEADER = (
    "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
    "Controvalore;Divisa controvalore;Descrizione"
)
TOY_FILE = (
    "\n".join(
        [
            HEADER,
            "t5;31/03/2026;Vendita;IE0000000012;-50;54,00;EUR;;-10,00;;;;Vendita parziale",
            "t4;27/02/2026;Dividendo;IE0000000012;;;EUR;100,00;;;;;Cedola",
            "t3;30/01/2026;Bonifico in entrata;;;;EUR;5.000,00;;;;;",
            "t2;02/01/2026;Acquisto;IE0000000012;100;50,00;EUR;;-10,00;;;;",
            "t1;02/01/2026;Bonifico in entrata;;;;EUR;10.000,00;;;;;Primo versamento",
        ]
    )
    + "\n"
)


def _prov(content: bytes) -> Provenance:
    return Provenance(
        source="user",
        dataset="broker_export",
        url="file:movimenti.csv",
        retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="synthetic",
    )


def _parse(text: str = TOY_FILE, mapping: BrokerMapping | None = None):  # type: ignore[no-untyped-def]
    content = text.encode("utf-8")
    return parse_broker_csv(content, _prov(content), mapping or load_broker_mapping(MAPPING_FILE))


# --------------------------------------------------------------------------- toy reconciliation
def test_imported_toy_replays_to_hand_values() -> None:
    result = _parse()
    # newest-first file reversed as a whole: chronological order, also within a day
    assert [t.id for t in result.transactions] == ["t1", "t2", "t3", "t4", "t5"]
    history = replay(result.transactions, base=EUR, to_base=eur_only)
    final = history.state_on(date(2026, 3, 31))
    assert final.cash[("conto-principale", EUR)] == Decimal(12780)
    (gain,) = history.realised
    assert gain.gain_base == Decimal("185.00")


def test_reversal_is_noted() -> None:
    assert any("reversed" in note for note in _parse().notes)


def test_fields_are_parsed_exactly() -> None:
    sale = _parse().transactions[-1]
    assert sale.kind is K.SELL
    assert sale.isin == X
    assert sale.quantity == Decimal(50)  # signed -50 in the file
    assert sale.price is not None
    assert sale.price.amount == Decimal("54.00")
    assert sale.fees.amount == Decimal("10.00")
    assert sale.fees.currency == EUR
    assert sale.taxes.amount == 0  # implicit zero ...
    assert sale.taxes.currency == EUR  # ... in the declared currency
    assert sale.account == "conto-principale"
    assert sale.note == "Vendita parziale"


def test_notes_record_transformations() -> None:
    notes = " ".join(_parse().notes)
    assert "newest first" in notes
    assert "signed" in notes


def test_fx_conversion_row() -> None:
    text = HEADER + "\nf1;02/01/2026;Cambio valuta;;;;EUR;-4.000,00;-2,00;;5.000,00;USD;\n"
    (conversion,) = _parse(text).transactions
    assert conversion.kind is K.FX_CONVERSION
    assert conversion.amount is not None
    assert conversion.amount.amount == Decimal(4000)
    assert conversion.fx_counter is not None
    assert conversion.fx_counter.currency == Currency("USD")
    assert conversion.fx_counter.amount == Decimal(5000)


# --------------------------------------------------------------------------- strictness
@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("Vendita;IE", "Vendita titoli;IE", "unknown"),
        ("-50;54,00", "50;54,00", "sign"),  # signed file: a sale must have negative quantity
        ("EUR;100,00;", "EUR;-100,00;", "sign"),  # a dividend must be positive
        ("31/03/2026", "2026-03-31", "date"),
        ("54,00", "54.00", "number"),  # "." is the thousands separator: bad grouping
        ("t4;27/02/2026", "t5;27/02/2026", "duplicated"),
        ("t3;30/01/2026", "t3;15/03/2026", "descending"),
        ("IE0000000012;-50", "IE0000000013;-50", "ISIN"),
        (";EUR;100,00;", ";;100,00;", "currency"),
        ("Bonifico in entrata;;;;EUR;5.000,00", "Bonifico in entrata;;;;EUR;", "amount"),
    ],
)
def test_strictness(old: str, new: str, match: str) -> None:
    assert old in TOY_FILE
    with pytest.raises(ValidationError, match=match):
        _parse(TOY_FILE.replace(old, new, 1))


def test_wrong_field_count_and_missing_header_column() -> None:
    with pytest.raises(ParseError, match="fields"):
        _parse(TOY_FILE.replace("Primo versamento", "Primo;versamento"))
    with pytest.raises(ParseError, match="Riferimento"):
        _parse(TOY_FILE.replace("Riferimento", "Rif", 1))


def test_absolute_amounts_mode() -> None:
    mapping = replace(
        load_broker_mapping(MAPPING_FILE), amount_sign="absolute", date_order="ascending"
    )
    text = HEADER + "\nw1;02/01/2026;Bonifico in uscita;;;;EUR;250,00;;;;;\n"
    (withdrawal,) = _parse(text, mapping).transactions
    assert withdrawal.kind is K.WITHDRAWAL
    assert withdrawal.amount is not None
    assert withdrawal.amount.amount == Decimal(250)
    with pytest.raises(ParseError, match="negative"):
        _parse(text.replace("250,00", "-250,00"), mapping)


def test_ascending_order_is_checked() -> None:
    mapping = replace(load_broker_mapping(MAPPING_FILE), date_order="ascending")
    with pytest.raises(ParseError, match="ascending"):
        _parse(TOY_FILE, mapping)


def test_empty_file_and_undecodable_bytes() -> None:
    with pytest.raises(ParseError, match="no transactions"):
        _parse(HEADER + "\n")
    content = TOY_FILE.encode("utf-8") + b"\xff"
    with pytest.raises(ParseError, match="decode"):
        parse_broker_csv(content, _prov(content), load_broker_mapping(MAPPING_FILE))


# --------------------------------------------------------------------------- mapping
def test_example_mapping_loads() -> None:
    mapping = load_broker_mapping(MAPPING_FILE)
    assert mapping.kinds["Acquisto"] is K.BUY
    assert mapping.columns["account"] == "=conto-principale"
    assert mapping.zero_charge_currency == EUR


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"date_order": "random"}, "date_order"),
        ({"amount_sign": "maybe"}, "amount_sign"),
        ({"columns": {"id": "A", "trade_date": "B", "kind": "C"}}, "account"),
        (
            {
                "columns": {
                    "id": "A",
                    "trade_date": "B",
                    "kind": "C",
                    "account": "=x",
                    "colour": "D",
                }
            },
            "colour",
        ),
        ({"kinds": {}}, "kinds"),
        ({"delimiter": ","}, "decimal separator"),
        ({"date_format": "%d/%m"}, "date_format"),
        ({"encoding": "nope"}, "encoding"),
        ({"delimiter": ":"}, "delimiter"),
        ({"decimal_separator": ";"}, "decimal_separator"),
        ({"thousands_separator": ","}, "differ"),
    ],
)
def test_mapping_validation(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        replace(load_broker_mapping(MAPPING_FILE), **changes)  # type: ignore[arg-type]


def test_mapping_file_strictness(tmp_path: Path) -> None:
    text = MAPPING_FILE.read_text(encoding="utf-8")
    for old, new, match in [
        ('"Acquisto" = "buy"', '"Acquisto" = "purchase"', "Acquisto"),
        ('encoding = "utf-8"', 'encoding = "utf-8"\nextra = 1', "unexpected"),
    ]:
        path = tmp_path / "mapping.toml"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        with pytest.raises(ValidationError, match=match):
            load_broker_mapping(path)


def test_header_only_without_rows_and_blank_file() -> None:
    with pytest.raises(ParseError, match="no header"):
        _parse("\n\n")


def test_minimal_mapping_without_optional_columns() -> None:
    mapping = replace(
        load_broker_mapping(MAPPING_FILE),
        date_order="ascending",
        columns={
            "id": "Riferimento",
            "trade_date": "Data",
            "kind": "Operazione",
            "account": "=main",
            "amount": "Importo",
            "amount_currency": "Divisa",
        },
    )
    row = "d1;02/01/2026;Bonifico in entrata;;;;EUR;100,00;;;;;"
    (deposit,) = _parse(f"{HEADER}\n{row}\n", mapping).transactions
    assert deposit.note == ""
    assert deposit.isin is None


def test_no_ignored_columns_note_when_all_are_used() -> None:
    mapping = replace(
        load_broker_mapping(MAPPING_FILE),
        date_order="ascending",
        columns={
            "id": "A",
            "trade_date": "B",
            "kind": "C",
            "account": "=main",
            "amount": "D",
            "amount_currency": "=EUR",
        },
    )
    result = _parse("A;B;C;D\nd1;02/01/2026;Bonifico in entrata;100\n", mapping)
    assert not any("Ignored" in note for note in result.notes)
