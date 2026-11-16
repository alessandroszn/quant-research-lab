"""The configurable tax model in the ``portfolio_report`` kind (design 9.3), end to end.

The account of ``tests/unit/tax/test_custom.py`` (synthetic, EUR), written as a native
transactions file. The run writes the yearly table and the loss balance, the notice says the
model is yours, and the report labels the section in both languages.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from qrlab.experiments import run_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.instruments import instrument_from_fields, write_instruments_toml
from qrlab.portfolio import write_native_csv
from qrlab.tax.custom import NOTICE
from support.custom_account import TRANSACTIONS

ROOT = Path(__file__).parents[3]
FUND = {
    "name": "Example World Equity UCITS ETF",
    "instrument_type": "etf",
    "asset_class": "equity",
    "currency": "EUR",
    "as_of": "2025-01-02",
    "domicile": "IE",
    "replication": "unknown",
    "distribution": "accumulating",
    "ter": "unknown",
    "benchmark": "unknown",
    "hedged_to": "none",
    "inception": "unknown",
    "fund_size": "unknown",
    "source": "synthetic example",
}
DAYS = (
    "2025-01-02", "2025-06-02", "2025-12-31", "2026-01-05", "2026-02-01", "2026-02-15",
    "2026-03-01", "2026-12-31",
)  # fmt: skip
MAPPING = """\
file_format = "csv"
skip_rows = 0
value_affixes = []
missing_tokens = []
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

[columns."US0000000044"]
instrument = "US0000000044"
price_type = "nav"
"""
TAX = """
[parameters.tax]
country = "custom"
description = "Example country, my reading"
gains_rate = 0.20
income_rate = 0.25
losses = "netted"
loss_carry_years = 2
exempt_after_months = 12
gains_allowance = 1000
wealth_tax_rate = 0.0
"""


def _config(tmp: Path, language: str) -> Path:
    (tmp / "transactions.csv").write_bytes(write_native_csv(TRANSACTIONS))
    prices = {"2025-06-02": (80, 50), "2026-02-01": (150, 50), "2026-03-01": (150, 80)}
    rows = [f"{d},{prices.get(d, (100, 50))[0]},{prices.get(d, (100, 50))[1]}" for d in DAYS]
    (tmp / "prices.csv").write_text(
        "date,IE0000000012,US0000000044\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )
    (tmp / "prices.toml").write_text(MAPPING, encoding="utf-8")
    instruments = [
        instrument_from_fields(FUND | {"isin": "IE0000000012"}),
        instrument_from_fields(FUND | {"isin": "US0000000044", "name": "Example US Fund"}),
    ]
    (tmp / "instruments.toml").write_text(write_instruments_toml(instruments), encoding="utf-8")
    config = tmp / "custom.toml"
    config.write_text(
        '[experiment]\nname = "custom"\nkind = "portfolio_report"\nhypothesis = "descriptive"\n'
        "\n[inputs]\n"
        f'transactions = "{(tmp / "transactions.csv").as_posix()}"\n'
        f'prices = "{(tmp / "prices.csv").as_posix()}"\n'
        f'prices_mapping = "{(tmp / "prices.toml").as_posix()}"\n'
        f'instruments = "{(tmp / "instruments.toml").as_posix()}"\n'
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"\n'
        '\n[parameters]\ntransactions_format = "native"\ntitle = "Custom"\n'
        f'base_currency = "EUR"\nlanguage = "{language}"\nflow_timing = "start"\n'
        'max_price_age_days = 0\nreturn_frequency = "none"\n'
        "generated_at = 2027-01-15T09:00:00Z\ntarget_weights = {}\n"
        + TAX
        + f'\n[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


def test_the_custom_model_end_to_end(tmp_path: Path) -> None:
    result = run_experiment(_config(tmp_path, "it"), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record.get("error")
    scalars = {k: v["value"] for k, v in result.record["scalars"].items()}
    assert scalars["gains_tax_estimate"] == 200.0
    assert scalars["income_tax_estimate"] == 100.0
    assert NOTICE in str(result.record["notice"])
    years = pd.read_csv(result.output_dir / "custom_years.csv", index_col="year")
    assert years.loc[2026, "exempt"] == 2500.0
    losses = pd.read_csv(result.output_dir / "custom_losses.csv", index_col="year")
    assert losses.loc[2025, "used"] == 1000.0
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    for text in (
        "un modello semplificato che hai configurato, non la legge di un paese",
        "Modello: Example country, my reading.",
        "Franchigia annua sugli utili",
        "Esente per possesso",
        "almeno 12 mesi",
    ):
        assert text in html, text


def test_the_english_section(tmp_path: Path) -> None:
    result = run_experiment(_config(tmp_path, "en"), kinds=KINDS, overwrite=False)
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert "a simplified model you configured, not a country&#x27;s law" in html or (
        "a simplified model you configured, not a country's law" in html
    )
    assert "can be used in the 2 following year(s)" in html
