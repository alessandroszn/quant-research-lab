"""The three experiment kinds, run on the example configs and their synthetic inputs."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pandas as pd
import pytest

from qrlab.backtest import TradeOnSignal, run_backtest, summarize_backtest
from qrlab.cli import main
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.backtest import read_returns
from qrlab.optimization import CostModel

ROOT = Path(__file__).parents[3]
CONFIGS = ROOT / "configs" / "experiments"
WALK_FORWARD = (
    'strategy = { name = "walk_forward", method = "minimum_variance", min_train = 36, step = 12, '
    "max_weight = 0.6 }"
)
WEIGHTS = "initial_weights = { equity_world = 0.25, equity_em = 0.25, bonds = 0.25, cash = 0.25 }"


def _wf(method: str) -> str:
    return (
        f'{{ name = "walk_forward", method = "{method}", min_train = 36, step = 12, '
        "max_weight = 1.0 }"
    )


def _localise(name: str, tmp: Path, **replace: str) -> Path:
    """Copy an example config into ``tmp`` with absolute inputs and a temporary output."""
    text = (CONFIGS / name).read_text(encoding="utf-8")
    text = text.replace('"../../', f'"{(ROOT).as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    raw = tomllib.loads(text)
    text = text.replace(
        f'directory = "{raw["output"]["directory"]}"', f'directory = "{(tmp / "out").as_posix()}"'
    )
    for old, new in replace.items():
        assert old in text, old
        text = text.replace(old, new)
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


def _record(path: Path) -> dict[str, object]:
    return json.loads((path / "record.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_portfolio_report_kind(tmp_path: Path) -> None:
    result = run_experiment(
        _localise("example_portfolio_report.toml", tmp_path), kinds=KINDS, overwrite=False
    )
    assert result.succeeded, result.record["error"]
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert "15.480,00 EUR" in html
    assert "Controlli di salute" in html
    scalars = result.record["scalars"]
    assert scalars["end_value"] == {"value": 15480.0, "tag": "descriptive"}
    assert scalars["twr_total"]["value"] == pytest.approx(0.031656, abs=1e-6)
    findings = pd.read_csv(result.output_dir / "check_findings.csv")
    assert "drift.max_deviation" in set(findings["check"])


def test_portfolio_report_variants_and_errors(tmp_path: Path) -> None:
    monthly = _localise(
        "example_portfolio_report.toml",
        tmp_path,
        **{
            'return_frequency = "none"': 'return_frequency = "monthly"',
            'language = "it"': 'language = "en"',
            'flow_timing = "start"': 'flow_timing = "end"',
            "target_weights = { IE0000000012 = 0.6, cash = 0.4 }": "target_weights = {}",
        },
    )
    result = run_experiment(monthly, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    assert "Health checks" in (result.output_dir / "report.html").read_text(encoding="utf-8")
    usd = _localise(
        "example_portfolio_report.toml",
        tmp_path / "usd",
        **{'base_currency = "EUR"': 'base_currency = "USD"'},
    )
    failed = run_experiment(usd, kinds=KINDS, overwrite=False)
    assert "single-currency" in str(failed.record["error"])
    for old, new, match in (
        (
            "target_weights = { IE0000000012 = 0.6, cash = 0.4 }",
            'target_weights = { a = "x" }',
            "target_weights",
        ),
        ("generated_at = 2026-04-01T09:00:00Z", "generated_at = 2026-04-01T09:00:00", "time zone"),
        ('language = "it"', 'language = "de"', "language"),
    ):
        bad = _localise(
            "example_portfolio_report.toml", tmp_path / f"bad{len(match)}", **{old: new}
        )
        with pytest.raises(ValidationError, match=match):
            validate_experiment(bad, kinds=KINDS)


def test_portfolio_report_needs_prices_after_the_first_trade(tmp_path: Path) -> None:
    prices = tmp_path / "early_prices.csv"
    prices.write_text("Data;IE0000000012\n02/01/2025;50,00\n", encoding="utf-8")
    config = _localise(
        "example_portfolio_report.toml",
        tmp_path,
        **{f"{ROOT.as_posix()}/examples/data/prices.csv": prices.as_posix()},
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert "no price dates" in str(result.record["error"])


def test_backtest_kind_matches_the_library(tmp_path: Path) -> None:
    result = run_experiment(
        _localise("example_backtest.toml", tmp_path), kinds=KINDS, overwrite=False
    )
    assert result.succeeded, result.record["error"]
    assert result.record["outputs"]["values.csv"]["tag"] == "out_of_sample"
    returns = read_returns(
        (ROOT / "examples/data/asset_returns.csv").read_bytes(),
        {
            "date_column": "date",
            "date_format": "%Y-%m-%d",
            "delimiter": ",",
            "decimal_separator": ".",
        },
    )
    hold = run_backtest(
        returns,
        lambda h: None,
        decide_every=1,
        execution_lag=1,
        policy=TradeOnSignal(),
        costs=CostModel(0.001, 1.0),
        taxes=None,
        initial_weights=pd.Series(0.25, index=returns.columns),
        initial_value=Money.of("100000", "EUR"),
        long_only=True,
    )
    buy_and_hold = summarize_backtest(hold, periods_per_year=12)
    scalars = result.record["scalars"]
    assert scalars["net_annualised_volatility"]["value"] < buy_and_hold.net.annualised_volatility


@pytest.mark.parametrize(
    ("strategy", "policy"),
    [
        ('{ name = "buy_and_hold" }', '{ type = "calendar", every = 12 }'),
        (
            '{ name = "trend", asset = "equity_world", cash = "cash", lookback = 12 }',
            '{ type = "trade_on_signal" }',
        ),
        (
            '{ name = "momentum", assets = ["equity_world", "equity_em"], lookback = 6 }',
            '{ type = "threshold", band = 0.05, to = "band" }',
        ),
        (
            _wf("hrp"),
            '{ type = "trade_on_signal" }',
        ),
        (
            _wf("risk_parity"),
            '{ type = "trade_on_signal" }',
        ),
        (
            _wf("maximum_diversification"),
            '{ type = "trade_on_signal" }',
        ),
        (
            _wf("equal_weights"),
            '{ type = "trade_on_signal" }',
        ),
    ],
)
def test_backtest_strategies(tmp_path: Path, strategy: str, policy: str) -> None:
    config = _localise(
        "example_backtest.toml",
        tmp_path,
        **{
            WALK_FORWARD: f"strategy = {strategy}",
            'policy = { type = "trade_on_signal" }': f"policy = {policy}",
            "capital_gains_tax = 0.26": "capital_gains_tax = 0.0",
        },
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    expected = "out_of_sample" if "walk_forward" in strategy else "in_sample"
    assert result.record["scalars"]["net_total_return"]["tag"] == expected


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        (
            'name = "walk_forward", method = "minimum_variance"',
            'name = "walk_forward", method = "kelly"',
            "method",
        ),
        ("max_weight = 0.6", "max_weight = 1.5", "max_weight"),
        ('strategy = { name = "walk_forward"', 'strategy = { name = "pairs"', "name"),
        ('policy = { type = "trade_on_signal" }', 'policy = { type = "weekly" }', "type"),
        ('policy = { type = "trade_on_signal" }', 'policy = { type = "calendar" }', "missing"),
        (
            'policy = { type = "trade_on_signal" }',
            'policy = { type = "threshold", band = 0.05 }',
            "missing",
        ),
        (
            'policy = { type = "trade_on_signal" }',
            'policy = { type = "trade_on_signal", every = 1 }',
            "unknown",
        ),
        ('policy = { type = "trade_on_signal" }', "policy = 1", "policy must be a table"),
        (
            WEIGHTS,
            "initial_weights = {}",
            "initial_weights",
        ),
        (
            WALK_FORWARD,
            "strategy = 3",
            "strategy must be a table",
        ),
        ("execution_lag = 1", "execution_lag = 0", "execution_lag"),
        (
            "costs = { proportional = 0.001, fixed = 1.0 }",
            "costs = { proportional = 0.001 }",
            "missing",
        ),
    ],
)
def test_backtest_config_errors(tmp_path: Path, old: str, new: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(_localise("example_backtest.toml", tmp_path, **{old: new}), kinds=KINDS)


def test_backtest_run_errors(tmp_path: Path) -> None:
    unknown = _localise(
        "example_backtest.toml",
        tmp_path,
        **{
            WALK_FORWARD: 'strategy = { name = "trend", asset = "gold", cash = "cash", '
            "lookback = 12 }"
        },
    )
    result = run_experiment(unknown, kinds=KINDS, overwrite=False)
    assert "not in the returns file" in str(result.record["error"])
    wrong_column = _localise(
        "example_backtest.toml", tmp_path / "x", **{'date_column = "date"': 'date_column = "Date"'}
    )
    assert "no date column" in str(
        run_experiment(wrong_column, kinds=KINDS, overwrite=False).record["error"]
    )


def test_projection_kind(tmp_path: Path) -> None:
    result = run_experiment(
        _localise("example_projection.toml", tmp_path), kinds=KINDS, overwrite=False
    )
    assert result.succeeded, result.record["error"]
    record = result.record
    assert 0.0 < record["scalars"]["p_goal"]["value"] < 1.0
    assert {"fan_real.csv", "fan_real.png", "terminal.csv", "sensitivity.csv"} <= set(
        record["outputs"]
    )
    again = run_experiment(
        _localise("example_projection.toml", tmp_path), kinds=KINDS, overwrite=True
    )
    assert again.record["scalars"] == record["scalars"]  # same seed, same numbers
    normal = _localise(
        "example_projection.toml",
        tmp_path / "n",
        **{
            'engine = { name = "student_t", dof = 5 }': 'engine = { name = "normal" }',
            "sensitivity = true": "sensitivity = false",
            "rebalance_every = 12": "rebalance_every = 0",
        },
    )
    plain = run_experiment(normal, kinds=KINDS, overwrite=False)
    assert plain.succeeded, plain.record["error"]
    assert "sensitivity.csv" not in plain.record["outputs"]


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("correlation = [[1.0, 0.2], [0.2, 1.0]]", "correlation = [[1.0]]", "correlation"),
        ("correlation = [[1.0, 0.2], [0.2, 1.0]]", "correlation = 1", "correlation"),
        ('engine = { name = "student_t", dof = 5 }', 'engine = { name = "student_t" }', "missing"),
        ('engine = { name = "student_t", dof = 5 }', "engine = 1", "engine must be a table"),
        ("flows = [{ kind", "flows = 3 # [{ kind", "flows"),
        (
            "[parameters.assets]\nequity = { mean = 0.005",
            '[parameters.assets]\nequity = { mean = "x"',
            "number",
        ),
        ("percentiles = [5, 25, 50, 75, 95]", "percentiles = 5", "percentiles"),
        ("start = 2026-06-30", "start = 2026-06-30T00:00:00Z", "date"),
        ("sensitivity = true", 'sensitivity = "yes"', "true or false"),
        ("paths = 5000", "paths = 5", "paths"),
        ("goal_real = 200000", 'goal_real = "a lot"', "number"),
        ("flows = [{ kind", "flows = [3, { kind", "each flow"),
        ("[parameters.assets]\n", "[parameters.unused]\n", "missing"),
    ],
)
def test_projection_config_errors(tmp_path: Path, old: str, new: str, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        validate_experiment(
            _localise("example_projection.toml", tmp_path, **{old: new}), kinds=KINDS
        )


def test_cli_runs_every_example(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for name in (
        "example_portfolio_report.toml",
        "example_backtest.toml",
        "example_projection.toml",
    ):
        config = _localise(name, tmp_path / name)
        assert main(["run", str(config)]) == 0, capsys.readouterr().err
    assert main(["kinds"]) == 0
    assert "portfolio_report" in capsys.readouterr().out
    assert {
        "backtest",
        "optimisation",
        "portfolio_report",
        "projection",
        "risk_report",
        "scenario_analysis",
        "study_factor_zoo",
        "study_one_over_n",
        "study_rebalancing",
        "study_volatility_managed",
    } == set(KINDS)


def test_short_backtests_have_no_annualised_figures(tmp_path: Path) -> None:
    one_row = tmp_path / "one.csv"
    one_row.write_text(
        "date,equity_world,equity_em,bonds,cash\n2016-01-31,0.01,0.02,0.0,0.001\n", encoding="utf-8"
    )
    config = _localise(
        "example_backtest.toml",
        tmp_path,
        **{
            f"{ROOT.as_posix()}/examples/data/asset_returns.csv": one_row.as_posix(),
            WALK_FORWARD: 'strategy = { name = "buy_and_hold" }',
        },
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    assert "net_annualised_return" not in result.record["scalars"]
    assert "net_annualised_volatility" not in result.record["scalars"]
    with pytest.raises(ValidationError, match="non-empty text"):
        validate_experiment(
            _localise(
                "example_backtest.toml", tmp_path / "c", **{'currency = "EUR"': 'currency = ""'}
            ),
            kinds=KINDS,
        )


@pytest.mark.parametrize(
    ("key", "match"), [("assets", "assets must be a table"), ("plan", "plan must be a table")]
)
def test_projection_tables_must_be_tables(key: str, match: str) -> None:
    raw = tomllib.loads((CONFIGS / "example_projection.toml").read_text(encoding="utf-8"))
    parameters = dict(raw["parameters"])
    parameters[key] = 1
    with pytest.raises(ValidationError, match=match):
        KINDS["projection"].parse(parameters)


# ------------------------------------------------------------------- notices (design 7.2)
@pytest.mark.parametrize(
    ("name", "start"),
    [
        ("example_projection.toml", "Scenarios from the stated assumptions, not a forecast."),
        ("example_optimisation.toml", "In-sample weights"),
        ("example_scenarios.toml", "What-if stress tests"),
        ("example_backtest.toml", "One historical path"),
        ("example_risk_report.toml", "Risk estimates from past returns"),
    ],
)
def test_kinds_write_their_notice(tmp_path: Path, name: str, start: str) -> None:
    result = run_experiment(_localise(name, tmp_path), kinds=KINDS, overwrite=False)
    notice = result.record["notice"]
    assert isinstance(notice, str)
    assert notice.startswith(start)
    assert notice.endswith("Research analytics, not investment advice.")
    assert (result.output_dir / "NOTICE.txt").read_text(encoding="utf-8") == notice + "\n"


def test_projection_says_when_sensitivity_was_off(tmp_path: Path) -> None:
    on = run_experiment(
        _localise("example_projection.toml", tmp_path / "on"), kinds=KINDS, overwrite=False
    )
    assert "No sensitivity analysis" not in on.record["notice"]
    off = run_experiment(
        _localise(
            "example_projection.toml",
            tmp_path / "off",
            **{"sensitivity = true": "sensitivity = false"},
        ),
        kinds=KINDS,
        overwrite=False,
    )
    assert off.record["notice"].endswith(
        "No sensitivity analysis was run for this projection. "
        "Research analytics, not investment advice."
    )


def test_portfolio_report_without_caveats_has_no_notice_file(tmp_path: Path) -> None:
    # Its HTML report already ends with the not-advice line (tested below).
    result = run_experiment(
        _localise("example_portfolio_report.toml", tmp_path), kinds=KINDS, overwrite=False
    )
    assert result.record["notice"] is None
    assert not (result.output_dir / "NOTICE.txt").exists()


# ------------------------------------------- the not-advice line in every report (design 10.2)
ADVICE = {"en": "not investment advice", "it": "non consulenza finanziaria"}


@pytest.mark.parametrize("name", sorted(p.name for p in CONFIGS.glob("*.toml")))
def test_every_example_output_says_it_is_not_advice(tmp_path: Path, name: str) -> None:
    # The HTML report when the kind writes one (in its language), else NOTICE.txt (English).
    config = _localise(name, tmp_path)
    language = tomllib.loads(config.read_text(encoding="utf-8"))["parameters"].get("language")
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    html = result.output_dir / "report.html"
    shown = html if html.exists() else result.output_dir / "NOTICE.txt"
    assert ADVICE[language or "en"] in shown.read_text(encoding="utf-8")


def test_the_english_portfolio_report_says_it_is_not_advice(tmp_path: Path) -> None:
    config = _localise(
        "example_portfolio_report.toml", tmp_path, **{'language = "it"': 'language = "en"'}
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    assert ADVICE["en"] in html
    assert ADVICE["it"] not in html


def test_the_report_writes_the_data_behind_its_figures(tmp_path: Path) -> None:
    """Design note 12.3a, checked by hand on the example portfolio (flows at the start of day).

    02/01: 10 000 in, 100 units bought at 50 with a fee of 10: 4 990 cash + 5 000 = 9 990.
    30/01: 5 000 in; the units at 55: 9 990 + 5 500 = 15 490.
    27/02: a dividend of 100; the units at 52: 10 090 + 5 200 = 15 290.
    31/03: 50 units sold at 54 with a fee of 10: 12 780 + 2 700 = 15 480.
    TWR: 9 990 / 10 000, 15 490 / 14 990, 15 290 / 15 490, 15 480 / 15 290; the drawdown
    counts the starting value as the first peak.
    """
    result = run_experiment(
        _localise("example_portfolio_report.toml", tmp_path), kinds=KINDS, overwrite=False
    )
    assert result.succeeded, result.record["error"]
    value = pd.read_csv(result.output_dir / "value.csv", index_col=0)
    dates = ["2026-01-02", "2026-01-30", "2026-02-27", "2026-03-31"]
    assert value.index.name == "date"
    assert list(value.index) == dates
    assert list(value.columns) == ["value_EUR"]
    assert value["value_EUR"].tolist() == [9990.0, 15490.0, 15290.0, 15480.0]
    twr = pd.read_csv(result.output_dir / "twr.csv", index_col=0)
    assert twr.index.name == "date"
    assert list(twr.index) == dates
    assert list(twr.columns) == ["cumulative_twr", "drawdown"]
    growth = [0.999, 0.999 * 15490 / 14990, 0.999 * 15290 / 14990, 0.999 * 15480 / 14990]
    assert twr["cumulative_twr"].tolist() == pytest.approx([g - 1 for g in growth], abs=1e-12)
    assert twr["drawdown"].tolist() == pytest.approx(
        [-0.001, 0.0, 15290 / 15490 - 1, 15480 / 15490 - 1], abs=1e-12
    )
    scalars = result.record["scalars"]
    assert twr["cumulative_twr"].iloc[-1] == pytest.approx(scalars["twr_total"]["value"])
    outputs = result.record["outputs"]
    assert outputs["value.csv"]["tag"] == outputs["twr.csv"]["tag"] == "descriptive"


def test_without_periods_there_is_no_twr_table() -> None:
    from qrlab.experiments.kinds.portfolio_report import _figure_tables

    values = pd.Series([100.0], index=pd.DatetimeIndex(["2026-01-02"]), name="value")
    tables = _figure_tables(values, "CHF", pd.Series([], dtype=float))
    assert list(tables) == ["value"]
    value = tables["value"].value
    assert isinstance(value, pd.DataFrame)
    assert list(value.columns) == ["value_CHF"]
