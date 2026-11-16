"""The Swiss tax section in the ``portfolio_report`` kind (design 9.2), end to end.

The account of ``tests/unit/tax/test_switzerland.py`` (synthetic, CHF), written as a native
transactions file, with prices on every flow date. The run writes the three Swiss tables and
the scalars, and the report shows the section in Italian.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.instruments import instrument_from_fields, write_instruments_toml
from qrlab.portfolio import write_native_csv
from support.swiss import TRANSACTIONS

ROOT = Path(__file__).parents[3]
FUND = {
    "name": "Example World Equity UCITS ETF",
    "instrument_type": "etf",
    "asset_class": "equity",
    "currency": "CHF",
    "as_of": "2025-12-01",
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
PRICES = """\
date,IE0000000012,CH0000000023
2025-12-01,100,100
2025-12-31,100,100
2026-02-01,100,100
2026-03-15,100,100
2026-06-01,100,130
2026-07-01,100,130
2026-09-01,100,130
2026-12-31,100,130
2027-02-01,110,130
2027-03-31,110,130
"""
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
currency = "CHF"
frequency = "monthly"

[columns."IE0000000012"]
instrument = "IE0000000012"
price_type = "nav"

[columns."CH0000000023"]
instrument = "CH0000000023"
price_type = "nav"
"""
TAX = """
[parameters.tax]
country = "ch"
marginal_rate = 0.30
wealth_tax_rate = 0.003
debt_financed = false
net_income = { 2026 = 80000, 2027 = 60000 }
reported_income = { IE0000000012 = [{ date = 2026-06-30, per_unit = "2.50", currency = "CHF" }] }
"""


def _config(tmp: Path, *, base: str = "CHF", tax: str = TAX, language: str = "it") -> Path:

    (tmp / "transactions.csv").write_bytes(write_native_csv(TRANSACTIONS))
    (tmp / "prices.csv").write_text(PRICES, encoding="utf-8")
    (tmp / "prices.toml").write_text(MAPPING, encoding="utf-8")
    instruments = [
        instrument_from_fields(FUND | {"isin": "IE0000000012"}),
        instrument_from_fields(
            FUND
            | {
                "isin": "CH0000000023",
                "name": "Example Swiss Fund",
                "domicile": "CH",
                "distribution": "distributing",
            }
        ),
    ]
    (tmp / "instruments.toml").write_text(write_instruments_toml(instruments), encoding="utf-8")
    config = tmp / "swiss.toml"
    config.write_text(
        '[experiment]\nname = "swiss"\nkind = "portfolio_report"\nhypothesis = "descriptive"\n'
        "\n[inputs]\n"
        f'transactions = "{(tmp / "transactions.csv").as_posix()}"\n'
        f'prices = "{(tmp / "prices.csv").as_posix()}"\n'
        f'prices_mapping = "{(tmp / "prices.toml").as_posix()}"\n'
        f'instruments = "{(tmp / "instruments.toml").as_posix()}"\n'
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"\n'
        '\n[parameters]\ntransactions_format = "native"\ntitle = "Swiss"\n'
        f'base_currency = "{base}"\nlanguage = "{language}"\nflow_timing = "start"\n'
        'max_price_age_days = 0\nreturn_frequency = "none"\n'
        "generated_at = 2027-04-01T09:00:00Z\ntarget_weights = {}\n"
        + tax
        + f'\n[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


def test_the_swiss_section_end_to_end(tmp_path: Path) -> None:
    result = run_experiment(_config(tmp_path), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record.get("error")
    scalars = {k: v["value"] for k, v in result.record["scalars"].items()}
    assert scalars["income_taxable"] == 2200.0
    assert scalars["income_tax_estimate"] == 660.0
    assert scalars["wealth"] == 245780.0
    assert scalars["safe_haven_met"] == 0.0
    years = pd.read_csv(result.output_dir / "ch_years.csv", index_col="year")
    assert years.loc[2026, "safe_haven"] == "not_excluded"
    assert years.loc[2027, "safe_haven"] == "met"
    assert years["wealth"].isna().tolist() == [False, False, True]
    income = pd.read_csv(result.output_dir / "ch_income.csv")
    assert income["kind"].tolist() == ["dividend", "reported_income"]
    criteria = pd.read_csv(result.output_dir / "ch_safe_haven.csv")
    assert len(criteria) == 15  # five criteria in each of the three years
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    for text in (
        "Circolare 36",
        "commercio professionale non escluso",
        "porto sicuro rispettato",
        "anno non concluso",
        "reddito del fondo (listino)",
        "2,50",
        "Aliquota marginale sul reddito",
        "LIFD (RS 642.11)",
        "2026-02-01 → 2026-06-01",
    ):
        assert text in html, text


def test_the_english_section(tmp_path: Path) -> None:
    result = run_experiment(_config(tmp_path, language="en"), kinds=KINDS, overwrite=False)
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    for text in ("professional trading not excluded", "year not ended", "LIFD/DBG (SR 642.11)"):
        assert text in html, text


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"tax": TAX.replace("marginal_rate = 0.30\n", "")}, "tax: missing \\['marginal_rate'\\]"),
        ({"tax": TAX.replace("debt_financed = false", "debt_financed = 0")}, "true or false"),
    ],
)
def test_swiss_keys_are_validated(tmp_path: Path, changes: dict[str, str], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_config(tmp_path, **changes), kinds=KINDS)


def test_a_base_currency_other_than_chf_is_refused_when_validating(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="needs base_currency = \"CHF\", not 'EUR'"):
        validate_experiment(_config(tmp_path, base="EUR"), kinds=KINDS)
