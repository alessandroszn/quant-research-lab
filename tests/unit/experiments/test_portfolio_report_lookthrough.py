"""Look-through and tracking in the ``portfolio_report`` kind (design 7.4b), with hand values.

The synthetic portfolio: deposit 1,000 EUR and buy 12 units of a fund at 50 EUR, which stays at
50 EUR. On every valuation date the fund is 600 / 1,000 = 60 % and cash 40 %.

The fund's holdings are 40 / 25 / 20 / 14 % of its NAV (sum 99 %, as in
``examples/portfolio_report.py``). By hand:

- as reported: 0.6 x (40, 25, 20, 14) % = 24.0 / 15.0 / 12.0 / 8.4 %, and the 1 % the file does
  not explain is 0.6 % of the portfolio;
- normalised: 0.6 x w / 0.99, e.g. 0.6 x 40 / 99 = 24.2424... %, and nothing is unexplained.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from qrlab.core import Currency
from qrlab.core.errors import ValidationError
from qrlab.data import Provenance
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.instruments import Isin
from qrlab.instruments.io import load_holdings_mapping, load_instruments, parse_holdings_csv
from qrlab.lookthrough import WeightTreatment, look_through

ROOT = Path(__file__).parents[3]
FUND = "IE0000000012"  # made-up ISIN with a valid check digit (examples/data/instruments.toml)
DAYS = ("02/01/2026", "30/01/2026", "27/02/2026", "31/03/2026")
HOLDINGS = """\
Synthetic World Equity UCITS ETF
Holdings as of 31/03/2026
Name,ISIN,Weight (%),Country Code,Sector,Currency,Asset Class
Example Corp A,US0000000119,40.0,US,Technology,USD,Equity
Example Corp B,US0000000127,25.0,US,Health Care,USD,Equity
Example Corp C,JP0000000133,20.0,JP,Industrials,JPY,Equity
Example Corp D,DE0000000140,14.0,DE,Financials,EUR,Equity

Synthetic file: the weights deliberately sum to 99 % to show the unexplained bucket.
"""
NAV = ("50,00", "55,00", "52,00", "54,00")
INDEX = ("1000,00", "1100,30", "1040,50", "1080,90")
TRACKING_MAPPING = """\
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
price_type = "{fund_type}"

[columns."WORLD-INDEX"]
instrument = "WORLD-INDEX"
price_type = "{index_type}"
"""


def _setup(
    tmp: Path,
    *,
    holdings: bool = True,
    tracking: bool = False,
    treatment: str | None = "as_reported",
    holdings_as_of: str = "2026-03-31",
    holdings_key: str = FUND,
    fund_type: str = "nav",
    index_type: str = "total_return",
    parameters_extra: str = "",
    inputs_extra: str = "",
    omit_holdings_parameters: bool = False,
) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "export.csv").write_text(
        "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
        "Controvalore;Divisa controvalore;Descrizione\n"
        "t2;02/01/2026;Acquisto;IE0000000012;12;50,00;EUR;;;;;;\n"
        "t1;02/01/2026;Bonifico in entrata;;;;EUR;1.000,00;;;;;\n",
        encoding="utf-8",
    )
    (tmp / "prices.csv").write_text(
        "Data;IE0000000012\n" + "".join(f"{d};50,00\n" for d in DAYS), encoding="utf-8"
    )
    (tmp / "holdings.csv").write_text(HOLDINGS, encoding="utf-8")
    (tmp / "tracking.csv").write_text(
        "Data;IE0000000012;WORLD-INDEX\n"
        + "".join(f"{d};{n};{i}\n" for d, n, i in zip(DAYS, NAV, INDEX, strict=True)),
        encoding="utf-8",
    )
    (tmp / "tracking_mapping.toml").write_text(
        TRACKING_MAPPING.format(fund_type=fund_type, index_type=index_type), encoding="utf-8"
    )
    data = ROOT / "examples" / "data"
    inputs = [
        f'transactions = "{(tmp / "export.csv").as_posix()}"',
        f'transactions_mapping = "{(ROOT / "configs/csv_mappings/example_broker.toml").as_posix()}"',  # noqa: E501
        f'prices = "{(tmp / "prices.csv").as_posix()}"',
        f'prices_mapping = "{(data / "prices_mapping.toml").as_posix()}"',
        f'instruments = "{(data / "instruments.toml").as_posix()}"',
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"',
    ]
    parameters = [
        'title = "Look-through test"',
        'base_currency = "EUR"',
        'language = "en"',
        'flow_timing = "start"',
        "max_price_age_days = 0",
        'return_frequency = "none"',
        "generated_at = 2026-04-01T09:00:00Z",
        "target_weights = {}",
    ]
    if treatment is not None:
        parameters.append(f'lookthrough_treatment = "{treatment}"')
    tables = []
    if holdings:
        mapping = (ROOT / "configs/csv_mappings/example_holdings.toml").as_posix()
        inputs += [
            f'holdings = {{ {holdings_key} = "{(tmp / "holdings.csv").as_posix()}" }}',
            f'holdings_mapping = {{ {holdings_key} = "{mapping}" }}',
        ]
        if not omit_holdings_parameters:
            tables.append(
                f"[parameters.holdings.{holdings_key}]\nas_of = {holdings_as_of}\n"
                'weight_basis = "market value, % of NAV"\nsector_taxonomy = "Synthetic sectors"\n'
            )
    if tracking:
        inputs += [
            f'tracking = {{ {FUND} = "{(tmp / "tracking.csv").as_posix()}" }}',
            f'tracking_mapping = {{ {FUND} = "{(tmp / "tracking_mapping.toml").as_posix()}" }}',
        ]
        tables.append(f'[parameters.tracking.{FUND}]\nindex_hedged_to = "none"\n')
    config = tmp / "report.toml"
    config.write_text(
        '[experiment]\nname = "lt-report"\nkind = "portfolio_report"\n'
        'hypothesis = "descriptive"\n\n'
        "[inputs]\n" + "\n".join(inputs) + "\n" + inputs_extra + "\n"
        "[parameters]\n"
        + "\n".join(parameters)
        + "\n"
        + parameters_extra
        + "\n"
        + "\n".join(tables)
        + "\n"
        f'[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


def _run(config: Path) -> tuple[dict[str, object], Path]:
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    return dict(result.record), result.output_dir


def _weights(out: Path) -> pd.Series:
    rows = pd.read_csv(out / "exposures.csv", index_col=0, keep_default_na=False)
    labels = rows["security"].where(rows["kind"] == "holding", rows["kind"])
    return pd.Series(rows["weight"].to_numpy(), index=labels).groupby(level=0).sum()


# ------------------------------------------------------------------------------ by hand
def test_exposures_as_reported_by_hand(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path))
    assert record["status"] == "success", record["error"]
    weights = _weights(out)
    expected = {
        "US0000000119": 0.24,
        "US0000000127": 0.15,
        "JP0000000133": 0.12,
        "DE0000000140": 0.084,
        "unexplained": 0.006,
        "cash": 0.40,
    }
    assert set(weights.index) == set(expected)
    for key, value in expected.items():
        assert weights[key] == pytest.approx(value, abs=1e-12), key
    scalars = record["scalars"]
    assert scalars["lookthrough_funds"] == {"value": 1.0, "tag": "descriptive"}  # type: ignore[index]
    assert scalars["unexplained_weight"]["value"] == pytest.approx(0.006, abs=1e-12)  # type: ignore[index]
    assert record["outputs"]["exposures.csv"]["tag"] == "descriptive"  # type: ignore[index]
    findings = pd.read_csv(out / "check_findings.csv")
    issuer = findings[findings["check"] == "lookthrough.issuer"]
    assert issuer["severity"].tolist() == ["critical"]  # 24 % in one security, above 10 %
    assert issuer["observed"].tolist() == pytest.approx([0.24])


def test_exposures_normalised_by_hand(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, treatment="normalised"))
    assert record["status"] == "success", record["error"]
    weights = _weights(out)
    assert weights["US0000000119"] == pytest.approx(0.6 * 40 / 99, abs=1e-12)
    assert weights["DE0000000140"] == pytest.approx(0.6 * 14 / 99, abs=1e-12)
    assert weights.get("unexplained", 0.0) == pytest.approx(0.0, abs=1e-12)
    assert record["scalars"]["unexplained_weight"]["value"] == pytest.approx(0.0, abs=1e-12)  # type: ignore[index]


def test_the_kind_matches_the_library(tmp_path: Path) -> None:
    """The kind's exposures equal ``look_through`` called directly, as the Python example does."""
    _, out = _run(_setup(tmp_path))
    content = HOLDINGS.encode("utf-8")
    snapshot = parse_holdings_csv(
        content,
        Provenance.from_json(
            '{"source": "user", "dataset": "h", "url": "file:h.csv", '
            '"retrieved_at": "2026-04-01T00:00:00+00:00", "sha256": "'
            + "0" * 64
            + f'", "size_bytes": {len(content)}, "terms": "synthetic"}}'
        ),
        load_holdings_mapping(ROOT / "configs/csv_mappings/example_holdings.toml"),
        fund=Isin(FUND),
        as_of=date(2026, 3, 31),
        weight_basis="market value, % of NAV",
        sector_taxonomy="Synthetic sectors",
    )
    instruments = {i.isin: i for i in load_instruments(ROOT / "examples/data/instruments.toml")}
    direct = look_through(
        as_of=date(2026, 3, 31),
        position_weights={Isin(FUND): 0.6},
        cash_weights={Currency("EUR"): 0.4},
        instruments=instruments,
        snapshots={Isin(FUND): snapshot},
        treatment=WeightTreatment.AS_REPORTED,
        issuers=None,
    )
    kind_rows = pd.read_csv(out / "exposures.csv", index_col=0, keep_default_na=False)
    direct_rows = direct.rows.fillna("").astype(str)
    assert list(kind_rows.columns) == list(direct.rows.columns)
    assert kind_rows.astype(str).drop(columns="weight").equals(direct_rows.drop(columns="weight"))
    assert kind_rows["weight"].to_numpy() == pytest.approx(direct.rows["weight"].to_numpy())


def test_tracking_difference_by_hand(tmp_path: Path) -> None:
    """NAV 50 -> 54 is +8.00 %, the index 1,000 -> 1,080.9 is +8.09 %: TD = -0.09 %.

    Under a year of data, the TD is not annualised and the tracking checks say why they have
    nothing to measure, instead of being skipped silently.
    """
    record, out = _run(_setup(tmp_path, tracking=True))
    assert record["status"] == "success", record["error"]
    text = " ".join(
        re.sub(r"<[^>]+>", " ", (out / "report.html").read_text(encoding="utf-8")).split()
    )
    assert "IE0000000012 2026-01-02 - 2026-03-31 NAV -0.09% n/a 0.20% n/a" in text
    assert "Tracking difference no held fund has a year of tracking data" in text


def test_tracking_without_holdings(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, holdings=False, treatment=None, tracking=True))
    assert record["status"] == "success", record["error"]
    assert record["scalars"]["lookthrough_funds"]["value"] == 0.0  # type: ignore[index]
    weights = _weights(out)
    assert weights["not_looked_through"] == pytest.approx(0.6)


def test_no_holdings_no_tracking_no_new_outputs(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, holdings=False, treatment=None))
    assert record["status"] == "success", record["error"]
    assert not (out / "exposures.csv").exists()
    assert "lookthrough_funds" not in record["scalars"]  # type: ignore[operator]


# ------------------------------------------------------------------------------ validation
@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"treatment": None}, "lookthrough_treatment"),
        ({"holdings": False}, "lookthrough_treatment"),
        ({"treatment": "magic"}, "lookthrough_treatment"),
        ({"omit_holdings_parameters": True}, r"parameters\.holdings"),
        ({"holdings_key": "IE0000000013"}, "invalid ISIN"),
        (
            {"parameters_extra": "[parameters.holdings.IE0000000020]\nas_of = 2026-03-31\n"},
            r"parameters\.holdings",
        ),
        ({"inputs_extra": 'tracking = { IE0000000012 = "x.csv" }\n'}, "tracking"),
    ],
)
def test_config_errors(tmp_path: Path, change: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_setup(tmp_path, **change), kinds=KINDS)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"holdings_key": "IE0000000020"}, "not held"),
        ({"holdings_as_of": "2026-04-30"}, "after"),
        ({"tracking": True, "fund_type": "price"}, "NAV or total return"),
        ({"tracking": True, "index_type": "price"}, "index series must be total return"),
    ],
)
def test_run_errors(tmp_path: Path, change: dict[str, object], match: str) -> None:
    record, _ = _run(_setup(tmp_path, **change))  # type: ignore[arg-type]
    assert record["status"] == "failure"
    assert match in str(record["error"])


def test_a_tracking_file_needs_the_fund_column(tmp_path: Path) -> None:
    config = _setup(tmp_path, tracking=True)
    mapping = tmp_path / "tracking_mapping.toml"
    mapping.write_text(
        mapping.read_text(encoding="utf-8").replace(
            '[columns."IE0000000012"]\ninstrument = "IE0000000012"',
            '[columns."IE0000000012"]\ninstrument = "OTHER"',
        ),
        encoding="utf-8",
    )
    record, _ = _run(config)
    assert record["status"] == "failure"
    assert "column for IE0000000012" in str(record["error"])


def test_the_kind_lists_the_lookthrough_inputs() -> None:
    kind = KINDS["portfolio_report"]
    assert kind.input_groups[2:] == ("holdings", "holdings_mapping", "tracking", "tracking_mapping")
    assert kind.optional_parameters[1:4] == ("lookthrough_treatment", "holdings", "tracking")


def test_an_issuer_map_in_the_kind_by_hand(tmp_path: Path) -> None:
    """Corp A (40 %) and Corp B (25 %) of one issuer, through a fund at 60 %: 0.6 x 0.65 = 39 %."""
    issuers = tmp_path / "issuers.csv"
    issuers.write_text(
        "isin,issuer\nUS0000000119,Example Group\nUS0000000127,Example Group\n", encoding="utf-8"
    )
    record, out = _run(_setup(tmp_path / "run", inputs_extra=f'issuers = "{issuers.as_posix()}"\n'))
    assert record["status"] == "success", record["error"]
    findings = pd.read_csv(out / "check_findings.csv")
    issuer = findings[findings["check"] == "lookthrough.issuer"]
    assert issuer["observed"].tolist() == pytest.approx([0.39])
    rows = pd.read_csv(out / "exposures.csv", index_col=0, keep_default_na=False)
    grouped = rows.groupby("issuer")["weight"].sum()
    assert grouped["Example Group"] == pytest.approx(0.39)
    assert "issuers" in record["inputs"]  # type: ignore[operator]


def test_an_issuer_map_needs_holdings(tmp_path: Path) -> None:
    issuers = tmp_path / "issuers.csv"
    issuers.write_text("isin,issuer\nUS0000000119,Example Group\n", encoding="utf-8")
    config = _setup(
        tmp_path / "run",
        holdings=False,
        treatment=None,
        inputs_extra=f'issuers = "{issuers.as_posix()}"\n',
    )
    with pytest.raises(ValidationError, match="issuers file"):
        validate_experiment(config, kinds=KINDS)


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        ("holdings = 3\n", r"\[parameters.holdings\] must hold one table per fund ISIN"),
        (f"holdings = {{ {FUND} = 3 }}\n", r"\[parameters.holdings.IE0000000012\] must be a table"),
    ],
)
def test_holdings_parameters_must_be_tables(tmp_path: Path, extra: str, match: str) -> None:
    config = _setup(tmp_path, holdings=False, treatment=None, parameters_extra=extra)
    with pytest.raises(ValidationError, match=match):
        validate_experiment(config, kinds=KINDS)


def test_tracking_needs_the_fund_in_the_instruments_file(tmp_path: Path) -> None:
    config = _setup(tmp_path, holdings=False, treatment=None, tracking=True)
    other = tmp_path / "instruments_other.toml"
    text = (ROOT / "examples/data/instruments.toml").read_text(encoding="utf-8")
    other.write_text(text.replace("IE0000000012", "IE0000000020"), encoding="utf-8")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            (ROOT / "examples/data/instruments.toml").as_posix(), other.as_posix()
        ),
        encoding="utf-8",
    )
    record, _ = _run(config)
    assert record["status"] == "failure"
    assert "not in the instruments file" in str(record["error"])
