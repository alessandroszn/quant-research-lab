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
missing_tokens = []
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
    # Two accumulating funds: their prices hold their income, so nothing is named (11.1).
    assert record["notice"] is None
    sources = pd.read_csv(out / "return_sources.csv", index_col=0)
    assert sources["source"].tolist() == ["accumulating", "accumulating"]
    assert sources["income_included"].tolist() == [True, True]
    assert "Price of an accumulating fund" in html


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


# ------------------------------------------------------------- total returns (design note 11.1)
# Fund B distributes 2 % of its 27/02 price with ex-date 31/03, so its March return is 1 % + 2 %
# = 3 % and its returns become b' = (1, 3, -2, 0) %. By hand (n - 1 = 3): var a = 10/3 e-4,
# var b' = 13/3 e-4, cov = -3 e-4; portfolio variance = 0.25 (10/3 + 13/3) e-4 - 0.5 x 3 e-4 =
# 5/12 e-4, volatility sqrt(5/12) % = 0.645497 % per month (0.707107 % on prices).
B_PRICES = _backwards(RETURNS_B)
PAID = 0.02 * B_PRICES[1]  # 2 % of the 27/02 price, ex-date 31/03
RETURNS_B_TOTAL = (0.01, 0.03, -0.02, 0.0)
DISTRIBUTIONS = (
    "\n[parameters.distributions]\n"
    f'{FUND_B} = [{{ ex_date = 2026-03-31, per_unit = {PAID!r}, currency = "EUR" }}]\n'
)


def _distributing(tmp: Path, *, parameters: str = "", extra_inputs: str = "",
                  price_type: str = "price", policy: str = "distributing") -> Path:  # fmt: skip
    config = _two_funds(tmp, price_type=price_type, extra_inputs=extra_inputs)
    instruments = tmp / "instruments.toml"
    text = instruments.read_text(encoding="utf-8")
    head, tail = text.split(f"[{FUND_B}]")
    instruments.write_text(
        head + f"[{FUND_B}]" + tail.replace('"accumulating"', f'"{policy}"'), encoding="utf-8"
    )
    config.write_text(
        config.read_text(encoding="utf-8").replace("\n[output]", parameters + "\n[output]"),
        encoding="utf-8",
    )
    return config


def _total_return_file(tmp: Path, *, price_type: str = "total_return",
                       currency: str = "EUR") -> str:  # fmt: skip
    """Fund B's total-return index (its prices with the distribution reinvested)."""
    index = _backwards(RETURNS_B_TOTAL)
    rows = [(d, [v]) for d, v in zip(MONTH_ENDS, index, strict=True)]
    csv, mapping = _write_prices(
        tmp, "total", rows, [FUND_B], price_type=price_type, currency=currency
    )
    return f'total_returns = "{csv.as_posix()}"\ntotal_returns_mapping = "{mapping.as_posix()}"\n'


def test_distributions_by_hand(tmp_path: Path) -> None:
    record, out = _run(_distributing(tmp_path, parameters=DISTRIBUTIONS))
    assert record["status"] == "success", record["error"]
    returns = pd.read_csv(out / "risk_returns.csv", index_col=0)
    assert returns[FUND_B].tolist() == pytest.approx(list(RETURNS_B_TOTAL), abs=1e-10)
    assert returns[FUND_A].tolist() == pytest.approx(list(RETURNS_A), abs=1e-10)
    assert _scalar(record, "volatility_period") == pytest.approx(0.00645497224, abs=1e-10)
    sources = pd.read_csv(out / "return_sources.csv", index_col=0)
    assert sources.loc[FUND_B, "source"] == "distributions"
    assert bool(sources.loc[FUND_B, "income_included"])
    assert record["outputs"]["return_sources.csv"]["tag"] == "descriptive"  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Returns used for risk" in html
    assert "Price plus the distributions given" in html
    assert record["notice"] is None  # every position's returns include its income


def test_a_total_return_file_gives_the_same_returns(tmp_path: Path) -> None:
    from_distributions, out_d = _run(_distributing(tmp_path / "d", parameters=DISTRIBUTIONS))
    (tmp_path / "f").mkdir()
    file_inputs = _total_return_file(tmp_path / "f")
    from_file, out_f = _run(_distributing(tmp_path / "f", extra_inputs=file_inputs))
    assert from_file["status"] == "success", from_file["error"]
    a = pd.read_csv(out_d / "risk_returns.csv", index_col=0)
    b = pd.read_csv(out_f / "risk_returns.csv", index_col=0)
    pd.testing.assert_frame_equal(a, b, atol=1e-12)
    sources = pd.read_csv(out_f / "return_sources.csv", index_col=0)
    assert sources.loc[FUND_B, "source"] == "total_return_file"
    assert "Total-return series given" in (out_f / "report.html").read_text(encoding="utf-8")
    assert _scalar(from_file, "volatility_period") == pytest.approx(
        _scalar(from_distributions, "volatility_period"), abs=1e-12
    )


@pytest.mark.parametrize("price_type", ["price", "nav"])
def test_a_distributing_fund_without_income_is_named(tmp_path: Path, price_type: str) -> None:
    """A NAV falls by each distribution like a price: both are named (the NAV was not, 8.3)."""
    record, out = _run(_distributing(tmp_path, price_type=price_type))
    assert record["status"] == "success", record["error"]
    notice = str(record["notice"])
    assert f"Fund {FUND_B} (distributing)" in notice
    assert f"Fund {FUND_A}" not in notice
    assert "exclude the income paid out" in notice
    sources = pd.read_csv(out / "return_sources.csv", index_col=0)
    assert sources.loc[FUND_B, "source"] == "distributing"
    assert not bool(sources.loc[FUND_B, "income_included"])
    assert _scalar(record, "volatility_period") == pytest.approx(0.0070710678, abs=1e-9)


def test_the_note_is_given_for_the_checks_alone(tmp_path: Path) -> None:
    """Without [parameters.risk] the diversification checks still read returns."""
    config = _distributing(tmp_path)
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace(RISK.format(frequency="monthly", window=4), ""), encoding="utf-8"
    )
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    assert f"Fund {FUND_B} (distributing)" in str(record["notice"])
    assert not (out / "return_sources.csv").exists()  # the table belongs to the risk section


def test_the_report_table_in_italian(tmp_path: Path) -> None:
    config = _distributing(tmp_path, parameters=DISTRIBUTIONS)
    text = config.read_text(encoding="utf-8").replace('language = "en"', 'language = "it"')
    config.write_text(text, encoding="utf-8")
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Rendimenti usati per il rischio" in html
    assert "Prezzo più le distribuzioni fornite" in html
    assert "Prezzo di un fondo ad accumulazione" in html


def _payments(*entries: str) -> str:
    return f"\n[parameters.distributions]\n{FUND_B} = [{', '.join(entries)}]\n"


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (_payments('{ ex_date = 2026-03-31, per_unit = 0.0, currency = "EUR" }'),
         "per_unit must be positive"),
        (_payments('{ ex_date = 2026-03-31, per_unit = 1.0, currency = "EUR" }',
                   '{ ex_date = 2026-03-31, per_unit = 2.0, currency = "EUR" }'),
         "two distributions on 2026-03-31"),
        (_payments("{ ex_date = 2026-03-31, per_unit = 1.0 }"), "currency"),
        (f"\n[parameters.distributions]\n{FUND_B} = []\n", "non-empty list"),
        (f"\n[parameters.distributions]\n{FUND_B} = [1.0]\n", "every entry must be a table"),
    ],
)  # fmt: skip
def test_bad_distributions_are_refused_when_read(
    tmp_path: Path, parameters: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_experiment(_distributing(tmp_path, parameters=parameters), kinds=KINDS)


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (_payments('{ ex_date = 2026-03-31, per_unit = 1.0, currency = "USD" }'),
         "USD, its price file in EUR"),
        (_payments('{ ex_date = 2026-06-30, per_unit = 1.0, currency = "EUR" }'),
         "after the last price date"),
        (_payments('{ ex_date = 2026-01-30, per_unit = 1.0, currency = "EUR" }'),
         "on or before the first price date"),
    ],
)  # fmt: skip
def test_distributions_that_do_not_fit_the_prices_fail_the_run(
    tmp_path: Path, parameters: str, message: str
) -> None:
    record, _ = _run(_distributing(tmp_path, parameters=parameters))
    assert record["status"] == "failure"
    assert message in str(record["error"])


def test_distributions_must_be_a_table_of_funds(tmp_path: Path) -> None:
    config = _distributing(tmp_path, parameters="\n[parameters.distributions]\n")
    with pytest.raises(ValidationError, match="per fund ISIN"):
        validate_experiment(config, kinds=KINDS)


def test_distributions_of_a_fund_not_held_raise(tmp_path: Path) -> None:
    parameters = (
        "\n[parameters.distributions]\n"
        'IE0000000038 = [{ ex_date = 2026-03-31, per_unit = 1.0, currency = "EUR" }]\n'
    )
    record, _ = _run(_distributing(tmp_path, parameters=parameters))
    assert record["status"] == "failure"
    assert "IE0000000038 is not held" in str(record["error"])


def test_a_fund_cannot_have_both_inputs(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    inputs = _total_return_file(tmp_path)
    record, _ = _run(_distributing(tmp_path, parameters=DISTRIBUTIONS, extra_inputs=inputs))
    assert record["status"] == "failure"
    assert "both a total-return series and distributions" in str(record["error"])


@pytest.mark.parametrize(
    ("price_type", "currency", "message"),
    [
        ("nav", "EUR", 'price_type = "total_return", not "nav"'),
        ("total_return", "USD", "must be in EUR, the same currency as its price file"),
    ],
)
def test_bad_total_return_files_raise(
    tmp_path: Path, price_type: str, currency: str, message: str
) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    inputs = _total_return_file(tmp_path, price_type=price_type, currency=currency)
    record, _ = _run(_distributing(tmp_path, extra_inputs=inputs))
    assert record["status"] == "failure"
    assert message in str(record["error"])


def test_a_total_return_file_needs_its_mapping(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    inputs = _total_return_file(tmp_path).split("\n")[0] + "\n"
    with pytest.raises(ValidationError, match="go together"):
        validate_experiment(_distributing(tmp_path, extra_inputs=inputs), kinds=KINDS)


def test_a_total_return_series_needs_a_price_file(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    index = _backwards(RETURNS_B_TOTAL)
    rows = [(d, [v]) for d, v in zip(MONTH_ENDS, index, strict=True)]
    csv, mapping = _write_prices(
        tmp_path, "total", rows, ["IE0000000038"], price_type="total_return"
    )
    inputs = f'total_returns = "{csv.as_posix()}"\ntotal_returns_mapping = "{mapping.as_posix()}"\n'
    record, _ = _run(_distributing(tmp_path, extra_inputs=inputs))
    assert record["status"] == "failure"
    assert "IE0000000038 has no price file" in str(record["error"])


# ------------------------------------------------------------------ benchmark (design note 11.2)
# 1,000 EUR buys 10 units of fund A on 30/01 at its price that day, so the portfolio's monthly
# returns are a = (2, -1, 3, 0) % (the start-of-day return on 30/01 is 0 and is left out). The
# benchmark returns b = (1, 0, 2, 0) %. By hand (n - 1 = 3): active (1, -1, 1, 0) %, mean
# 0.25 %, variance 2.75 / 3 = 11/12 (%^2), so the tracking error is sqrt(11/12) x sqrt(12) % =
# sqrt(11) % = 3.316625 % and the information ratio 12 x 0.25 / sqrt(11) = 0.904534; beta =
# S_xy / S_xx = 5 / 2.75 = 1.818182.
BENCH_RETURNS = (0.01, 0.0, 0.02, 0.0)
BENCH = '\n[parameters.benchmark]\nname = "Example index, net total return"\n'


def _with_benchmark(tmp: Path, *, parameters: str = BENCH, columns: int = 1,
                    price_type: str = "total_return", currency: str = "EUR",
                    files: bool = True) -> Path:  # fmt: skip
    tmp.mkdir(parents=True, exist_ok=True)
    a = _backwards(RETURNS_A)
    prices = _write_prices(
        tmp, "prices", [(d, [p]) for d, p in zip(MONTH_ENDS, a, strict=True)], [FUND_A]
    )
    levels = _backwards(BENCH_RETURNS)
    rows = [(d, [v] * columns) for d, v in zip(MONTH_ENDS, levels, strict=True)]
    names = ["INDEX", "OTHER"][:columns]
    bench = _write_prices(tmp, "bench", rows, names, price_type=price_type, currency=currency)
    export = (
        f"t2;30/01/2026;Acquisto;{FUND_A};10;{_number(a[0])};EUR;;;;;;\n"
        f"t1;30/01/2026;Bonifico in entrata;;;;EUR;{_number(10 * a[0])};;;;;\n"
    )
    inputs = (
        f'benchmark = "{bench[0].as_posix()}"\nbenchmark_mapping = "{bench[1].as_posix()}"\n'
        if files
        else ""
    )
    config = _config(
        tmp,
        export=export,
        instruments=INSTRUMENT.format(isin=FUND_A, currency="EUR"),
        prices=prices,
        extra_inputs=inputs,
        parameters=parameters,
    )
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace('return_frequency = "none"', 'return_frequency = "monthly"'),
        encoding="utf-8",
    )
    return config


def test_benchmark_by_hand(tmp_path: Path) -> None:
    record, out = _run(_with_benchmark(tmp_path))
    assert record["status"] == "success", record["error"]
    table = pd.read_csv(out / "benchmark.csv", index_col=0)
    assert table["portfolio"].tolist() == pytest.approx(list(RETURNS_A), abs=1e-10)
    assert table["benchmark"].tolist() == pytest.approx(list(BENCH_RETURNS), abs=1e-10)
    assert len(table) == 4  # the start-of-day return on 30/01 is left out
    assert _scalar(record, "tracking_error") == pytest.approx(0.03316625, abs=1e-8)
    assert _scalar(record, "information_ratio") == pytest.approx(0.904534, abs=1e-6)
    assert _scalar(record, "beta") == pytest.approx(5 / 2.75, abs=1e-9)
    assert _scalar(record, "benchmark_total") == pytest.approx(1.01 * 1.02 - 1.0, abs=1e-10)
    assert record["outputs"]["benchmark.csv"]["tag"] == "descriptive"  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Example index, net total return" in html
    assert "Tracking error (annualised)" in html
    assert "Beta (on returns; no risk-free series given)" in html
    # The risk.beta check now has a benchmark: 1.82 is above its critical level of 1.50.
    findings = pd.read_csv(out / "check_findings.csv")
    beta = findings[findings["check"] == "risk.beta"]
    assert beta["severity"].tolist() == ["critical"]
    assert float(beta["observed"].iloc[0]) == pytest.approx(5 / 2.75, abs=1e-9)


def test_without_a_benchmark_the_report_says_so(tmp_path: Path) -> None:
    record, out = _run(_with_benchmark(tmp_path, parameters="", files=False))
    assert record["status"] == "success", record["error"]
    assert not (out / "benchmark.csv").exists()
    assert "No benchmark was given for this report." in (out / "report.html").read_text(
        encoding="utf-8"
    )
    findings = pd.read_csv(out / "check_findings.csv")
    assert "risk.beta" not in findings["check"].tolist()  # not applicable, as before


def test_the_benchmark_section_in_italian(tmp_path: Path) -> None:
    config = _with_benchmark(tmp_path)
    text = config.read_text(encoding="utf-8").replace('language = "en"', 'language = "it"')
    config.write_text(text, encoding="utf-8")
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Portafoglio rispetto al benchmark" in html
    assert "Tracking error (annualizzato)" in html


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"columns": 2}, "exactly one column"),
        ({"price_type": "price"}, 'price_type = "total_return", not "price"'),
        ({"currency": "USD"}, "needs an fx input"),
    ],
)
def test_bad_benchmarks_fail_the_run(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    record, _ = _run(_with_benchmark(tmp_path, **changes))  # type: ignore[arg-type]
    assert record["status"] == "failure"
    assert message in str(record["error"])


@pytest.mark.parametrize(
    ("parameters", "files"), [(BENCH, False), ("", True), ("benchmark = 1\n", True)]
)
def test_the_benchmark_inputs_go_together(tmp_path: Path, parameters: str, files: bool) -> None:
    config = _with_benchmark(tmp_path, parameters=parameters, files=files)
    with pytest.raises(ValidationError, match="benchmark"):
        validate_experiment(config, kinds=KINDS)


# ------------------------------------------- VaR backtest and factor proxies (design note 11.4)
# Two funds with the same returns, at 0.5 / 0.5, give portfolio returns
# (1, -1, 2, 0, -5, 1, 3, -4) %. With a window of 4 and the normal model at 95 %, the forecasts
# are 1.6235, 5.8423, 5.6141 and 5.8481 %: only -5 % exceeds its forecast. n = 4, x = 1,
# expected 0.2, Kupiec LR = -2 [3 ln 0.95 + ln 0.05 - 3 ln 0.75 - ln 0.25] = 1.8005, p 0.1796.
BACKTEST_RETURNS = (0.01, -0.01, 0.02, 0.0, -0.05, 0.01, 0.03, -0.04)
BACKTEST = '\n[parameters.risk.backtest]\nwindow = {window}\nmodel = "{model}"\n'


def _backtested(
    tmp: Path, *, window: int = 4, model: str = "normal", repeat: int = 1, confidence: str = "0.95"
) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    returns = BACKTEST_RETURNS * repeat
    # business month ends, so the last five are MONTH_ENDS, the dates of TWO_FUNDS_EXPORT
    ends = pd.date_range(end="2026-05-29", periods=len(returns) + 1, freq="BME")
    days = [d.strftime("%d/%m/%Y") for d in ends]
    path = _backwards(returns)
    rows = [(d, [p, p]) for d, p in zip(days, path, strict=True)]
    prices = _write_prices(tmp, "prices", rows, [FUND_A, FUND_B])
    instruments = (
        INSTRUMENT.format(isin=FUND_A, currency="EUR")
        + "\n"
        + INSTRUMENT.format(isin=FUND_B, currency="EUR")
    )
    risk = RISK.format(frequency="monthly", window=4).replace("0.95", confidence)
    risk += BACKTEST.format(window=window, model=model)
    return _config(tmp, export=TWO_FUNDS_EXPORT, instruments=instruments, prices=prices,
                   parameters=risk)  # fmt: skip


def test_var_backtest_by_hand(tmp_path: Path) -> None:
    record, out = _run(_backtested(tmp_path))
    assert record["status"] == "success", record["error"]
    path = pd.read_csv(out / "var_backtest.csv", index_col=0)
    assert path["return"].tolist() == pytest.approx(list(BACKTEST_RETURNS[4:]), abs=1e-10)
    assert path["var"].tolist() == pytest.approx([0.016235, 0.058423, 0.056141, 0.058481], abs=1e-6)
    assert path["exceedance"].tolist() == [True, False, False, False]
    assert _scalar(record, "backtest_exceedances") == 1.0
    assert _scalar(record, "backtest_expected") == pytest.approx(0.2)
    assert _scalar(record, "kupiec_pvalue") == pytest.approx(0.1796, abs=1e-4)
    assert record["outputs"]["var_backtest.csv"]["tag"] == "out_of_sample"  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Backtest of the VaR model" in html
    assert "Fewer than 5 exceedances are expected" in html


@pytest.mark.parametrize(
    ("model", "window", "confidence"),
    [("normal", 6, 0.95), ("historical", 5, 0.8)],
)
def test_var_backtest_matches_the_library(
    tmp_path: Path, model: str, window: int, confidence: float
) -> None:
    from qrlab.metrics.risk import historical_var, parametric_var
    from qrlab.risk.var_backtest import var_backtest, var_forecasts

    record, out = _run(
        _backtested(tmp_path, window=window, model=model, repeat=4, confidence=str(confidence))
    )
    assert record["status"] == "success", record["error"]
    models = {
        "normal": lambda r: parametric_var(r, confidence=confidence),
        "historical": lambda r: historical_var(r, confidence=confidence),
    }
    index = pd.date_range(end="2026-05-31", periods=32, freq="ME")
    series = pd.Series(BACKTEST_RETURNS * 4, index=index)
    forecasts = var_forecasts(series, window=window, model=models[model])
    test = var_backtest(series.loc[forecasts.index], forecasts, confidence=confidence)
    path = pd.read_csv(out / "var_backtest.csv", index_col=0)
    assert path["var"].tolist() == pytest.approx(forecasts.tolist(), abs=1e-10)
    assert _scalar(record, "conditional_coverage_pvalue") == pytest.approx(
        test.conditional_coverage_pvalue, abs=1e-10
    )
    html = (out / "report.html").read_text(encoding="utf-8")
    assert ("Fewer than 5 exceedances are expected" in html) == (test.expected < 5)


def test_the_cornish_fisher_model_is_the_library_one(rng: np.random.Generator) -> None:
    """Cornish-Fisher is often undefined on short windows (as in risk_report): checked directly."""
    from qrlab.experiments.kinds._portfolio_risk import _var_model
    from qrlab.risk.var_methods import cornish_fisher

    index = pd.date_range("2016-01-31", periods=120, freq="ME")
    returns = pd.Series(0.005 + 0.02 * rng.standard_t(5, 120), index=index)
    model = _var_model("cornish_fisher", 0.95)
    assert model(returns) == cornish_fisher(returns, confidence=0.95).var


def test_a_backtest_needs_two_forecasts(tmp_path: Path) -> None:
    record, _ = _run(_backtested(tmp_path, window=7))
    assert record["status"] == "failure"
    assert "8 monthly returns at today's weights give fewer than 2 forecasts" in str(
        record["error"]
    )


def test_the_backtest_table_in_italian(tmp_path: Path) -> None:
    config = _backtested(tmp_path)
    config.write_text(
        config.read_text(encoding="utf-8").replace('language = "en"', 'language = "it"'),
        encoding="utf-8",
    )
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Backtest del modello di VaR" in html
    assert "Test di Kupiec, p-value (copertura)" in html


# Fund A's prices start on 30/01/2026; a historical scenario in early 2025 covers only fund B,
# whose price is flat then (a window is covered by a series with a return dated on or before
# its start, hence the prices of 29/11/2024). A factor returns -10 % then +5 %: with beta 0.8
# the proxy gives (1 - 0.08)(1 + 0.04) - 1 = -4.32 %, so the portfolio, at 0.5 / 0.5, loses
# 2.16 %. A hypothetical factor shock of -20 % gives -16 % for fund A.
EARLY_2025 = ("29/11/2024", "31/12/2024", "31/01/2025", "28/02/2025", "31/03/2025", "30/04/2025",
              "30/05/2025", "30/06/2025", "31/07/2025", "29/08/2025", "30/09/2025",
              "31/10/2025", "28/11/2025", "31/12/2025")  # fmt: skip
PROXIES = f'\n[parameters.risk.proxies."{FUND_A}"]\nWorld = 0.8\n'
SCENARIOS = (
    '[early_2025]\nkind = "historical"\ndescription = "Early 2025"\n'
    "start = 2024-12-31\nend = 2025-02-28\n\n"
    '[world_down]\nkind = "hypothetical"\ndescription = "World -20 %"\n'
    "factors = { World = -0.20 }\npositions = {}\ncurrencies = {}\n"
)


def _proxied(tmp: Path, *, proxies: str = PROXIES, factors: bool = True,
             price_type: str = "total_return", currency: str = "EUR") -> Path:  # fmt: skip
    tmp.mkdir(parents=True, exist_ok=True)
    a, b = _backwards(RETURNS_A), _backwards(RETURNS_B)
    lines = [f"{d};;{_number(100.0)}" for d in EARLY_2025]
    lines += [
        f"{d};{_number(pa)};{_number(pb)}" for d, pa, pb in zip(MONTH_ENDS, a, b, strict=True)
    ]
    prices = tmp / "prices.csv"
    prices.write_text(f"Data;{FUND_A};{FUND_B}\n" + "\n".join(lines) + "\n", encoding="utf-8")
    mapping = tmp / "prices_mapping.toml"
    columns = "\n".join(COLUMN.format(isin=i, price_type="price") for i in (FUND_A, FUND_B))
    mapping.write_text(
        PRICE_MAPPING.format(currency="EUR", frequency="monthly", columns=columns),
        encoding="utf-8",
    )
    scenarios = tmp / "scenarios.toml"
    scenarios.write_text(SCENARIOS, encoding="utf-8")
    rows = [("29/11/2024", [100.0]), ("31/12/2024", [100.0]), ("31/01/2025", [90.0]),
            ("28/02/2025", [94.5])]  # fmt: skip
    factor_files = _write_prices(tmp, "factors", rows, ["World"], price_type=price_type,
                                 currency=currency)  # fmt: skip
    extra = f'scenarios = "{scenarios.as_posix()}"\n'
    if factors:
        extra += (
            f'factors = "{factor_files[0].as_posix()}"\n'
            f'factors_mapping = "{factor_files[1].as_posix()}"\n'
        )
    instruments = (
        INSTRUMENT.format(isin=FUND_A, currency="EUR")
        + "\n"
        + INSTRUMENT.format(isin=FUND_B, currency="EUR")
    )
    return _config(tmp, export=TWO_FUNDS_EXPORT, instruments=instruments,
                   prices=(prices, mapping), extra_inputs=extra,
                   parameters=RISK.format(frequency="monthly", window=4) + proxies)  # fmt: skip


def test_a_factor_proxy_by_hand(tmp_path: Path) -> None:
    record, out = _run(_proxied(tmp_path))
    assert record["status"] == "success", record["error"]
    table = pd.read_csv(out / "scenarios.csv", index_col=0)
    assert table.loc["early_2025", "portfolio_return"] == pytest.approx(0.5 * -0.0432, abs=1e-12)
    assert table.loc["early_2025", "not_covered_weight"] == pytest.approx(0.0)
    assert table.loc["world_down", "portfolio_return"] == pytest.approx(0.5 * -0.16, abs=1e-12)
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Factor proxies in the stress tests" in html
    assert "Factor proxy" in html  # the method of fund A in the scenario detail


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"proxies": ""}, "factors, factors_mapping and [parameters.risk.proxies] go together"),
        ({"factors": False}, "go together"),
        ({"price_type": "price"}, 'must declare price_type = "total_return"'),
        ({"currency": "USD"}, "factors are in USD, IE0000000012 is exposed to EUR"),
        ({"proxies": '\n[parameters.risk.proxies."IE0000000038"]\nWorld = 1.0\n'},
         "are not held"),
        ({"proxies": f'\n[parameters.risk.proxies."{FUND_A}"]\nEurope = 1.0\n'},
         "no factor returns for ['Europe']"),
        ({"proxies": f'\n[parameters.risk.proxies."{FUND_A}"]\nWorld = "one"\n'},
         "World must be a finite number"),
        ({"proxies": f'\n[parameters.risk.proxies."{FUND_A}"]\n'},
         "must be a non-empty table"),
        ({"proxies": "\n[parameters.risk.proxies]\n"}, "per ISIN, a table of factor = beta"),
    ],
)  # fmt: skip
def test_proxy_errors(tmp_path: Path, changes: dict[str, object], message: str) -> None:
    config = _proxied(tmp_path, **changes)  # type: ignore[arg-type]
    try:
        validate_experiment(config, kinds=KINDS)
    except ValidationError as error:
        assert message in str(error)  # noqa: PT017 - refused when the config is read
        return
    record, _ = _run(config)
    assert record["status"] == "failure"
    assert message in str(record["error"])


@pytest.mark.parametrize(
    ("backtest", "message"),
    [
        (BACKTEST.format(window=1, model="normal"), "window"),
        (BACKTEST.format(window=4, model="garch"), "model"),
        ("\n[parameters.risk]\nbacktest = 1\n", "must be a table"),
    ],
)
def test_backtest_settings_are_checked(tmp_path: Path, backtest: str, message: str) -> None:
    config = _two_funds(tmp_path)
    text = config.read_text(encoding="utf-8")
    if backtest.startswith("\n[parameters.risk]\n"):
        text = text.replace("confidence = 0.95\n", "confidence = 0.95\nbacktest = 1\n")
    else:
        text = text.replace("\n[output]", backtest + "\n[output]")
    config.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError, match=message):
        validate_experiment(config, kinds=KINDS)
