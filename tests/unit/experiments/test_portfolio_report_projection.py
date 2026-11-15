"""Projection and savings plan in the ``portfolio_report`` kind (design 8.4), with hand values.

**Deterministic case.** Today's portfolio is 100 units of one fund at 100 EUR = 10,000 EUR, no
cash. With zero volatility every path is the same. With a mean of ln(1.005) per month, 100 EUR
paid at the start of each month for 12 months and no cost, tax or inflation:

    W12 = 10,000 x 1.005^12 + 100 x sum_{k=1..12} 1.005^k = 10,616.78 + 1,239.72 = 11,856.50.

**Log-normal median.** No flows, normal engine, mu = 0.004, sigma = 0.04 per month, 120
months: the median terminal value is 10,000 x exp(120 x 0.004) = 16,160.74. With 20,000 paths
the standard error of the median is about W sigma sqrt(n) sqrt(pi / 2) / sqrt(paths) = 63; the
tolerance is 4 standard errors.

**Weighted TER.** Two funds at 60 % and 40 % with TERs 0.20 % and 0.10 %: 0.6 x 0.20 + 0.4 x
0.10 = 0.16 % a year.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS

ROOT = Path(__file__).parents[3]
FUND_A, FUND_B = "IE0000000012", "IE0000000020"
DAYS = ("30/04/2026", "29/05/2026")

INSTRUMENT = """\
[{isin}]
name = "Fund {isin}"
instrument_type = "etf"
asset_class = "equity"
currency = "EUR"
as_of = 2026-01-02
domicile = "IE"
replication = "physical_sampling"
distribution = "accumulating"
ter = "{ter}"
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
thousands_separator = "."
encoding = "utf-8"
currency = "EUR"
frequency = "monthly"
{columns}
"""
COLUMN = '[columns."{isin}"]\ninstrument = "{isin}"\nprice_type = "nav"\n'
MEAN = repr(math.log(1.005))
PROJECTION = """
[parameters.projection]
seed = 7
engine = {{ name = "normal" }}
paths = {paths}
periods = {periods}
periods_per_year = 12
goal_real = 11000
percentiles = [5, 50, 95]
early_periods = 6
rebalance_every = 0
flow_timing = "start"
annual_cost = {cost}
inflation = 0.0
capital_gains_tax = 0.0
wealth_tax = 0.0
flows = [{flows}]
"""
DETERMINISTIC = (
    PROJECTION.format(
        paths=10,
        periods=12,
        cost="0.0",
        flows='{ kind = "contribution", amount = 100, first = 0, last = 11, indexed = false }',
    )
    + f"\n[parameters.projection.assets.{FUND_A}]\nmean = {MEAN}\nvolatility = 0.0\n"
)


def _setup(
    tmp: Path, *, projection: str = DETERMINISTIC, two_funds: bool = False,
    ter_b: str = "0.0010", cash: bool = False,
) -> Path:  # fmt: skip
    tmp.mkdir(parents=True, exist_ok=True)
    if two_funds:
        export = (
            "t3;30/04/2026;Acquisto;IE0000000020;4;100,00;EUR;;;;;;\n"
            "t2;30/04/2026;Acquisto;IE0000000012;6;100,00;EUR;;;;;;\n"
            "t1;30/04/2026;Bonifico in entrata;;;;EUR;1.000,00;;;;;\n"
        )
        isins = [FUND_A, FUND_B]
    else:
        deposit = "10.500,00" if cash else "10.000,00"
        export = (
            "t2;30/04/2026;Acquisto;IE0000000012;100;100,00;EUR;;;;;;\n"
            f"t1;30/04/2026;Bonifico in entrata;;;;EUR;{deposit};;;;;\n"
        )
        isins = [FUND_A]
    (tmp / "export.csv").write_text(
        "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
        "Controvalore;Divisa controvalore;Descrizione\n" + export,
        encoding="utf-8",
    )
    (tmp / "prices.csv").write_text(
        "Data;"
        + ";".join(isins)
        + "\n"
        + "".join(f"{d};" + ";".join(["100,00"] * len(isins)) + "\n" for d in DAYS),
        encoding="utf-8",
    )
    (tmp / "prices_mapping.toml").write_text(
        PRICE_MAPPING.format(columns="\n".join(COLUMN.format(isin=i) for i in isins)),
        encoding="utf-8",
    )
    instruments = INSTRUMENT.format(isin=FUND_A, ter="0.0020")
    if two_funds:
        instruments += "\n" + INSTRUMENT.format(isin=FUND_B, ter=ter_b)
    (tmp / "instruments.toml").write_text(instruments, encoding="utf-8")
    broker = (ROOT / "configs/csv_mappings/example_broker.toml").as_posix()
    checks = (ROOT / "configs/checks/example.toml").as_posix()
    config = tmp / "report.toml"
    config.write_text(
        '[experiment]\nname = "projection-report"\nkind = "portfolio_report"\n'
        'hypothesis = "descriptive"\n\n[inputs]\n'
        f'transactions = "{(tmp / "export.csv").as_posix()}"\n'
        f'transactions_mapping = "{broker}"\n'
        f'prices = "{(tmp / "prices.csv").as_posix()}"\n'
        f'prices_mapping = "{(tmp / "prices_mapping.toml").as_posix()}"\n'
        f'instruments = "{(tmp / "instruments.toml").as_posix()}"\nchecks = "{checks}"\n'
        '\n[parameters]\ntransactions_format = "mapped"\n'
        'title = "Projection test"\nbase_currency = "EUR"\nlanguage = "en"\n'
        'flow_timing = "start"\nmax_price_age_days = 0\nreturn_frequency = "none"\n'
        "generated_at = 2026-06-01T09:00:00Z\ntarget_weights = {}\n"
        + projection
        + f'\n[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


def _run(config: Path) -> tuple[dict[str, object], Path]:
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    return dict(result.record), result.output_dir


# ------------------------------------------------------------------------------ by hand
def test_deterministic_plan_by_hand(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path))
    assert record["status"] == "success", record["error"]
    expected = 10_000 * 1.005**12 + 100 * sum(1.005**k for k in range(1, 13))
    assert expected == pytest.approx(11_856.50, abs=0.005)
    terminal = pd.read_csv(out / "terminal.csv", index_col=0)
    for column in ("real", "nominal", "after_tax"):
        assert terminal[column].tolist() == pytest.approx([expected] * 3, abs=0.005)
    fan = pd.read_csv(out / "fan_real.csv", index_col=0)
    assert fan.index[0] == "2026-05-29"  # the projection starts on the report's last date
    assert fan.iloc[0].tolist() == pytest.approx([10_000.0] * 3)  # today's value
    assert record["scalars"]["projection_p_goal"]["value"] == 1.0  # type: ignore[index]
    assert (out / "sensitivity.csv").exists()
    assert record["outputs"]["fan_real.png"]["tag"] == "descriptive"  # type: ignore[index]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "EUR 10,000.00" in html  # initial wealth in the assumptions
    notice = str(record["notice"])
    assert notice.startswith("Scenarios from the stated assumptions, not a forecast.")
    assert notice.endswith("Research analytics, not investment advice.")


def test_log_normal_median(tmp_path: Path) -> None:
    projection = PROJECTION.format(paths=20000, periods=120, cost="0.0", flows="") + (
        f"\n[parameters.projection.assets.{FUND_A}]\nmean = 0.004\nvolatility = 0.04\n"
    )
    record, out = _run(_setup(tmp_path, projection=projection))
    assert record["status"] == "success", record["error"]
    median = pd.read_csv(out / "terminal.csv", index_col=0).loc["P50", "nominal"]
    assert isinstance(median, float)
    expected = 10_000 * math.exp(120 * 0.004)
    se = expected * 0.04 * math.sqrt(120) * math.sqrt(math.pi / 2) / math.sqrt(20_000)
    assert abs(median - expected) < 4 * se


def test_weighted_ter_by_hand(tmp_path: Path) -> None:
    projection = PROJECTION.format(paths=10, periods=12, cost='"ter"', flows="") + (
        f"\n[parameters.projection.assets.{FUND_A}]\nmean = 0.004\nvolatility = 0.04\n"
        f"\n[parameters.projection.assets.{FUND_B}]\nmean = 0.003\nvolatility = 0.03\n"
        f'\n[parameters.projection.correlations]\n"{FUND_A} {FUND_B}" = 0.8\n'
    )
    record, out = _run(_setup(tmp_path, projection=projection, two_funds=True))
    assert record["status"] == "success", record["error"]
    cost = record["scalars"]["projection_annual_cost"]["value"]  # type: ignore[index]
    assert cost == pytest.approx(0.6 * 0.0020 + 0.4 * 0.0010)
    assert (out / "report.html").read_text(encoding="utf-8").count("0.16%") >= 1


def test_the_same_seed_gives_the_same_outputs(tmp_path: Path) -> None:
    projection = PROJECTION.format(paths=200, periods=24, cost="0.0", flows="") + (
        f"\n[parameters.projection.assets.{FUND_A}]\nmean = 0.004\nvolatility = 0.04\n"
    )
    _, first = _run(_setup(tmp_path / "a", projection=projection))
    _, second = _run(_setup(tmp_path / "b", projection=projection))
    for name in ("terminal.csv", "fan_real.csv", "sensitivity.csv", "fan_real.png"):
        assert (
            hashlib.sha256((first / name).read_bytes()).digest()
            == hashlib.sha256((second / name).read_bytes()).digest()
        ), name


# ------------------------------------------------------------------------------ errors
@pytest.mark.parametrize(
    ("change", "match"),
    [
        (
            {"projection": DETERMINISTIC.replace(f"assets.{FUND_A}", "assets.IE0000000020")},
            "IE0000000012",
        ),
        ({"two_funds": True}, "IE0000000020"),  # a held fund without assumptions
        ({"cash": True}, "cash"),  # 500 EUR of cash and no [parameters.projection.cash]
    ],
)
def test_run_errors(tmp_path: Path, change: dict[str, object], match: str) -> None:
    record, _ = _run(_setup(tmp_path, **change))  # type: ignore[arg-type]
    assert record["status"] == "failure"
    assert match in str(record["error"])


def test_missing_correlation_and_unknown_ter(tmp_path: Path) -> None:
    two = PROJECTION.format(paths=10, periods=12, cost='"ter"', flows="") + (
        f"\n[parameters.projection.assets.{FUND_A}]\nmean = 0.004\nvolatility = 0.04\n"
        f"\n[parameters.projection.assets.{FUND_B}]\nmean = 0.003\nvolatility = 0.03\n"
    )
    record, _ = _run(_setup(tmp_path / "corr", projection=two, two_funds=True))
    assert record["status"] == "failure"
    assert "correlation" in str(record["error"])
    with_corr = two + f'\n[parameters.projection.correlations]\n"{FUND_A} {FUND_B}" = 0.8\n'
    record, _ = _run(
        _setup(tmp_path / "ter", projection=with_corr, two_funds=True, ter_b="unknown")
    )
    assert record["status"] == "failure"
    assert "TER" in str(record["error"])


def test_cash_is_an_asset_with_its_own_return(tmp_path: Path) -> None:
    """10,000 in the fund at 1.005 a month and 500 of cash at 0 % for 12 months, no flows."""
    projection = (
        PROJECTION.format(paths=10, periods=12, cost="0.0", flows="")
        + f"\n[parameters.projection.assets.{FUND_A}]\nmean = {MEAN}\nvolatility = 0.0\n"
        + "\n[parameters.projection.cash]\nmean = 0.0\nvolatility = 0.0\n"
    )
    record, out = _run(_setup(tmp_path, projection=projection, cash=True))
    assert record["status"] == "success", record["error"]
    terminal = pd.read_csv(out / "terminal.csv", index_col=0)
    expected = 10_000 * 1.005**12 + 500  # no rebalancing: each asset compounds on its own
    assert terminal["nominal"].tolist() == pytest.approx([expected] * 3, abs=0.005)


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("seed = 7\n", "", "seed"),
        ('engine = { name = "normal" }', 'engine = { name = "magic" }', "name"),
        ("paths = 10\n", "paths = 1\n", "paths"),
        ("annual_cost = 0.0", 'annual_cost = "tre"', "annual_cost"),
        ("sensitivity", "sensitivity", None),
    ],
)
def test_projection_parameters_are_validated(
    tmp_path: Path, old: str, new: str, match: str | None
) -> None:
    text = DETERMINISTIC.replace(old, new)
    if match is None:  # sensitivity is not a key: it is always computed
        bad = DETERMINISTIC.replace("seed = 7\n", "seed = 7\nsensitivity = false\n")
        with pytest.raises(ValidationError, match="sensitivity"):
            validate_experiment(_setup(tmp_path, projection=bad), kinds=KINDS)
        return
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_setup(tmp_path, projection=text), kinds=KINDS)


def test_without_projection_nothing_changes(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, projection=""))
    assert record["status"] == "success", record["error"]
    assert not (out / "terminal.csv").exists()
    assert record["notice"] is None


def test_the_kind_lists_the_projection() -> None:
    assert "projection" in KINDS["portfolio_report"].optional_parameters


ASSET = f"\n[parameters.projection.assets.{FUND_A}]\nmean = 0.004\nvolatility = 0.04\n"
BASE = PROJECTION.format(paths=10, periods=12, cost="0.0", flows="")


@pytest.mark.parametrize(
    ("projection", "match"),
    [
        ("\nprojection = 3\n", r"\[parameters.projection\] must be a table"),
        (BASE.replace("seed = 7", "seed = -1") + ASSET, "seed"),
        (BASE.replace("percentiles = [5, 50, 95]", "percentiles = []") + ASSET, "percentiles"),
        (BASE + "assets = 3\n", "one table per held position"),
        (BASE + ASSET.replace("volatility = 0.04", "volatility = -0.1"), "volatility"),
        (BASE + "correlations = 3\n" + ASSET, "correlations\\] must be a table"),
        (BASE + f'correlations = {{ "{FUND_A}" = 0.5 }}\n' + ASSET, "two different assets"),
        (BASE + f'correlations = {{ "{FUND_A} {FUND_B}" = 2 }}\n' + ASSET, r"\[-1, 1\]"),
        (
            BASE
            + f'correlations = {{ "{FUND_A} {FUND_B}" = 0.5, "{FUND_B} {FUND_A}" = 0.5 }}\n'
            + ASSET,
            "twice",
        ),
    ],
)
def test_more_projection_parameters_are_validated(
    tmp_path: Path, projection: str, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_setup(tmp_path, projection=projection), kinds=KINDS)


def test_ter_cost_with_cash_counts_cash_at_zero(tmp_path: Path) -> None:
    """10,000 in a fund with a 0.20 % TER and 500 of cash: 0.20 % x 10,000 / 10,500."""
    projection = (
        PROJECTION.format(paths=10, periods=12, cost='"ter"', flows="")
        + f"\n[parameters.projection.assets.{FUND_A}]\nmean = {MEAN}\nvolatility = 0.0\n"
        + "\n[parameters.projection.cash]\nmean = 0.0\nvolatility = 0.0\n"
    )
    record, _ = _run(_setup(tmp_path, projection=projection, cash=True))
    assert record["status"] == "success", record["error"]
    cost = record["scalars"]["projection_annual_cost"]["value"]  # type: ignore[index]
    assert cost == pytest.approx(0.0020 * 10_000 / 10_500)
