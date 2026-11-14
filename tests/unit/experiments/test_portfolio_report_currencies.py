"""Several currencies in the ``portfolio_report`` kind (design 7.4a), with hand-calculated values.

The synthetic portfolio, in a EUR base:

- deposit 2,000 EUR, change 1,000 EUR into 1,250 USD (at 1.25), buy 10 units of a USD fund at
  100 USD: 250 USD of cash remain;
- on every valuation date EUR/USD = 1.25 and the fund is at 100 USD.

By hand: the position is 10 x 100 / 1.25 = 800 EUR, the USD cash 250 / 1.25 = 200 EUR and the
EUR cash 1,000 EUR, so the portfolio is worth 2,000 EUR. In a GBP base, with EUR/GBP = 0.8, the
same holdings are worth 2,000 x 0.8 = 1,600 GBP (cross rate through EUR).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.workspace import config_template

ROOT = Path(__file__).parents[3]
USD_FUND = "US0000000119"  # made-up ISINs with valid check digits
EUR_FUND = "IE0000000012"
DATES = ("2026-02-27", "2026-01-30", "2026-01-02")  # newest first, as the ECB publishes

EXPORT = """\
Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;\
Controvalore;Divisa controvalore;Descrizione
{extra}t4;02/01/2026;Acquisto;US0000000119;10;100,00;USD;;;;;;
t3;02/01/2026;Cambio valuta;;;;EUR;-1.000,00;;;1.250,00;USD;
t2;02/01/2026;Bonifico in entrata;;;;EUR;{deposit};;;;;
"""
INSTRUMENT = """\
[{isin}]
name = "Example {currency} fund"
instrument_type = "etf"
asset_class = "equity"
currency = "{currency}"
as_of = 2026-01-02
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
date_column = "Data"
date_format = "%d/%m/%Y"
delimiter = ";"
decimal_separator = ","
thousands_separator = "."
encoding = "utf-8"
currency = "{currency}"
frequency = "monthly"
{columns}
"""
COLUMN = '[columns."{isin}"]\ninstrument = "{isin}"\nprice_type = "price"\n'


def _fx(path: Path, rows: dict[str, str]) -> Path:
    """Write an ECB-format zip (one CSV, newest date first, trailing commas)."""
    lines = ["Date,USD,GBP,"] + [f"{day},{rate}," for day, rate in rows.items()]
    info = zipfile.ZipInfo("eurofxref-hist.csv", date_time=(2026, 3, 1, 0, 0, 0))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, "\n".join(lines) + "\n")
    return path


def _prices(tmp: Path, name: str, currency: str, isins: list[str], price: str) -> tuple[Path, Path]:
    days = ["02/01/2026", "30/01/2026", "27/02/2026"]
    csv = tmp / f"{name}.csv"
    csv.write_text(
        "Data;"
        + ";".join(isins)
        + "\n"
        + "".join(f"{d};" + ";".join([price] * len(isins)) + "\n" for d in days),
        encoding="utf-8",
    )
    mapping = tmp / f"{name}_mapping.toml"
    columns = "\n".join(COLUMN.format(isin=i) for i in isins)
    mapping.write_text(MAPPING.format(currency=currency, columns=columns), encoding="utf-8")
    return csv, mapping


def _setup(
    tmp: Path,
    *,
    base: str = "EUR",
    fx_rows: dict[str, str] | None = None,
    max_age: str | None = "0",
    with_eur_fund: bool = False,
    extra_inputs: str = "",
    fx: bool = True,
) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    extra = "t5;02/01/2026;Acquisto;IE0000000012;10;50,00;EUR;;;;;;\n" if with_eur_fund else ""
    deposit = "2.500,00" if with_eur_fund else "2.000,00"
    (tmp / "export.csv").write_text(EXPORT.format(extra=extra, deposit=deposit), encoding="utf-8")
    instruments = INSTRUMENT.format(isin=USD_FUND, currency="USD")
    if with_eur_fund:
        instruments += "\n" + INSTRUMENT.format(isin=EUR_FUND, currency="EUR")
    (tmp / "instruments.toml").write_text(instruments, encoding="utf-8")
    usd_csv, usd_mapping = _prices(tmp, "prices_usd", "USD", [USD_FUND], "100,00")
    inputs = [
        f'transactions = "{(tmp / "export.csv").as_posix()}"',
        f'transactions_mapping = "{(ROOT / "configs/csv_mappings/example_broker.toml").as_posix()}"',  # noqa: E501
        f'prices = "{usd_csv.as_posix()}"',
        f'prices_mapping = "{usd_mapping.as_posix()}"',
        f'instruments = "{(tmp / "instruments.toml").as_posix()}"',
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"',
    ]
    if fx:
        rows = fx_rows or dict.fromkeys(DATES, "1.25,0.8")
        inputs.append(f'fx = "{_fx(tmp / "fx.zip", rows).as_posix()}"')
    if with_eur_fund:
        eur_csv, eur_mapping = _prices(tmp, "prices_eur", "EUR", [EUR_FUND], "50,00")
        inputs += [
            f'extra_prices = {{ eur = "{eur_csv.as_posix()}" }}',
            f'extra_prices_mapping = {{ eur = "{eur_mapping.as_posix()}" }}',
        ]
    age = f"fx_max_age_days = {max_age}\n" if max_age is not None else ""
    config = tmp / "report.toml"
    config.write_text(
        '[experiment]\nname = "fx-report"\nkind = "portfolio_report"\n'
        'hypothesis = "descriptive"\n\n'
        "[inputs]\n" + "\n".join(inputs) + "\n" + extra_inputs + "\n"
        f'[parameters]\ntitle = "FX test"\nbase_currency = "{base}"\nlanguage = "en"\n'
        'flow_timing = "start"\nmax_price_age_days = 0\nreturn_frequency = "none"\n'
        f"generated_at = 2026-03-01T09:00:00Z\ntarget_weights = {{}}\n{age}\n"
        f'[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


def _run(config: Path) -> tuple[dict[str, object], str]:
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    html_path = result.output_dir / "report.html"
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    return dict(result.record), html


# ------------------------------------------------------------------------- by hand
def test_usd_position_and_cash_by_hand(tmp_path: Path) -> None:
    record, html = _run(_setup(tmp_path))
    assert record["status"] == "success", record["error"]
    assert record["scalars"]["end_value"] == {"value": 2000.0, "tag": "descriptive"}  # type: ignore[index]
    assert "ECB reference rates, max age 0 days" in html
    assert "eurofxref-hist" in html  # the FX file is listed with the sources
    assert "fx" in record["inputs"]  # type: ignore[operator]


def test_gbp_base_uses_the_cross_rate(tmp_path: Path) -> None:
    record, _ = _run(_setup(tmp_path, base="GBP"))
    assert record["status"] == "success", record["error"]
    assert record["scalars"]["end_value"]["value"] == pytest.approx(1600.0, abs=1e-9)  # type: ignore[index]


def test_an_extra_price_file_per_currency(tmp_path: Path) -> None:
    # Adds 10 units of a EUR fund at 50 EUR, paid from a 500 EUR larger deposit: 2,500 EUR.
    record, html = _run(_setup(tmp_path, with_eur_fund=True))
    assert record["status"] == "success", record["error"]
    assert record["scalars"]["end_value"]["value"] == 2500.0  # type: ignore[index]
    assert sorted(k for k in record["inputs"] if k.startswith("extra_prices")) == [  # type: ignore[attr-defined]
        "extra_prices.eur",
        "extra_prices_mapping.eur",
    ]
    assert "prices_eur" in html  # the extra price file is listed with the sources


def test_a_stale_rate_is_refused_or_listed(tmp_path: Path) -> None:
    rows = {"2026-02-26": "1.25,0.8", "2026-01-30": "1.25,0.8", "2026-01-02": "1.25,0.8"}
    refused, _ = _run(_setup(tmp_path / "strict", fx_rows=rows, max_age="0"))
    assert refused["status"] == "failure"
    assert "USD rate" in str(refused["error"])
    used, html = _run(_setup(tmp_path / "lenient", fx_rows=rows, max_age="1"))
    assert used["status"] == "success", used["error"]
    assert used["scalars"]["end_value"]["value"] == 2000.0  # type: ignore[index]
    assert "2026-02-26" in html  # the carried-forward rate is listed in the report


def test_without_fx_a_foreign_amount_still_raises(tmp_path: Path) -> None:
    record, _ = _run(_setup(tmp_path, fx=False, max_age=None))
    assert record["status"] == "failure"
    assert "single-currency" in str(record["error"])
    assert "fx input" in str(record["error"])


# ------------------------------------------------------------------------- validation
def test_fx_max_age_days_goes_with_the_fx_input(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="fx_max_age_days"):
        validate_experiment(_setup(tmp_path / "a", max_age=None), kinds=KINDS)
    with pytest.raises(ValidationError, match="fx_max_age_days"):
        validate_experiment(_setup(tmp_path / "b", fx=False), kinds=KINDS)
    with pytest.raises(ValidationError, match="fx_max_age_days"):
        validate_experiment(_setup(tmp_path / "c", max_age="-1"), kinds=KINDS)


def test_extra_price_groups_need_the_same_keys(tmp_path: Path) -> None:
    config = _setup(
        tmp_path,
        extra_inputs=f'extra_prices = {{ usd2 = "{(tmp_path / "export.csv").as_posix()}" }}\n',
    )
    with pytest.raises(ValidationError, match="same keys"):
        validate_experiment(config, kinds=KINDS)


def test_an_isin_in_two_price_files(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    usd_csv, usd_mapping = tmp_path / "prices_usd.csv", tmp_path / "prices_usd_mapping.toml"
    text = config.read_text(encoding="utf-8").replace(
        "\n[parameters]",
        f'extra_prices = {{ again = "{usd_csv.as_posix()}" }}\n'
        f'extra_prices_mapping = {{ again = "{usd_mapping.as_posix()}" }}\n\n[parameters]',
    )
    config.write_text(text, encoding="utf-8")
    record, _ = _run(config)
    assert record["status"] == "failure"
    assert "US0000000119 is in two price files" in str(record["error"])


def test_an_fx_sidecar_must_match_the_file(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    sidecar = tmp_path / "fx.zip.provenance.json"
    sidecar.write_text(
        json.dumps(
            {
                "source": "ecb",
                "dataset": "eurofxref-hist",
                "url": "file:fx.zip",
                "retrieved_at": "2026-03-01T00:00:00+00:00",
                "sha256": hashlib.sha256(b"other").hexdigest(),
                "size_bytes": 5,
                "terms": "synthetic",
            }
        ),
        encoding="utf-8",
    )
    record, _ = _run(config)
    assert record["status"] == "failure"
    assert "SHA-256" in str(record["error"])


def test_the_template_and_kind_list_the_new_inputs() -> None:
    kind = KINDS["portfolio_report"]
    assert kind.optional_inputs[0] == "fx"  # later phases add more
    assert kind.input_groups[:2] == ("extra_prices", "extra_prices_mapping")  # 7.4b adds more
    assert kind.optional_parameters[0] == "fx_max_age_days"
    template = config_template(kind)
    assert '# fx = "../data/FILL-IN"  # optional' in template
    assert "# [inputs.extra_prices]  # optional group: one file per key" in template
    assert "# fx_max_age_days = FILL-IN  # optional" in template


# ------------------------------------------------------------------------- the full example
def test_the_full_example_by_hand(tmp_path: Path) -> None:
    """``example_portfolio_report_full.toml`` on 31/03/2026, by hand.

    EUR side: the 15,480 EUR of the single-currency example, minus 1,000 EUR changed into
    1,240 USD and a 2 EUR fee: 14,478 EUR. USD side at 1.25: 10 units at 101 USD are 808 EUR;
    cash 1,240 - 1,000 + 5 (dividend) = 245 USD is 196 EUR. Total 15,482 EUR.
    """
    text = (ROOT / "configs/experiments/example_portfolio_report_full.toml").read_text(
        encoding="utf-8"
    )
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + f'directory = "{(tmp_path / "out").as_posix()}"' + text[end + 1 :]
    config = tmp_path / "full.toml"
    config.write_text(text, encoding="utf-8")
    record, html = _run(config)
    assert record["status"] == "success", record["error"]
    assert record["scalars"]["end_value"]["value"] == 15482.0  # type: ignore[index]
    assert "ECB reference rates, max age 0 days" in html
    assert "synthetic rates in the ECB file format" in html  # terms from the sidecar
    # Look-through (7.4b): the world fund is 50 x 54 = 2,700 EUR, and its holdings leave 1 %
    # unexplained, i.e. 27 / 15,482 of the portfolio.
    assert record["scalars"]["lookthrough_funds"]["value"] == 1.0  # type: ignore[index]
    assert record["scalars"]["unexplained_weight"]["value"] == pytest.approx(  # type: ignore[index]
        27 / 15482, abs=1e-15
    )
