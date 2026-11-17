"""Loss rules and the income tax reach the configs (design note 11.5).

Hand case of the income tax: one asset with zero mean and zero volatility, one yearly period,
€10,000, an income tax of 26 % on a taxable yield of 2 %: the terminal wealth is
10,000 x (1 - 0.26 x 0.02) = €9,948. The loss rules are checked by hand in
``tests/unit/simulation/test_losses.py`` (the 8.6b note's case); here the kinds must give
exactly the library's result.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from qrlab.backtest import run_backtest
from qrlab.core.errors import ValidationError
from qrlab.core.money import Money
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds.backtest import read_returns
from qrlab.optimization.rebalancing import CalendarPolicy, CostModel
from qrlab.simulation import LossRules, TaxModel

ROOT = Path(__file__).parents[3]

PROJECTION = """\
[experiment]
name = "income-tax"
kind = "projection"
hypothesis = "descriptive"
seed = 1

[inputs]

[parameters]
engine = {{ name = "normal" }}
paths = 10
periods = 1
start = 2026-12-31
goal_real = 1
percentiles = [50]
early_periods = 1
sensitivity = false
correlation = [[1.0]]
flows = []

[parameters.assets]
fund = {{ mean = 0.0, volatility = 0.0, weight = 1.0 }}

[parameters.plan]
initial_wealth = 10000
currency = "EUR"
periods_per_year = 1
flow_timing = "end"
rebalance_every = 0
annual_cost = 0.0
inflation = 0.0
capital_gains_tax = 0.0
wealth_tax = 0.0
{extra}
[output]
directory = "{out}"
"""


def _projection(tmp: Path, extra: str) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    config = tmp / "projection.toml"
    config.write_text(PROJECTION.format(extra=extra, out=(tmp / "out").as_posix()), "utf-8")
    return config


def test_income_tax_in_the_projection_kind_by_hand(tmp_path: Path) -> None:
    result = run_experiment(
        _projection(tmp_path, "income_tax_rate = 0.26\ntaxable_yield = 0.02\n"),
        kinds=KINDS,
        overwrite=False,
    )
    assert result.succeeded, result.record["error"]
    terminal = pd.read_csv(result.output_dir / "terminal.csv")
    assert terminal.filter(like="nominal").iloc[0, 0] == pytest.approx(9948.0, abs=1e-9)
    plain = run_experiment(_projection(tmp_path / "plain", ""), kinds=KINDS, overwrite=False)
    assert pd.read_csv(plain.output_dir / "terminal.csv").filter(like="nominal").iloc[
        0, 0
    ] == pytest.approx(10000.0)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("income_tax_rate = 0.26\n", "go together"),
        ("income_tax_rate = 1.5\ntaxable_yield = 0.02\n", "income_tax_rate"),
        ("losses = { carry_years = -1, fund_assets = [] }\n", "carry_years"),
        ('losses = { carry_years = 4, fund_assets = "fund" }\n', "a list of asset names"),
        ("losses = { carry_years = 4 }\n", "fund_assets"),
        ("losses = 4\n", "losses must be a table"),
    ],
)
def test_projection_key_errors(tmp_path: Path, extra: str, message: str) -> None:
    config = _projection(tmp_path, extra)
    try:
        validate_experiment(config, kinds=KINDS)
    except ValidationError as error:
        assert message in str(error)  # noqa: PT017 - refused when the config is read
        return
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert message in str(result.record["error"])


def test_an_unknown_fund_asset_fails_the_projection(tmp_path: Path) -> None:
    config = _projection(
        tmp_path,
        'capital_gains_tax_placeholder = 0\nlosses = { carry_years = 4, fund_assets = ["x"] }\n',
    )
    text = config.read_text(encoding="utf-8").replace("capital_gains_tax_placeholder = 0\n", "")
    text = text.replace("capital_gains_tax = 0.0", "capital_gains_tax = 0.26")
    config.write_text(text, encoding="utf-8")
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "fund_assets ['x'] are not assets" in str(result.record["error"])


# ------------------------------------------------------------------------------- backtest
def _backtest(tmp: Path, losses: str) -> Path:
    text = (ROOT / "configs/experiments/example_backtest.toml").read_text(encoding="utf-8")
    text = text.replace(
        'directory = "../../results/example-walk-forward-minvar"',
        f'directory = "{(tmp / "out").as_posix()}"',
    )
    text = text.replace('"../../', f'"{ROOT.as_posix()}/')
    text = text.replace(
        'strategy = { name = "walk_forward", method = "minimum_variance", min_train = 36, '
        "step = 12, max_weight = 0.6 }",
        'strategy = { name = "buy_and_hold" }',
    ).replace('policy = { type = "trade_on_signal" }', 'policy = { type = "calendar", every = 1 }')
    text = text.replace("[output]", losses + "[output]")
    tmp.mkdir(parents=True, exist_ok=True)
    config = tmp / "backtest.toml"
    config.write_text(text, encoding="utf-8")
    return config


LOSSES = '[parameters.losses]\ncarry_years = 4\nfund_assets = ["equity_world"]\n\n'


def test_losses_in_the_backtest_kind_match_the_library(tmp_path: Path) -> None:
    result = run_experiment(_backtest(tmp_path, LOSSES), kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    returns = read_returns(
        (ROOT / "examples/data/asset_returns.csv").read_bytes(),
        {"date_column": "date", "date_format": "%Y-%m-%d", "delimiter": ",",
         "decimal_separator": "."},
    )  # fmt: skip
    expected = run_backtest(
        returns,
        lambda h: None,
        decide_every=1,
        execution_lag=1,
        policy=CalendarPolicy(1),
        costs=CostModel(0.001, 1.0),
        taxes=TaxModel(0.26, 0.0, losses=LossRules(4, frozenset({"equity_world"}))),
        initial_weights=pd.Series(0.25, index=returns.columns),
        initial_value=Money.of("100000", "EUR"),
        long_only=True,
    )
    values = pd.read_csv(result.output_dir / "values.csv", index_col=0)
    assert values["net"].iloc[-1] == pytest.approx(float(expected.net_values.iloc[-1]), rel=1e-12)
    plain = run_experiment(_backtest(tmp_path / "plain", ""), kinds=KINDS, overwrite=False)
    other = pd.read_csv(plain.output_dir / "values.csv", index_col=0)
    assert other["net"].iloc[-1] != values["net"].iloc[-1]  # the rules change the taxes


def test_backtest_loss_errors(tmp_path: Path) -> None:
    bad = '[parameters.losses]\ncarry_years = 4\nfund_assets = ["gold"]\n\n'
    result = run_experiment(_backtest(tmp_path, bad), kinds=KINDS, overwrite=False)
    assert not result.succeeded
    assert "fund_assets ['gold'] are not assets" in str(result.record["error"])
    with pytest.raises(ValidationError, match="losses"):
        validate_experiment(
            _backtest(tmp_path / "b", "[parameters.losses]\ncarry_years = 4\n\n"), kinds=KINDS
        )
