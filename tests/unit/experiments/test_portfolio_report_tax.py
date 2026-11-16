"""The Italian tax position in the ``portfolio_report`` kind (design 8.6a), by hand.

On 3 March 2025, in an amministrato account: ETF X (10 units bought at 100) is sold at 200, a
gain of 1,000 taxed as capital income, 260, which the broker withheld; ETF Z (10 at 100) is sold
at 70, a loss of 300 that joins the losses balance until 31 December 2029.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS

ROOT = Path(__file__).parents[3]
X, Z = "IE0000000012", "IE0000000020"
INSTRUMENT = """\
[{isin}]
name = "Fund {isin}"
instrument_type = "etf"
asset_class = "equity"
currency = "EUR"
as_of = 2025-01-02
domicile = "IE"
replication = "physical_sampling"
distribution = "accumulating"
ter = "0.0020"
benchmark = "Example Index"
hedged_to = "none"
inception = "unknown"
fund_size = "unknown"
source = "synthetic example"
"""
MAPPING = """\
file_format = "csv"
skip_rows = 0
value_affixes = []
missing_tokens = []
date_column = "Data"
date_format = "%d/%m/%Y"
delimiter = ";"
decimal_separator = ","
thousands_separator = "."
encoding = "utf-8"
currency = "EUR"
frequency = "monthly"

[columns."IE0000000012"]
instrument = "IE0000000012"
price_type = "nav"

[columns."IE0000000020"]
instrument = "IE0000000020"
price_type = "nav"
"""
TAX = """
[parameters.tax]
country = "it"
regime = "{regime}"
public_share = {{ {shares} }}
"""


def _setup(tmp: Path, *, tax: str, withheld: str = "-260,00") -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "export.csv").write_text(
        "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
        "Controvalore;Divisa controvalore;Descrizione\n"
        "t5;03/03/2025;Vendita;IE0000000020;-10;70,00;EUR;;;;;;\n"
        f"t4;03/03/2025;Vendita;IE0000000012;-10;200,00;EUR;;;{withheld};;;\n"
        "t3;02/01/2025;Acquisto;IE0000000020;10;100,00;EUR;;;;;;\n"
        "t2;02/01/2025;Acquisto;IE0000000012;10;100,00;EUR;;;;;;\n"
        "t1;02/01/2025;Bonifico in entrata;;;;EUR;2.000,00;;;;;\n",
        encoding="utf-8",
    )
    (tmp / "prices.csv").write_text(
        "Data;IE0000000012;IE0000000020\n02/01/2025;100,00;100,00\n31/01/2025;150,00;90,00\n"
        "28/02/2025;200,00;70,00\n31/03/2025;200,00;70,00\n",
        encoding="utf-8",
    )
    (tmp / "mapping.toml").write_text(MAPPING, encoding="utf-8")
    (tmp / "instruments.toml").write_text(
        INSTRUMENT.format(isin=X) + "\n" + INSTRUMENT.format(isin=Z), encoding="utf-8"
    )
    broker = (ROOT / "configs/csv_mappings/example_broker.toml").as_posix()
    config = tmp / "report.toml"
    config.write_text(
        '[experiment]\nname = "tax-report"\nkind = "portfolio_report"\n'
        'hypothesis = "descriptive"\n\n[inputs]\n'
        f'transactions = "{(tmp / "export.csv").as_posix()}"\ntransactions_mapping = "{broker}"\n'
        f'prices = "{(tmp / "prices.csv").as_posix()}"\n'
        f'prices_mapping = "{(tmp / "mapping.toml").as_posix()}"\n'
        f'instruments = "{(tmp / "instruments.toml").as_posix()}"\n'
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"\n'
        '\n[parameters]\ntransactions_format = "mapped"\n'
        'title = "Tax test"\nbase_currency = "EUR"\nlanguage = "it"\n'
        'flow_timing = "start"\nmax_price_age_days = 3\nreturn_frequency = "none"\n'
        "generated_at = 2025-04-01T09:00:00Z\ntarget_weights = {}\n"
        + tax
        + f'\n[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


SHARES = f'"{X}" = 0, "{Z}" = 0'


def _run(config: Path) -> tuple[dict[str, object], Path]:
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    return dict(result.record), result.output_dir


def test_tax_position_by_hand(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, tax=TAX.format(regime="amministrato", shares=SHARES)))
    assert record["status"] == "success", record["error"]
    scalars = record["scalars"]
    assert scalars["tax_due"]["value"] == 260.0  # type: ignore[index]
    assert scalars["tax_withheld"]["value"] == 260.0  # type: ignore[index]
    assert scalars["losses_remaining"]["value"] == 300.0  # type: ignore[index]
    events = pd.read_csv(out / "tax_events.csv")
    assert events["category"].tolist() == ["redditi_di_capitale", "redditi_diversi"]
    assert events["result"].tolist() == pytest.approx([1000.0, -300.0])
    assert events["difference"].tolist() == pytest.approx([0.0, 0.0])
    losses = pd.read_csv(out / "losses_balance.csv")
    assert losses.loc[0, "usable_until"] == "2029-12-31"
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Posizione fiscale (analisi, non consulenza fiscale)" in html
    assert "Zainetto fiscale per anno" in html
    assert "D.Lgs. 117/2026" in html


def test_a_wrong_withholding_shows_in_the_report(tmp_path: Path) -> None:
    config = _setup(
        tmp_path, tax=TAX.format(regime="amministrato", shares=SHARES), withheld="-200,00"
    )
    record, out = _run(config)
    events = pd.read_csv(out / "tax_events.csv")
    assert events["difference"].tolist() == pytest.approx([-60.0, 0.0])
    assert record["scalars"]["tax_withheld"]["value"] == 200.0  # type: ignore[index]


def test_a_missing_public_share_fails_the_run(tmp_path: Path) -> None:
    record, _ = _run(_setup(tmp_path, tax=TAX.format(regime="amministrato", shares=f'"{X}" = 0')))
    assert record["status"] == "failure"
    assert "public-bond share" in str(record["error"])


@pytest.mark.parametrize(
    ("tax", "match"),
    [
        (TAX.format(regime="forfettario", shares=SHARES), "regime"),
        (TAX.format(regime="amministrato", shares=f'"{X}" = 1.5'), r"\[0, 1\]"),
        (
            '\n[parameters.tax]\ncountry = "it"\nregime = "amministrato"\npublic_share = 3\n',
            "table",
        ),
        ('\n[parameters.tax]\ncountry = "it"\nregime = "amministrato"\n', "public_share"),
        (
            '\n[parameters.tax]\nregime = "amministrato"\npublic_share = {}\n',
            "needs country, one of \\['ch', 'custom', 'it'\\]",
        ),
        (
            '\n[parameters.tax]\ncountry = "fr"\nregime = "amministrato"\npublic_share = {}\n',
            "country must be one of \\['ch', 'custom', 'it'\\], got 'fr'",
        ),
        (
            '\n[parameters.tax]\ncountry = "it"\nregime = "amministrato"\npublic_share = {}\n'
            "rate = 1\n",
            "unknown keys \\['rate'\\]",
        ),
        ("\ntax = 3\n", "tax must be a table"),
    ],
)
def test_tax_parameters_are_validated(tmp_path: Path, tax: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_setup(tmp_path, tax=tax), kinds=KINDS)


def test_without_tax_nothing_changes(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, tax=""))
    assert record["status"] == "success", record["error"]
    assert not (out / "tax_events.csv").exists()
    assert "Posizione fiscale" not in (out / "report.html").read_text(encoding="utf-8")


# ---------------------------------------------------------- stamp duty and IVAFE (design 11.3)
# 20 units of ETF X bought at 100 on 2 January 2025 and held: €2,000 on 31 December. The
# account opened on 2 January, so 364 days of 2025: stamp duty 0.002 x 2,000 x 364/365 = 3.989
# -> €4.00 (yearly statements, rounded to 10 cents); IVAFE 3.989 -> €3.99, not payable (<= 12).
MONTH_ENDS_2025 = ("31/01/2025", "28/02/2025", "31/03/2025", "30/04/2025", "30/05/2025",
                   "30/06/2025", "31/07/2025", "29/08/2025", "30/09/2025", "31/10/2025",
                   "28/11/2025", "31/12/2025")  # fmt: skip


def _held(tmp: Path, custody: str) -> Path:
    config = _setup(tmp, tax=TAX.format(regime="amministrato", shares=SHARES) + custody)
    (tmp / "export.csv").write_text(
        "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
        "Controvalore;Divisa controvalore;Descrizione\n"
        "t2;02/01/2025;Acquisto;IE0000000012;20;100,00;EUR;;;;;;\n"
        "t1;02/01/2025;Bonifico in entrata;;;;EUR;2.000,00;;;;;\n",
        encoding="utf-8",
    )
    rows = "".join(f"{d};100,00;100,00\n" for d in ("02/01/2025", *MONTH_ENDS_2025))
    (tmp / "prices.csv").write_text(f"Data;{X};{Z}\n{rows}", encoding="utf-8")
    return config


ITALY_CUSTODY = (
    '\n[parameters.tax.custody."conto-principale"]\nwhere = "italy"\nstatements = "year"\n'
)
ABROAD_CUSTODY = '\n[parameters.tax.custody."conto-principale"]\nwhere = "abroad"\nshare = 1.0\n'


def test_stamp_duty_by_hand(tmp_path: Path) -> None:
    record, out = _run(_held(tmp_path, ITALY_CUSTODY))
    assert record["status"] == "success", record["error"]
    items = pd.read_csv(out / "wealth_tax_items.csv")
    assert items["tax"].tolist() == ["stamp_duty"]
    assert items["days"].tolist() == [364]
    assert items["amount"].tolist() == pytest.approx([4.0])
    years = pd.read_csv(out / "wealth_tax_years.csv")
    assert years["stamp_duty"].tolist() == pytest.approx([4.0])
    assert record["scalars"]["stamp_duty_last_year"]["value"] == 4.0  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Imposta di bollo e IVAFE per anno" in html
    assert "D.L. 201/2011, art. 19" in html


def test_ivafe_by_hand_in_english(tmp_path: Path) -> None:
    config = _held(tmp_path, ABROAD_CUSTODY)
    config.write_text(
        config.read_text(encoding="utf-8").replace('language = "it"', 'language = "en"'),
        encoding="utf-8",
    )
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    items = pd.read_csv(out / "wealth_tax_items.csv")
    assert items["holding"].tolist() == [X]
    assert items["amount"].tolist() == pytest.approx([3.99])
    years = pd.read_csv(out / "wealth_tax_years.csv")
    assert years["ivafe_payable"].tolist() == pytest.approx([0.0])  # 3.99 is not above 12
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Stamp duty by statement and IVAFE by holding" in html
    assert "total is 12 euro or less." in html  # the apostrophe is escaped in HTML


@pytest.mark.parametrize(
    ("custody", "match"),
    [
        ('\n[parameters.tax.custody."other"]\nwhere = "italy"\nstatements = "year"\n',
         r"accounts are held: \['conto-principale'\]"),
        ('\n[parameters.tax.custody."conto-principale"]\nwhere = "abroad"\n',
         r"missing \['share'\]"),
    ],
)  # fmt: skip
def test_custody_errors(tmp_path: Path, custody: str, match: str) -> None:
    config = _held(tmp_path, custody)
    try:
        validate_experiment(config, kinds=KINDS)
    except ValidationError as error:
        message = str(error)
    else:
        record, _ = _run(config)
        assert record["status"] == "failure"
        message = str(record["error"])
    assert re.search(match, message), message


def test_without_custody_the_section_is_as_before(tmp_path: Path) -> None:
    record, out = _run(_held(tmp_path, ""))
    assert record["status"] == "success", record["error"]
    assert not (out / "wealth_tax_items.csv").exists()
    assert "stamp_duty_last_year" not in record["scalars"]  # type: ignore[operator]
    assert "IVAFE" not in (out / "report.html").read_text(encoding="utf-8")
