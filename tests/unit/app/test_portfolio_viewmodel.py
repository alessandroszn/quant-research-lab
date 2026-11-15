"""The Portfolio screen's view model, without Qt (design 8.8b), on the 8.8a hand example.

A starting position on 2 January 2026: 1,000 EUR deposited and 100 units of X at a market
price of 50 with an original cost of 40; on 30 January 50 units are sold at 55. The report
built from the saved files runs, and its notice says the cost was declared.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from qrlab.experiments import run_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.portfolio_report import DECLARED_COST
from qrlab.portfolio import NATIVE_COLUMNS
from qrlab_app.portfolio import INSTRUMENTS_FILE, TRANSACTIONS_FILE, PortfolioViewModel, Problem
from qrlab_app.viewmodels import AppError, DataViewModel, WorkspaceViewModel

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
X = "IE0000000012"
INSTRUMENT = {
    "isin": X,
    "name": "Example World Equity UCITS ETF",
    "instrument_type": "etf",
    "asset_class": "equity",
    "currency": "EUR",
    "as_of": "2026-01-02",
    "replication": "physical_sampling",
    "distribution": "accumulating",
    "ter": "0.0020",
    "source": "synthetic example",
}


def _model(tmp: Path) -> PortfolioViewModel:
    ws = WorkspaceViewModel()
    ws.create(tmp / "ws")
    return PortfolioViewModel(ws, kinds=KINDS, now=lambda: NOW)


def _filled(tmp: Path) -> PortfolioViewModel:
    model = _model(tmp)
    model.create("mine")
    row = model.add_instrument()
    for name, text in INSTRUMENT.items():
        model.set_instrument(row, name, text)
    model.add_starting_position("2026-01-02")
    deposit, transfer = 0, 1
    model.set_transaction(deposit, "amount", "1000")
    for name, text in {"quantity": "100", "price": "50", "cost": "40"}.items():
        model.set_transaction(transfer, name, text)
    sale = model.add_transaction("sell")
    for name, text in {
        "trade_date": "2026-01-30",
        "isin": X,
        "quantity": "50",
        "price": "55",
        "price_currency": "EUR",
    }.items():
        model.set_transaction(sale, name, text)
    return model


def test_a_new_portfolio_is_an_empty_folder(tmp_path: Path) -> None:
    model = _model(tmp_path)
    assert model.refresh() == []
    assert model.create(" mine ") == "mine"
    assert model.names == ["mine"]
    assert model.selected == "mine"
    assert (model.workspace.require() / "portfolios" / "mine").is_dir()
    assert (model.transactions, model.instruments, model.dirty) == ([], [], False)
    with pytest.raises(AppError, match="already exists"):
        model.create("mine")
    with pytest.raises(AppError, match="not a valid file name"):
        model.create("a/b")


def test_the_starting_position_rows(tmp_path: Path) -> None:
    model = _filled(tmp_path)
    ids = [r["id"] for r in model.transactions]
    kinds = [r["kind"] for r in model.transactions]
    assert (ids, kinds) == (["t1", "t2", "t3"], ["deposit", "transfer_in", "sell"])
    transfer = model.transactions[1]
    assert (transfer["trade_date"], transfer["isin"], transfer["cost_currency"]) == (
        "2026-01-02",
        X,
        "EUR",
    )
    assert (transfer["fees"], transfer["fees_currency"]) == ("0", "EUR")
    assert model.editable(1, "cost")
    assert not model.editable(1, "amount")
    assert not model.editable(0, "isin")
    assert model.editable(0, "amount_currency")
    assert model.dirty


def test_a_new_kind_empties_the_cells_it_does_not_use(tmp_path: Path) -> None:
    model = _filled(tmp_path)
    model.set_transaction(1, "kind", "buy")
    assert model.transactions[1]["cost"] == ""
    assert model.transactions[1]["quantity"] == "100"
    model.set_transaction(1, "kind", "nonsense")
    assert model.editable(1, "kind")
    assert not model.editable(1, "quantity")


def test_save_writes_both_files_and_the_report_runs(tmp_path: Path) -> None:
    model = _filled(tmp_path)
    assert model.save() is None
    assert not model.dirty
    folder = model.workspace.require() / "portfolios" / "mine"
    header = (folder / TRANSACTIONS_FILE).read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(NATIVE_COLUMNS)
    assert (folder / INSTRUMENTS_FILE).read_text(encoding="utf-8").startswith(f"[{X}]\n")
    config = model.create_report("mine-report")
    text = config.read_text(encoding="utf-8")
    assert 'transactions = "../portfolios/mine/transactions.csv"' in text
    assert 'transactions_format = "native"' in text
    with pytest.raises(AppError, match="already exists"):
        model.create_report("mine-report")

    # What the user fills in on the report screen: prices, their mapping, checks, parameters.
    data = model.workspace.require() / "data"
    (data / "prices.csv").write_text(
        "date,IE0000000012\n2026-01-02,50\n2026-01-30,55\n", encoding="utf-8"
    )
    (data / "prices.toml").write_text(
        'date_column = "date"\ndate_format = "%Y-%m-%d"\ndelimiter = ","\n'
        'decimal_separator = "."\nthousands_separator = ""\nencoding = "utf-8"\n'
        'currency = "EUR"\nfrequency = "monthly"\n\n[columns."IE0000000012"]\n'
        'instrument = "IE0000000012"\nprice_type = "nav"\n',
        encoding="utf-8",
    )
    checks = (ROOT / "configs/checks/example.toml").as_posix()
    filled = {
        'prices = "../data/FILL-IN"': 'prices = "../data/prices.csv"',
        'prices_mapping = "../data/FILL-IN"': 'prices_mapping = "../data/prices.toml"',
        'checks = "../data/FILL-IN"': f'checks = "{checks}"',
        "# title = FILL-IN": 'title = "Mine"',
        "# base_currency = FILL-IN": 'base_currency = "EUR"',
        "# language = FILL-IN": 'language = "it"',
        "# flow_timing = FILL-IN": 'flow_timing = "start"',
        "# max_price_age_days = FILL-IN": "max_price_age_days = 0",
        "# return_frequency = FILL-IN": 'return_frequency = "none"',
        "# generated_at = FILL-IN": "generated_at = 2026-02-01T09:00:00Z",
        "# target_weights = FILL-IN": "target_weights = {}",
    }
    for old, new in filled.items():
        assert old in text, old
        text = text.replace(old, new)
    config.write_text(text, encoding="utf-8")
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record.get("error")
    assert DECLARED_COST in str(result.record["notice"])


def test_saved_rows_come_back_sorted(tmp_path: Path) -> None:
    model = _filled(tmp_path)
    late = model.add_transaction("deposit")
    for name, text in {"trade_date": "2026-01-10", "amount": "5", "amount_currency": "EUR"}.items():
        model.set_transaction(late, name, text)
    assert model.save() is None
    assert [r["id"] for r in model.transactions] == ["t1", "t2", "t4", "t3"]
    model.select("mine")
    assert [r["trade_date"] for r in model.transactions] == [
        "2026-01-02",
        "2026-01-02",
        "2026-01-10",
        "2026-01-30",
    ]


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (lambda m: m.set_instrument(0, "isin", "IE0000000013"), ("instruments", 0, "library")),
        (
            lambda m: (
                m.add_instrument(),
                [m.set_instrument(1, k, v) for k, v in INSTRUMENT.items()],
            ),
            ("instruments", 1, "duplicate_isin"),
        ),
        (lambda m: m.transactions.clear(), ("transactions", None, "no_transactions")),
        (lambda m: m.set_transaction(2, "quantity", ""), ("transactions", 2, "library")),
        (
            lambda m: m.set_transaction(2, "isin", "US0000000044"),
            ("transactions", 2, "unknown_isin"),
        ),
        (lambda m: m.set_transaction(2, "quantity", "500"), ("transactions", 2, "library")),
        (
            lambda m: m.set_transaction(2, "trade_date", "2026-01-01"),
            ("transactions", 2, "library"),
        ),
        (
            lambda m: (
                m.set_transaction(0, "trade_date", "2026-01-31"),
                m.set_transaction(0, "amount", "abc"),
            ),
            ("transactions", 0, "library"),
        ),
    ],
)
def test_problems_point_at_the_row_and_nothing_is_written(
    tmp_path: Path, edit: object, expected: tuple[str, int | None, str]
) -> None:
    model = _filled(tmp_path)
    edit(model)  # type: ignore[operator]
    problem = model.save()
    assert isinstance(problem, Problem)
    assert (problem.table, problem.row, problem.key) == (
        expected[0],
        expected[1],
        f"portfolio.{expected[2]}",
    )
    folder = model.workspace.require() / "portfolios" / "mine"
    assert not (folder / TRANSACTIONS_FILE).exists()
    assert model.dirty
    with pytest.raises(AppError, match="Validate and save the portfolio first"):
        model.create_report("r")


def test_the_library_message_is_kept(tmp_path: Path) -> None:
    model = _filled(tmp_path)
    model.set_transaction(2, "quantity", "500")
    problem = model.check()
    assert problem is not None
    assert problem.values == {"error": "t3: cannot remove 500 units, more than 100 held"}


def test_revert_unreadable_files_and_guards(tmp_path: Path) -> None:
    model = _filled(tmp_path)
    assert model.save() is None
    model.set_transaction(0, "amount", "2000")
    assert model.dirty
    model.revert()
    assert (model.dirty,) == (False,)  # a tuple: mypy keeps the property unnarrowed
    assert model.transactions[0]["amount"] == "1000"
    folder = model.workspace.require() / "portfolios" / "mine"
    (folder / TRANSACTIONS_FILE).write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(AppError, match="Cannot read mine: the header must be exactly"):
        model.select("mine")
    model.clear()
    assert (model.selected, model.names, model.dirty) == (None, [], False)
    with pytest.raises(AppError, match="No portfolio is selected"):
        model.add_transaction("deposit")
    model.create("other")
    with pytest.raises(AppError, match="Add the instruments first"):
        model.add_starting_position("2026-01-02")
    with pytest.raises(AppError, match="is not a date"):
        model.add_starting_position("02/01/2026")
    model.add_instrument()
    model.remove_instrument(0)
    model.add_transaction("deposit")
    model.remove_transaction(0)
    assert (model.transactions, model.instruments) == ([], [])
    for _ in range(3):
        model.add_transaction("deposit")
    model.remove_transaction(0)  # t2 and t3 are left: the next free id is t4
    assert model.transactions[model.add_transaction("deposit")]["id"] == "t4"


def test_a_file_downloaded_by_hand_is_imported_unchanged(tmp_path: Path) -> None:
    ws = WorkspaceViewModel()
    ws.create(tmp_path / "ws")
    data = DataViewModel(ws, now=lambda: NOW)
    download = tmp_path / "IWDA_holdings.csv"
    download.write_bytes(b"Ticker,Name\nAAPL,APPLE\n")
    stored = data.import_file(download, "holdings-world")
    assert stored.read_bytes() == download.read_bytes()
    (entry,) = data.files
    assert (entry.source, entry.dataset, entry.url) == (
        "user",
        "holdings-world",
        "file:IWDA_holdings.csv",
    )
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    with pytest.raises(AppError, match="Cannot import empty"):
        data.import_file(empty, "holdings-world")
    with pytest.raises(AppError, match="not a valid file name"):
        data.import_file(download, "../up")


def test_a_cost_typed_after_saving_takes_the_price_currency(tmp_path: Path) -> None:
    """Regression (8.8b): a saved transfer without a cost comes back with no cost currency."""
    model = _filled(tmp_path)
    model.set_transaction(1, "cost", "")
    assert model.save() is None
    assert model.transactions[1]["kind"] == "transfer_in"
    assert model.transactions[1]["cost_currency"] == ""
    model.set_transaction(1, "cost", "40")
    assert model.transactions[1]["cost_currency"] == "EUR"
    assert model.save() is None
