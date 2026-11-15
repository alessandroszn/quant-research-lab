"""The native transactions file in the ``portfolio_report`` kind (design 8.8a), by hand.

A starting position on 2 January 2026: 1,000 EUR of cash and 100 units of X at a market price
of 50, with an original cost of 40. On 30 January X is at 55 and 50 units are sold at 55:

- realised 2,750 - 2,000 = 750, taxed as capital income at 26 %: 195;
- unrealised 50 x (55 - 40) = 750; the gain carried in, 1,000, is shown apart;
- profit and loss 6,500 - 6,000 = 500 = 750 + 750 - 1,000, with a zero residual.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.data.provenance import Provenance
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.portfolio_report import DECLARED_COST
from qrlab.portfolio import load_broker_mapping, parse_broker_csv, write_native_csv
from qrlab.portfolio.transactions import TransactionKind
from support.portfolio import D0, D1, X, money, tx

ROOT = Path(__file__).parents[3]
FULL = ROOT / "configs/experiments/example_portfolio_report_full.toml"
K = TransactionKind


def _absolute(text: str, out: Path) -> str:
    """Make the example config's relative paths absolute and send its outputs to ``out``."""
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    return text[:start] + f'directory = "{out.as_posix()}"' + text[end + 1 :]


def _native_full(tmp: Path) -> Path:
    """Write the full example with its broker export converted to a native file."""
    mapped = FULL.read_text(encoding="utf-8")
    export = ROOT / "examples/data/broker_export_full.csv"
    imported = parse_broker_csv(
        export.read_bytes(),
        _provenance(),
        load_broker_mapping(ROOT / "configs/csv_mappings/example_broker.toml"),
    )
    native = tmp / "transactions.csv"
    native.write_bytes(write_native_csv(imported.transactions))
    lines = [
        line
        for line in mapped.splitlines()
        if not line.startswith(("transactions_mapping", "transactions ="))
    ]
    text = "\n".join(lines) + "\n"
    text = text.replace("[inputs]\n", f'[inputs]\ntransactions = "{native.as_posix()}"\n', 1)
    text = text.replace('transactions_format = "mapped"', 'transactions_format = "native"')
    config = tmp / "native.toml"
    config.write_text(_absolute(text, tmp / "native-out"), encoding="utf-8")
    return config


def _provenance() -> Provenance:
    return Provenance(
        source="test",
        dataset="transactions",
        url="file:broker_export_full.csv",
        retrieved_at=datetime(2026, 4, 1, tzinfo=UTC),
        sha256="0" * 64,
        size_bytes=0,
        terms="synthetic",
    )


def test_the_native_file_gives_the_same_report_as_the_mapped_export(tmp_path: Path) -> None:
    mapped = tmp_path / "mapped.toml"
    mapped.write_text(
        _absolute(FULL.read_text(encoding="utf-8"), tmp_path / "mapped-out"), encoding="utf-8"
    )
    a = run_experiment(mapped, kinds=KINDS, overwrite=False)
    b = run_experiment(_native_full(tmp_path), kinds=KINDS, overwrite=False)
    assert a.succeeded, a.record.get("error")
    assert b.succeeded, b.record.get("error")
    csvs = sorted(p.name for p in a.output_dir.glob("*.csv"))
    assert csvs == sorted(p.name for p in b.output_dir.glob("*.csv"))
    assert csvs == ["check_findings.csv", "exposures.csv"]
    for name in csvs:
        assert (a.output_dir / name).read_bytes() == (b.output_dir / name).read_bytes(), name
    assert a.record["scalars"] == b.record["scalars"]
    assert a.record["notice"] == b.record["notice"]


def _config(tmp: Path, parameters: str, mapping: bool) -> Path:
    text = _absolute(FULL.read_text(encoding="utf-8"), tmp / "out")
    text = text.replace('transactions_format = "mapped"\n', parameters)
    if not mapping:
        text = "\n".join(
            line for line in text.splitlines() if not line.startswith("transactions_mapping")
        )
    config = tmp / "config.toml"
    config.write_text(text, encoding="utf-8")
    return config


@pytest.mark.parametrize(
    ("parameters", "mapping", "match"),
    [
        ("", True, 'transactions_format is required: "mapped" for a broker export'),
        ('transactions_format = "csv"\n', True, "transactions_format"),
        ('transactions_format = "native"\n', True, "takes no transactions_mapping"),
        ('transactions_format = "mapped"\n', False, "needs a transactions_mapping"),
    ],
)
def test_the_format_is_explicit(tmp_path: Path, parameters: str, mapping: bool, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_config(tmp_path, parameters, mapping), kinds=KINDS)


PRICES_MAPPING = """\
file_format = "csv"
skip_rows = 0
value_affixes = []
date_column = "date"
date_format = "%Y-%m-%d"
delimiter = ","
decimal_separator = "."
thousands_separator = ""
encoding = "utf-8"
currency = "EUR"
frequency = "monthly"

[columns."IE0000000012"]
instrument = "IE0000000012"
price_type = "nav"
"""


def test_a_starting_position_by_hand(tmp_path: Path) -> None:
    transactions = [
        tx("d", D0, K.DEPOSIT, amount=money(1000)),
        tx("i", D0, K.TRANSFER_IN, isin=X, quantity="100", price=money(50), cost=money(40)),
        tx("s", D1, K.SELL, isin=X, quantity="50", price=money(55)),
    ]
    (tmp_path / "transactions.csv").write_bytes(write_native_csv(transactions))
    (tmp_path / "prices.csv").write_text(
        "date,IE0000000012\n2026-01-02,50\n2026-01-30,55\n", encoding="utf-8"
    )
    (tmp_path / "prices.toml").write_text(PRICES_MAPPING, encoding="utf-8")
    config = tmp_path / "start.toml"
    config.write_text(
        '[experiment]\nname = "start"\nkind = "portfolio_report"\nhypothesis = "descriptive"\n'
        "\n[inputs]\n"
        f'transactions = "{(tmp_path / "transactions.csv").as_posix()}"\n'
        f'prices = "{(tmp_path / "prices.csv").as_posix()}"\n'
        f'prices_mapping = "{(tmp_path / "prices.toml").as_posix()}"\n'
        f'instruments = "{(ROOT / "examples/data/instruments.toml").as_posix()}"\n'
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"\n'
        '\n[parameters]\ntransactions_format = "native"\ntitle = "Start"\n'
        'base_currency = "EUR"\nlanguage = "it"\nflow_timing = "start"\n'
        'max_price_age_days = 0\nreturn_frequency = "none"\n'
        "generated_at = 2026-02-01T09:00:00Z\ntarget_weights = {}\n"
        '\n[parameters.tax]\nregime = "amministrato"\npublic_share = { IE0000000012 = 0 }\n'
        f'\n[output]\ndirectory = "{(tmp_path / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record.get("error")
    assert result.record["scalars"]["tax_due"]["value"] == 195.0
    assert DECLARED_COST in str(result.record["notice"])
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert "Plusvalenze portate da trasferimenti" in html
    assert "-1.000,00" in html
    assert "Il residuo del risultato" not in html  # the P&L reconciles: no residual warning
    record = json.loads((result.output_dir / "record.json").read_text(encoding="utf-8"))
    assert record["status"] == "success"
