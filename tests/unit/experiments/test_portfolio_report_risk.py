"""Risk and stress tests in the ``portfolio_report`` kind (design 8.3), with hand values.

**Two funds.** 1,000 EUR is deposited on 30/01/2026 and spent on 29/05/2026: 5 units of fund A
and 5 of fund B at 100 EUR each, so today's weights are 0.5 and 0.5 and there is no cash. The
monthly prices before that are built so that the four monthly returns are

    a = (2, -1, 3, 0) %,   b = (1, 1, -2, 0) %.

By hand (sample covariance, n - 1 = 3): var a = 3.333e-4, var b = 2.000e-4,
cov = -1.667e-4; portfolio variance = 0.25 x 3.333e-4 + 0.25 x 2e-4 + 2 x 0.25 x (-1.667e-4)
= 0.5e-4, volatility 0.70711 % per month; contributions 0.58926 % (83.3 %) and 0.11785 %
(16.7 %). Annualised: sqrt(12) x 0.70711 % = 2.44949 %.

**Currency.** A USD fund at 100 -> 110 -> 110 USD while EUR/USD goes 1.25 -> 1.10 -> 1.10: in
EUR, 80 -> 100 -> 100, so +25.0 % then 0 %. USD cash returns +13.636 % (1.25 / 1.10 - 1),
then 0 %.

**Stress.** A hypothetical -30 % shock to fund A, at 50 %, gives -15 %.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS

ROOT = Path(__file__).parents[3]
FUND_A, FUND_B, FUND_USD = "IE0000000012", "IE0000000020", "US0000001000"
MONTH_ENDS = ("30/01/2026", "27/02/2026", "31/03/2026", "30/04/2026", "29/05/2026")
RETURNS_A = (0.02, -0.01, 0.03, 0.0)
RETURNS_B = (0.01, 0.01, -0.02, 0.0)

INSTRUMENT = """\
[{isin}]
name = "Fund {isin}"
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
PRICE_MAPPING = """\
file_format = "csv"
skip_rows = 0
value_affixes = []
date_column = "Data"
date_format = "%d/%m/%Y"
delimiter = ";"
decimal_separator = ","
thousands_separator = ""
encoding = "utf-8"
currency = "{currency}"
frequency = "{frequency}"
{columns}
"""
COLUMN = '[columns."{isin}"]\ninstrument = "{isin}"\nprice_type = "{price_type}"\n'
RISK = """
[parameters.risk]
frequency = "{frequency}"
window = {window}
confidence = 0.95
covariance = {{ estimator = "sample" }}
"""


def _backwards(returns: tuple[float, ...], last: float = 100.0) -> list[float]:
    """Prices ending at ``last`` whose simple returns are ``returns``."""
    prices = [last]
    for r in reversed(returns):
        prices.insert(0, prices[0] / (1.0 + r))
    return prices


def _number(value: float) -> str:
    return f"{value:.12f}".replace(".", ",")


def _write_prices(
    tmp: Path, name: str, rows: list[tuple[str, list[float]]], isins: list[str], *,
    currency: str = "EUR", frequency: str = "monthly", price_type: str = "price",
) -> tuple[Path, Path]:  # fmt: skip
    csv = tmp / f"{name}.csv"
    csv.write_text(
        "Data;"
        + ";".join(isins)
        + "\n"
        + "".join(f"{d};" + ";".join(_number(p) for p in prices) + "\n" for d, prices in rows),
        encoding="utf-8",
    )
    mapping = tmp / f"{name}_mapping.toml"
    columns = "\n".join(COLUMN.format(isin=i, price_type=price_type) for i in isins)
    mapping.write_text(
        PRICE_MAPPING.format(currency=currency, frequency=frequency, columns=columns),
        encoding="utf-8",
    )
    return csv, mapping


def _config(
    tmp: Path, *, export: str, instruments: str, prices: tuple[Path, Path],
    extra_inputs: str = "", parameters: str = "", daily_checks: bool = False,
) -> Path:  # fmt: skip
    (tmp / "export.csv").write_text(
        "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
        "Controvalore;Divisa controvalore;Descrizione\n" + export,
        encoding="utf-8",
    )
    (tmp / "instruments.toml").write_text(instruments, encoding="utf-8")
    broker = (ROOT / "configs/csv_mappings/example_broker.toml").as_posix()
    checks = (ROOT / "configs/checks/example.toml").as_posix()
    if daily_checks:  # the checks' periods_per_year must match daily portfolio returns (7.1)
        text = (ROOT / "configs/checks/example.toml").read_text(encoding="utf-8")
        (tmp / "checks.toml").write_text(
            text.replace("periods_per_year = 12", "periods_per_year = 252"), encoding="utf-8"
        )
        checks = (tmp / "checks.toml").as_posix()
    config = tmp / "report.toml"
    config.write_text(
        '[experiment]\nname = "risk-report"\nkind = "portfolio_report"\n'
        'hypothesis = "descriptive"\n\n[inputs]\n'
        f'transactions = "{(tmp / "export.csv").as_posix()}"\n'
        f'transactions_mapping = "{broker}"\n'
        f'prices = "{prices[0].as_posix()}"\nprices_mapping = "{prices[1].as_posix()}"\n'
        f'instruments = "{(tmp / "instruments.toml").as_posix()}"\nchecks = "{checks}"\n'
        + extra_inputs
        + '\n[parameters]\ntransactions_format = "mapped"\n'
        'title = "Risk test"\nbase_currency = "EUR"\nlanguage = "en"\n'
        'flow_timing = "start"\nmax_price_age_days = 0\nreturn_frequency = "none"\n'
        "generated_at = 2026-06-01T09:00:00Z\ntarget_weights = {}\n"
        + parameters
        + f'\n[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


TWO_FUNDS_EXPORT = (
    "t3;29/05/2026;Acquisto;IE0000000020;5;100,00;EUR;;;;;;\n"
    "t2;29/05/2026;Acquisto;IE0000000012;5;100,00;EUR;;;;;;\n"
    "t1;30/01/2026;Bonifico in entrata;;;;EUR;1.000,00;;;;;\n"
)


def _two_funds(tmp: Path, *, risk: str = RISK.format(frequency="monthly", window=4),
               extra_inputs: str = "", daily: bool = False,
               price_type: str = "price") -> Path:  # fmt: skip
    tmp.mkdir(parents=True, exist_ok=True)
    a, b = _backwards(RETURNS_A), _backwards(RETURNS_B)
    rows = [(d, [pa, pb]) for d, pa, pb in zip(MONTH_ENDS, a, b, strict=True)]
    frequency = "monthly"
    if daily:  # every business day; only the month-end prices are the hand values
        days = pd.bdate_range("2026-01-02", "2026-05-29")
        ends = {pd.Timestamp(pd.to_datetime(d, dayfirst=True)): p for d, p in rows}
        rows = [
            (day.strftime("%d/%m/%Y"), ends.get(day, [90.0 + day.day % 7, 95.0 + day.day % 5]))
            for day in days
        ]
        frequency = "daily"
    prices = _write_prices(
        tmp, "prices", rows, [FUND_A, FUND_B], frequency=frequency, price_type=price_type
    )
    instruments = (
        INSTRUMENT.format(isin=FUND_A, currency="EUR")
        + "\n"
        + INSTRUMENT.format(isin=FUND_B, currency="EUR")
    )
    return _config(
        tmp,
        export=TWO_FUNDS_EXPORT,
        instruments=instruments,
        prices=prices,
        extra_inputs=extra_inputs,
        parameters=risk,
        daily_checks=daily,
    )


def _run(config: Path) -> tuple[dict[str, object], Path]:
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    return dict(result.record), result.output_dir


def _scalar(record: dict[str, object], name: str) -> float:
    return float(record["scalars"][name]["value"])  # type: ignore[index]


# ------------------------------------------------------------------------------ by hand
def test_two_funds_by_hand(tmp_path: Path) -> None:
    record, out = _run(_two_funds(tmp_path))
    assert record["status"] == "success", record["error"]
    assert _scalar(record, "volatility_period") == pytest.approx(0.0070710678, abs=1e-9)
    assert _scalar(record, "volatility_annual") == pytest.approx(0.0244948974, abs=1e-9)
    contributions = pd.read_csv(out / "risk_contributions.csv", index_col=0)
    assert contributions.loc[FUND_A, "weight"] == pytest.approx(0.5)
    assert contributions.loc[FUND_A, "contribution"] == pytest.approx(0.0058925565, abs=1e-9)
    assert contributions.loc[FUND_B, "contribution"] == pytest.approx(0.0011785113, abs=1e-9)
    assert contributions.loc[FUND_A, "share"] == pytest.approx(5 / 6)
    returns = pd.read_csv(out / "risk_returns.csv", index_col=0)
    assert returns[FUND_A].tolist() == pytest.approx(list(RETURNS_A), abs=1e-10)
    assert returns[FUND_B].tolist() == pytest.approx(list(RETURNS_B), abs=1e-10)
    var_es = pd.read_csv(out / "var_es.csv", index_col=0, keep_default_na=False)
    assert list(var_es.index) == ["historical", "normal", "Cornish-Fisher"]
    # 4 returns at 95 % leave a tail of 0.2 observations: no historical VaR, and it says why.
    assert "4 observations" in str(var_es.loc["historical", "note"])
    assert "var_historical" not in record["scalars"]  # type: ignore[operator]
    for table in ("risk_contributions.csv", "risk_returns.csv", "var_es.csv"):
        assert record["outputs"][table]["tag"] == "descriptive"  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Fund IE0000000012" in html
    assert "0.59%" in html
    assert "Risk is computed from price returns" in str(record["notice"])


def test_historical_var_and_es_match_the_portfolio_returns(tmp_path: Path) -> None:
    """Portfolio returns 0.5 a + 0.5 b = (1.5, 0, 0.5, 0) %. At 75 %, the tail is one return."""
    risk = RISK.format(frequency="monthly", window=4).replace("0.95", "0.75")
    record, out = _run(_two_funds(tmp_path, risk=risk))
    assert record["status"] == "success", record["error"]
    returns = pd.read_csv(out / "risk_returns.csv", index_col=0)
    assert returns["portfolio"].tolist() == pytest.approx([0.015, 0.0, 0.005, 0.0], abs=1e-10)
    from qrlab.metrics.risk import historical_es, historical_var

    series = returns["portfolio"]
    series.index = pd.DatetimeIndex(series.index)
    var_es = pd.read_csv(out / "var_es.csv", index_col=0)
    assert var_es.loc["historical", "var"] == pytest.approx(historical_var(series, confidence=0.75))
    assert var_es.loc["historical", "es"] == pytest.approx(historical_es(series, confidence=0.75))
    assert _scalar(record, "var_historical") == pytest.approx(var_es.loc["historical", "var"])


def test_daily_prices_give_the_same_monthly_returns(tmp_path: Path) -> None:
    _, monthly = _run(_two_funds(tmp_path / "m"))
    _, daily = _run(_two_funds(tmp_path / "d", daily=True))
    a = pd.read_csv(monthly / "risk_returns.csv", index_col=0)
    b = pd.read_csv(daily / "risk_returns.csv", index_col=0)
    assert a.index.tolist() == b.index.tolist()  # month-end labels
    assert b.to_numpy() == pytest.approx(a.to_numpy(), abs=1e-10)


def test_currency_and_foreign_cash_by_hand(tmp_path: Path) -> None:
    rows = [("30/01/2026", [100.0]), ("27/02/2026", [110.0]), ("31/03/2026", [110.0])]
    prices = _write_prices(tmp_path, "prices", rows, [FUND_USD], currency="USD")
    fx = tmp_path / "fx.zip"
    lines = "Date,USD,\n2026-03-31,1.10,\n2026-02-27,1.10,\n2026-01-30,1.25,\n"
    with zipfile.ZipFile(fx, "w") as archive:
        archive.writestr(zipfile.ZipInfo("eurofxref-hist.csv", (2026, 4, 1, 0, 0, 0)), lines)
    export = (
        "t3;30/01/2026;Acquisto;US0000001000;10;100,00;USD;;;;;;\n"
        "t2;30/01/2026;Cambio valuta;;;;EUR;-1.000,00;;;1.250,00;USD;\n"
        "t1;30/01/2026;Bonifico in entrata;;;;EUR;2.000,00;;;;;\n"
    )
    config = _config(
        tmp_path,
        export=export,
        instruments=INSTRUMENT.format(isin=FUND_USD, currency="USD"),
        prices=prices,
        extra_inputs=f'fx = "{fx.as_posix()}"\n',
        parameters="fx_max_age_days = 0\n" + RISK.format(frequency="monthly", window=2),
    )
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    returns = pd.read_csv(out / "risk_returns.csv", index_col=0)
    assert returns[FUND_USD].tolist() == pytest.approx([0.25, 0.0], abs=1e-12)
    assert returns["cash USD"].tolist() == pytest.approx([1.25 / 1.10 - 1.0, 0.0], abs=1e-12)
    assert "cash EUR" not in returns.columns  # base cash returns 0 and is left out


# ------------------------------------------------------------------------------ stress tests
def test_hypothetical_and_uncovered_scenarios(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios.toml"
    scenarios.write_text(
        '[fund_a_down]\nkind = "hypothetical"\ndescription = "Fund A falls 30 %"\n'
        f'factors = {{}}\npositions = {{ "{FUND_A}" = -0.30 }}\ncurrencies = {{}}\n\n'
        '[old_crisis]\nkind = "historical"\ndescription = "Before the prices"\n'
        "start = 2008-01-01\nend = 2008-12-31\n",
        encoding="utf-8",
    )
    record, out = _run(
        _two_funds(tmp_path / "run", extra_inputs=f'scenarios = "{scenarios.as_posix()}"\n')
    )
    assert record["status"] == "success", record["error"]
    table = pd.read_csv(out / "scenarios.csv", index_col=0)
    assert table.loc["fund_a_down", "portfolio_return"] == pytest.approx(-0.15)
    assert table.loc["fund_a_down", "not_covered_weight"] == pytest.approx(0.0)  # B: 0 shock
    assert table.loc["old_crisis", "not_covered_weight"] == pytest.approx(1.0)


# ------------------------------------------------------------------------------ errors
def test_a_window_longer_than_the_history_names_the_position(tmp_path: Path) -> None:
    record, _ = _run(_two_funds(tmp_path, risk=RISK.format(frequency="monthly", window=5)))
    assert record["status"] == "failure"
    assert "IE0000000012" in str(record["error"])
    assert "window" in str(record["error"])


def test_monthly_prices_cannot_give_weekly_returns(tmp_path: Path) -> None:
    record, _ = _run(_two_funds(tmp_path, risk=RISK.format(frequency="weekly", window=4)))
    assert record["status"] == "failure"
    assert "weekly" in str(record["error"])


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ('frequency = "monthly"', 'frequency = "daily"', "frequency"),
        ("window = 4", "window = 1", "window"),
        ("confidence = 0.95", "confidence = 1.5", "confidence"),
        ('covariance = { estimator = "sample" }\n', "", "covariance"),
    ],
)
def test_risk_parameters_are_validated(tmp_path: Path, old: str, new: str, match: str) -> None:
    risk = RISK.format(frequency="monthly", window=4)
    assert old in risk
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_two_funds(tmp_path, risk=risk.replace(old, new)), kinds=KINDS)


def test_scenarios_need_the_risk_parameters(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios.toml"
    scenarios.write_text("", encoding="utf-8")
    config = _two_funds(
        tmp_path / "run", risk="", extra_inputs=f'scenarios = "{scenarios.as_posix()}"\n'
    )
    with pytest.raises(ValidationError, match=r"\[parameters.risk\]"):
        validate_experiment(config, kinds=KINDS)


def test_without_risk_nothing_changes(tmp_path: Path) -> None:
    record, out = _run(_two_funds(tmp_path, risk=""))
    assert record["status"] == "success", record["error"]
    assert not (out / "risk_contributions.csv").exists()
    assert "volatility_period" not in record["scalars"]  # type: ignore[operator]
    assert record["notice"] is None
    record_json = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert record_json["notice"] is None


def test_the_kind_lists_the_risk_inputs() -> None:
    kind = KINDS["portfolio_report"]
    assert "scenarios" in kind.optional_inputs
    assert "risk" in kind.optional_parameters


def test_nav_prices_need_no_price_only_notice(tmp_path: Path) -> None:
    record, _ = _run(_two_funds(tmp_path, price_type="nav"))
    assert record["status"] == "success", record["error"]
    assert record["notice"] is None


def test_cornish_fisher_is_reported_when_defined(tmp_path: Path, rng: np.random.Generator) -> None:
    """With 120 fat-tailed monthly returns the Cornish-Fisher expansion is a quantile."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    days = pd.date_range("2016-01-29", periods=121, freq="BME")
    ra = 0.005 + 0.02 * rng.standard_t(5, 120)  # fat tails: inside the expansion's domain
    rb = 0.003 + 0.015 * rng.standard_t(5, 120)
    rows = [
        (d.strftime("%d/%m/%Y"), [pa, pb])
        for d, pa, pb in zip(days, _backwards(tuple(ra)), _backwards(tuple(rb)), strict=True)
    ]
    prices = _write_prices(tmp_path, "prices", rows, [FUND_A, FUND_B], price_type="nav")
    last = days[-1].strftime("%d/%m/%Y")
    export = (
        f"t3;{last};Acquisto;IE0000000020;5;100,00;EUR;;;;;;\n"
        f"t2;{last};Acquisto;IE0000000012;5;100,00;EUR;;;;;;\n"
        f"t1;{days[0].strftime('%d/%m/%Y')};Bonifico in entrata;;;;EUR;1.000,00;;;;;\n"
    )
    instruments = (
        INSTRUMENT.format(isin=FUND_A, currency="EUR")
        + "\n"
        + INSTRUMENT.format(isin=FUND_B, currency="EUR")
    )
    config = _config(
        tmp_path, export=export, instruments=instruments, prices=prices,
        parameters=RISK.format(frequency="monthly", window=120),
    )  # fmt: skip
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    var_es = pd.read_csv(out / "var_es.csv", index_col=0, keep_default_na=False)
    assert var_es.loc["Cornish-Fisher", "note"] == ""
    assert float(str(var_es.loc["Cornish-Fisher", "var"])) > 0


def test_unit_values_need_fx_and_known_currencies() -> None:
    from qrlab.core.money import Currency
    from qrlab.data import parse_ecb_fx
    from qrlab.data.provenance import Provenance
    from qrlab.experiments.kinds._portfolio_risk import unit_values

    eur, usd, gbp = Currency("EUR"), Currency("USD"), Currency("GBP")
    with pytest.raises(ValidationError, match="needs an fx input"):
        unit_values(None, eur, {usd})
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("eurofxref-hist.csv", "Date,USD,\n2026-01-30,1.25,\n")
    data = content.getvalue()
    provenance = Provenance(
        source="ecb", dataset="eurofxref-hist", url="file:fx.zip",
        retrieved_at=datetime(2026, 2, 1, tzinfo=UTC), sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data), terms="synthetic",
    )  # fmt: skip
    fx = parse_ecb_fx(data, provenance)
    with pytest.raises(ValidationError, match="no ECB rate for GBP"):
        unit_values(fx, eur, {gbp})


@pytest.mark.parametrize("risk", ["\nrisk = 3\n"])
def test_risk_must_be_a_table(tmp_path: Path, risk: str) -> None:
    with pytest.raises(ValidationError, match=r"\[parameters.risk\] must be a table"):
        validate_experiment(_two_funds(tmp_path, risk=risk), kinds=KINDS)
