"""Kinds risk_report, scenario_analysis and optimisation: hand-checked cases and the examples."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.workspace import config_template

ROOT = Path(__file__).parents[3]
FORMAT = (
    'returns_format = { date_column = "date", date_format = "%Y-%m-%d", delimiter = ",", '
    'decimal_separator = "." }'
)


def _returns(tmp: Path, columns: dict[str, list[float]]) -> Path:
    n = len(next(iter(columns.values())))
    frame = pd.DataFrame(columns, index=pd.date_range("2020-01-31", periods=n, freq="ME"))
    frame.index.name = "date"
    path = tmp / "returns.csv"
    frame.to_csv(path)
    return path


def _config(tmp: Path, kind: str, inputs: dict[str, Path], parameters: str, name: str) -> Path:
    lines = "\n".join(f'{k} = "{v.as_posix()}"' for k, v in inputs.items())
    text = (
        f'[experiment]\nname = "{name}"\nkind = "{kind}"\nhypothesis = "descriptive"\n\n'
        f"[inputs]\n{lines}\n\n[parameters]\n{parameters}\n\n"
        f'[output]\ndirectory = "{(tmp / "out" / name).as_posix()}"\n'
    )
    path = tmp / f"{name}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _record(result_dir: Path) -> dict[str, object]:
    return json.loads((result_dir / "record.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------------- risk_report
RISK = f"""confidence = 0.95
periods_per_year = 12
{FORMAT}
weights = {{ a = 0.5, b = 0.5 }}
covariance = {{ estimator = "sample" }}
filtered = {{ decay = 0.9, warmup = 10 }}
backtest = {{ window = 20, model = "normal" }}"""


def test_risk_contributions_by_hand(tmp_path: Path) -> None:
    # b moves exactly twice as much as a: perfectly correlated, sigma_b = 2 sigma_a.
    # 50/50 weights: vol = 0.5 sigma_a + 0.5 sigma_b, so a contributes 1/3 and b 2/3.
    a = [0.01 if i % 2 == 0 else -0.01 for i in range(40)]
    path = _returns(tmp_path, {"a": a, "b": [2 * x for x in a]})
    result = run_experiment(
        _config(tmp_path, "risk_report", {"returns": path}, RISK, "risk"),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    contributions = pd.read_csv(result.output_dir / "contributions.csv", index_col="asset")
    assert contributions["volatility_share"].to_numpy() == pytest.approx([1 / 3, 2 / 3])
    sigma_a = math.sqrt(40 * 0.0001 / 39)
    vol = 0.5 * sigma_a + 0.5 * 2 * sigma_a
    scalars = result.record["scalars"]
    assert scalars["volatility_annual"]["value"] == pytest.approx(vol * math.sqrt(12))
    assert scalars["volatility_annual"]["tag"] == "descriptive"
    assert scalars["kupiec_pvalue"]["tag"] == "out_of_sample"
    var_es = pd.read_csv(result.output_dir / "var_es.csv", index_col="method")
    assert list(var_es.index) == ["historical", "normal", "cornish_fisher", "filtered_historical"]
    # +-1.5 % returns have excess kurtosis -2: Cornish-Fisher is not a quantile, left empty.
    assert var_es["var"].isna()["cornish_fisher"]
    assert "not a quantile" in str(var_es.loc["cornish_fisher", "note"])
    # Portfolio returns are +-1.5 %: the historical 95 % VaR is a 1.5 % loss.
    assert var_es.loc["historical", "var"] == pytest.approx(0.015)
    path_table = pd.read_csv(result.output_dir / "var_backtest.csv", index_col=0)
    assert len(path_table) == 40 - 20
    assert scalars["backtest_exceedances"]["value"] == float(path_table["exceedance"].sum())


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("confidence = 0.95", "confidence = 0.4", "confidence must be in"),
        ('model = "normal"', 'model = "garch"', "model"),
        ("weights = { a = 0.5, b = 0.5 }", "weights = {}", "non-empty table"),
        ('estimator = "sample"', 'estimator = "ewma"', "missing"),
        ('estimator = "sample"', 'estimator = "magic"', "estimator"),
        ('covariance = { estimator = "sample" }', 'covariance = "sample"', "covariance must be a"),
    ],
)
def test_risk_parameters_are_validated(tmp_path: Path, old: str, new: str, message: str) -> None:
    path = _returns(tmp_path, {"a": [0.01, -0.01] * 20, "b": [0.02, -0.02] * 20})
    config = _config(tmp_path, "risk_report", {"returns": path}, RISK.replace(old, new), "bad")
    with pytest.raises(ValidationError, match=message):
        validate_experiment(config, kinds=KINDS)


def test_risk_weights_must_match_the_assets(tmp_path: Path) -> None:
    path = _returns(tmp_path, {"a": [0.01, -0.01] * 20, "c": [0.02, -0.02] * 20})
    result = run_experiment(
        _config(tmp_path, "risk_report", {"returns": path}, RISK, "mismatch"),
        kinds=KINDS,
        overwrite=False,
    )
    assert not result.succeeded
    assert "must cover exactly the assets" in str(result.record["error"])


def test_risk_with_ewma_and_other_backtest_models(tmp_path: Path, rng: np.random.Generator) -> None:
    returns = {"a": list(rng.standard_t(4, 80) * 0.03), "b": list(rng.normal(0.002, 0.02, 80))}
    path = _returns(tmp_path, returns)
    params = RISK.replace('estimator = "sample"', 'estimator = "ewma", decay = 0.94, demean = true')
    params = params.replace('model = "normal"', 'model = "historical"')
    result = run_experiment(
        _config(tmp_path, "risk_report", {"returns": path}, params, "hist"),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    var_es = pd.read_csv(result.output_dir / "var_es.csv", index_col="method")
    assert var_es["var"].notna().all()  # fat tails: Cornish-Fisher is defined here
    # A Cornish-Fisher backtest stops with the library's reason when a window is not valid.
    flat = _returns(tmp_path, {"a": [0.01, -0.01] * 30, "b": [0.02, -0.02] * 30})
    params = params.replace('model = "historical"', 'model = "cornish_fisher"')
    result = run_experiment(
        _config(tmp_path, "risk_report", {"returns": flat}, params, "cf"),
        kinds=KINDS,
        overwrite=False,
    )
    assert not result.succeeded
    assert "not a quantile" in str(result.record["error"])


# --------------------------------------------------------------------------------- optimisation
def _optimisation(method: str, bounds: str = "{ min = 0.0, max = 1.0 }") -> str:
    return f"""periods_per_year = 12
{FORMAT}
method = {method}
covariance = {{ estimator = "sample" }}
bounds = {bounds}"""


def test_minimum_variance_by_hand(tmp_path: Path) -> None:
    # Uncorrelated, zero-mean returns with variances in ratio 1:4: w is proportional to 1/var,
    # so (0.8, 0.2).
    a = [0.1, -0.1, 0.1, -0.1] * 6
    b = [0.2, 0.2, -0.2, -0.2] * 6
    path = _returns(tmp_path, {"a": a, "b": b})
    result = run_experiment(
        _config(
            tmp_path,
            "optimisation",
            {"returns": path},
            _optimisation('{ name = "minimum_variance" }'),
            "minvar",
        ),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    weights = pd.read_csv(result.output_dir / "weights.csv", index_col="asset")["weight"]
    assert weights.to_numpy() == pytest.approx([0.8, 0.2], abs=1e-6)
    assert result.record["outputs"]["weights.csv"]["tag"] == "in_sample"


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ('{ name = "equal_weights" }', [0.5, 0.5]),
        ('{ name = "risk_parity" }', [2 / 3, 1 / 3]),  # 1/sigma: sigma_b = 2 sigma_a
        ('{ name = "hrp" }', [0.8, 0.2]),  # two uncorrelated clusters: inverse variance
        ('{ name = "maximum_diversification" }', [2 / 3, 1 / 3]),
        ('{ name = "mean_variance", risk_aversion = 4.0 }', None),
        ('{ name = "maximum_sharpe", risk_free_per_period = 0.0 }', None),
    ],
)
def test_every_method_runs(tmp_path: Path, method: str, expected: list[float] | None) -> None:
    a = [0.11, -0.09, 0.11, -0.09] * 6
    b = [0.21, 0.21, -0.19, -0.19] * 6
    path = _returns(tmp_path, {"a": a, "b": b})
    result = run_experiment(
        _config(tmp_path, "optimisation", {"returns": path}, _optimisation(method), "m"),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    weights = pd.read_csv(result.output_dir / "weights.csv", index_col="asset")["weight"]
    assert weights.sum() == pytest.approx(1.0)
    if expected is not None:
        assert weights.to_numpy() == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    ("method", "bounds", "message"),
    [
        ('{ name = "magic" }', "{ min = 0.0, max = 1.0 }", "name"),
        ('{ name = "mean_variance" }', "{ min = 0.0, max = 1.0 }", "missing"),
        ('{ name = "equal_weights" }', "{ min = 0.5, max = 0.4 }", "min <= max"),
        ('"x"', "{ min = 0.0, max = 1.0 }", "method must be a table"),
    ],
)
def test_optimisation_parameters_are_validated(
    tmp_path: Path, method: str, bounds: str, message: str
) -> None:
    path = _returns(tmp_path, {"a": [0.01, -0.01] * 5, "b": [0.02, -0.02] * 5})
    config = _config(
        tmp_path, "optimisation", {"returns": path}, _optimisation(method, bounds), "x"
    )
    with pytest.raises(ValidationError, match=message):
        validate_experiment(config, kinds=KINDS)


# ---------------------------------------------------------------------------- scenario_analysis
SCENARIOS = """[equity_minus_30]
kind = "hypothetical"
description = "Equity -30 %"
factors = { "Mkt-RF" = -0.30 }
positions = {}
currencies = {}

[usd_minus_10]
kind = "hypothetical"
description = "USD -10 %"
factors = {}
positions = {}
currencies = { USD = -0.10 }

[replay]
kind = "historical"
description = "Two months"
start = 2020-01-31
end = 2020-03-31
"""

SCENARIO_PARAMS = (
    'as_of = 2026-10-30\nvalue = 100000\ncurrency = "EUR"\nposition_returns_currency = "EUR"\n'
    + FORMAT.replace("returns_format", "csv_format")
)


def _stress_files(tmp: Path) -> dict[str, Path]:
    files = {
        "holdings": "holding,type,weight,currency\nIE0000000012,position,0.6,EUR\n"
        "US0000000002,position,0.3,USD\nEUR,cash,0.1,EUR\n",
        "betas": "holding,Mkt-RF\nIE0000000012,1.0\nUS0000000002,0.5\n",
        "position_returns": "date,IE0000000012\n2020-01-31,0.0\n2020-02-29,0.1\n2020-03-31,-0.2\n",
        "factors": "date,Mkt-RF\n2020-01-31,0.0\n2020-02-29,0.05\n2020-03-31,-0.1\n",
        "fx": "date,USD\n2020-01-31,0.0\n2020-02-29,0.0\n2020-03-31,0.02\n",
    }
    paths = {}
    for name, text in files.items():
        paths[name] = tmp / f"{name}.csv"
        paths[name].write_text(text, encoding="utf-8")
    paths["scenarios"] = tmp / "scenarios.toml"
    paths["scenarios"].write_text(SCENARIOS, encoding="utf-8")
    return paths


def test_scenarios_by_hand(tmp_path: Path) -> None:
    paths = _stress_files(tmp_path)
    result = run_experiment(
        _config(tmp_path, "scenario_analysis", paths, SCENARIO_PARAMS, "stress"),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    summary = pd.read_csv(result.output_dir / "scenarios.csv", index_col="scenario")
    # Equity -30 %: 0.6 x (1.0 x -30 %) + 0.3 x (0.5 x -30 %) = -22.5 %, -22,500 EUR.
    assert summary.loc["equity_minus_30", "portfolio_return"] == pytest.approx(-0.225)
    assert summary.loc["equity_minus_30", "pnl"] == pytest.approx(-22500.0)
    # USD -10 % hits only the USD position: 0.3 x -10 % = -3 %.
    assert summary.loc["usd_minus_10", "portfolio_return"] == pytest.approx(-0.03)
    # Replay: IE own series 1.1 x 0.8 - 1 = -12 %; US by proxy 0.5 x (5 %, -10 %) compounded
    # = 1.025 x 0.95 - 1 = -2.625 %, then USD 1.0 x 1.02 - 1 = 2 %: (0.97375 x 1.02) - 1.
    us = (1.025 * 0.95) * 1.02 - 1
    assert summary.loc["replay", "portfolio_return"] == pytest.approx(0.6 * -0.12 + 0.3 * us)
    positions = pd.read_csv(result.output_dir / "positions.csv")
    methods = positions[positions["scenario"] == "replay"].set_index("holding")["method"]
    assert methods.to_dict() == {
        "IE0000000012": "direct",
        "US0000000002": "proxy",
        "cash EUR": "cash",
    }


def test_scenarios_without_optional_inputs(tmp_path: Path) -> None:
    paths = _stress_files(tmp_path)
    required = {k: paths[k] for k in ("holdings", "scenarios")}
    scenarios = SCENARIOS.split("[replay]")[0].replace('{ "Mkt-RF" = -0.30 }', "{}")
    paths["scenarios"].write_text(scenarios, encoding="utf-8")
    result = run_experiment(
        _config(tmp_path, "scenario_analysis", required, SCENARIO_PARAMS, "bare"),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    summary = pd.read_csv(result.output_dir / "scenarios.csv", index_col="scenario")
    assert summary.loc["usd_minus_10", "portfolio_return"] == pytest.approx(-0.03)


@pytest.mark.parametrize(
    ("holdings", "message"),
    [
        ("holding,type,weight\nIE0000000012,position,1.0\n", "lacks columns"),
        ("holding,type,weight,currency\nIE0000000012,bond,1.0,EUR\n", "type must be"),
        (
            "holding,type,weight,currency\nIE0000000012,position,0.5,EUR\n"
            "IE0000000012,position,0.5,EUR\n",
            "listed twice",
        ),
    ],
)
def test_holdings_are_validated(tmp_path: Path, holdings: str, message: str) -> None:
    paths = _stress_files(tmp_path)
    paths["holdings"].write_text(holdings, encoding="utf-8")
    result = run_experiment(
        _config(tmp_path, "scenario_analysis", paths, SCENARIO_PARAMS, "h"),
        kinds=KINDS,
        overwrite=False,
    )
    assert not result.succeeded
    assert message in str(result.record["error"])


def test_betas_need_a_holding_column(tmp_path: Path) -> None:
    paths = _stress_files(tmp_path)
    paths["betas"].write_text("isin,Mkt-RF\nIE0000000012,1.0\n", encoding="utf-8")
    result = run_experiment(
        _config(tmp_path, "scenario_analysis", paths, SCENARIO_PARAMS, "b"),
        kinds=KINDS,
        overwrite=False,
    )
    assert not result.succeeded
    assert "'holding' column" in str(result.record["error"])


def test_unknown_and_optional_inputs(tmp_path: Path) -> None:
    paths = _stress_files(tmp_path)
    paths["typo"] = paths["fx"]
    config = _config(tmp_path, "scenario_analysis", paths, SCENARIO_PARAMS, "u")
    with pytest.raises(ValidationError, match=r"unknown \['typo'\]"):
        validate_experiment(config, kinds=KINDS)
    template = config_template(KINDS["scenario_analysis"])
    assert '# fx = "../data/FILL-IN"  # optional' in template
    bad = _config(
        tmp_path,
        "scenario_analysis",
        _stress_files(tmp_path),
        SCENARIO_PARAMS.replace("value = 100000", "value = 0"),
        "v",
    )
    with pytest.raises(ValidationError, match="value must be positive"):
        validate_experiment(bad, kinds=KINDS)


# ------------------------------------------------------------------------------ the examples
@pytest.mark.parametrize(
    "name", ["example_risk_report.toml", "example_optimisation.toml", "example_scenarios.toml"]
)
def test_examples_run(tmp_path: Path, name: str) -> None:
    text = (ROOT / "configs" / "experiments" / name).read_text(encoding="utf-8")
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + f'directory = "{(tmp_path / "out").as_posix()}"' + text[end + 1 :]
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    result = run_experiment(path, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    assert _record(result.output_dir)["status"] == "success"
