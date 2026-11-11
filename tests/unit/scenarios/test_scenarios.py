"""Stress tests: historical replays and hypothetical shocks. All data synthetic.

Hand values (design note 3.2):

- A at 60 %, EUR cash 40 %, A falls 30 %: portfolio -18 %;
- a USD position at 50 %, local -10 %, USD -5 %: base 0.9 x 0.95 - 1 = -14.5 %, portfolio
  -7.25 %; hedged to EUR: -10 % and -5 %; USD cash at 20 % with USD -5 %: -1 %;
- proxy with beta 1.2 and market -10 % then -10 %: 1 - 0.88^2 = -22.56 %;
- a position without history or betas at 25 % is not covered and excluded;
- market -30 % with betas 0.8 and 1.1 at weights 0.5 and 0.3: -21.9 %.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.identifiers import Isin
from qrlab.scenarios import (
    HistoricalScenario,
    HypotheticalScenario,
    MarketData,
    PositionSeries,
    StressPortfolio,
    load_scenarios,
    run_scenario,
)
from support.checks import A, B, C, D

EUR, USD = Currency("EUR"), Currency("USD")
ROOT = Path(__file__).parents[3]
WINDOW = HistoricalScenario("crash", "Synthetic crash", date(2020, 1, 31), date(2020, 3, 31))
MONTHS = pd.DatetimeIndex(pd.to_datetime(["2019-12-31", "2020-01-31", "2020-02-29", "2020-03-31"]))


def _portfolio(
    weights: Mapping[Isin, float],
    cash: Mapping[Currency, float] | None = None,
    currencies: Mapping[Isin, Currency] | None = None,
) -> StressPortfolio:
    return StressPortfolio(
        as_of=date(2026, 6, 30),
        value=Money.of("100000", "EUR"),
        position_weights=weights,
        cash_weights=cash or {},
        exposure_currencies={i: (currencies or {}).get(i, EUR) for i in weights},
    )


def _monthly(values: list[float]) -> pd.Series:
    return pd.Series(values, index=MONTHS)


def _market(
    positions: Mapping[Isin, PositionSeries] | None = None,
    factors: pd.DataFrame | None = None,
    betas: pd.DataFrame | None = None,
    fx: Mapping[Currency, pd.Series] | None = None,
) -> MarketData:
    return MarketData(
        positions or {}, factors if factors is not None else pd.DataFrame(), betas, fx or {}
    )


def _crash(fall: float) -> PositionSeries:
    """Return a series flat except one month, so the window return is exactly ``fall``."""
    return PositionSeries(_monthly([0.05, 0.0, fall, 0.0]), EUR)


# --------------------------------------------------------------------------- historical
def test_direct_replay_hand_example() -> None:
    result = run_scenario(WINDOW, _portfolio({A: 0.6}, {EUR: 0.4}), _market({A: _crash(-0.30)}))
    assert result.portfolio_return == pytest.approx(-0.18)
    assert result.pnl == Money.of("-18000.00", "EUR")
    row = result.rows[0]
    assert row.method == "direct"
    assert row.base_return == pytest.approx(-0.3)
    assert row.contribution == pytest.approx(-0.18)
    assert (result.first_date, result.last_date) == (date(2020, 2, 29), date(2020, 3, 31))
    assert result.rows[1].method == "cash"
    assert result.not_covered_weight == 0.0
    assert result.notes == ()


@pytest.mark.parametrize(("weight", "shock"), [(1.0, -0.2), (0.3, -0.5), (0.75, 0.1)])
def test_single_position_gives_weight_times_shock(weight: float, shock: float) -> None:
    cash = {EUR: 1.0 - weight} if weight < 1 else {}
    result = run_scenario(WINDOW, _portfolio({A: weight}, cash), _market({A: _crash(shock)}))
    assert result.portfolio_return == pytest.approx(weight * shock)


def test_currency_effect_hand_example() -> None:
    usd_series = PositionSeries(_monthly([0.0, 0.0, -0.10, 0.0]), USD)
    fx = {USD: _monthly([0.0, 0.0, -0.05, 0.0])}
    portfolio = _portfolio({A: 0.5}, {EUR: 0.3, USD: 0.2}, {A: USD})
    result = run_scenario(WINDOW, portfolio, _market({A: usd_series}, fx=fx))
    position, eur_cash, usd_cash = result.rows
    assert position.base_return == pytest.approx(0.9 * 0.95 - 1)
    assert position.contribution == pytest.approx(-0.0725)
    assert usd_cash.contribution == pytest.approx(-0.01)
    assert eur_cash.contribution == 0.0
    assert result.portfolio_return == pytest.approx(-0.0825)


def test_series_in_base_currency_and_hedged_classes_take_no_currency_effect() -> None:
    fx = {USD: _monthly([0.0, 0.0, -0.05, 0.0])}
    local = _monthly([0.0, 0.0, -0.10, 0.0])
    eur_nav = run_scenario(
        WINDOW,
        _portfolio({A: 0.5}, {EUR: 0.5}, {A: USD}),
        _market({A: PositionSeries(local, EUR)}, fx=fx),
    )
    assert eur_nav.portfolio_return == pytest.approx(-0.05)
    betas = pd.DataFrame({"mkt": [1.0]}, index=[A.code])
    factors = pd.DataFrame({"mkt": local})
    hedged = run_scenario(
        WINDOW,
        _portfolio({A: 0.5}, {EUR: 0.5}, {A: EUR}),
        _market(factors=factors, betas=betas, fx=fx),
    )
    assert hedged.rows[0].fx_return == 0.0
    assert hedged.portfolio_return == pytest.approx(-0.05)


def test_proxy_compounds_period_by_period() -> None:
    factors = pd.DataFrame({"mkt": _monthly([0.0, 0.0, -0.10, -0.10]), "val": 0.0})
    betas = pd.DataFrame({"mkt": [1.2], "val": [0.5]}, index=[A.code])
    result = run_scenario(WINDOW, _portfolio({A: 1.0}), _market(factors=factors, betas=betas))
    assert result.rows[0].method == "proxy"
    assert result.portfolio_return == pytest.approx(0.88**2 - 1)
    assert result.portfolio_return != pytest.approx(1.2 * (0.9**2 - 1))


def test_proxy_equals_direct_when_returns_are_exactly_factor_driven(
    rng: np.random.Generator,
) -> None:
    index = pd.date_range("2019-01-31", periods=24, freq="ME")
    factors = pd.DataFrame(rng.normal(0.0, 0.03, size=(24, 2)), index=index, columns=["m", "v"])
    beta = np.array([0.9, -0.4])
    own = PositionSeries(pd.Series(factors.to_numpy() @ beta, index=index), EUR)
    window = HistoricalScenario("w", "Synthetic", date(2019, 6, 30), date(2020, 6, 30))
    direct = run_scenario(window, _portfolio({A: 1.0}), _market({A: own}))
    betas = pd.DataFrame([beta], index=[A.code], columns=["m", "v"])
    proxy = run_scenario(window, _portfolio({A: 1.0}), _market(factors=factors, betas=betas))
    assert proxy.portfolio_return == pytest.approx(direct.portfolio_return, abs=1e-14)


def test_uncovered_positions_are_excluded_not_zeroed() -> None:
    short = PositionSeries(pd.Series([-0.5], index=MONTHS[-1:]), EUR)  # starts inside the window
    gappy = PositionSeries(_monthly([0.0, 0.0, np.nan, -0.1]), EUR)
    result = run_scenario(
        WINDOW,
        _portfolio({A: 0.5, B: 0.25, C: 0.15, D: 0.1}),
        _market({A: _crash(-0.2), B: short, C: gappy}),
    )
    assert [r.method for r in result.rows] == [
        "direct",
        "not covered",
        "not covered",
        "not covered",
    ]
    assert result.not_covered_weight == pytest.approx(0.5)
    assert result.portfolio_return == pytest.approx(-0.1)
    assert result.notes == ("50.00% of the portfolio is not covered and is excluded",)
    assert result.rows[1].contribution is None


def test_missing_fx_or_factor_columns_are_reported() -> None:
    result = run_scenario(
        WINDOW,
        _portfolio({A: 0.5}, {EUR: 0.3, USD: 0.2}, {A: USD}),
        _market({A: PositionSeries(_monthly([0.0, 0.0, -0.1, 0.0]), USD)}),
    )
    assert result.not_covered_weight == pytest.approx(0.7)
    assert "no USD rates cover the window" in result.notes
    assert result.rows[0].local_return == pytest.approx(-0.1)
    no_factor = run_scenario(
        WINDOW,
        _portfolio({A: 1.0}),
        _market(factors=pd.DataFrame({"other": _monthly([0.0] * 4)}),
                betas=pd.DataFrame({"mkt": [1.0]}, index=[A.code])),
    )  # fmt: skip
    assert "factor returns do not include ['mkt']: no proxies" in no_factor.notes
    short_factors = run_scenario(
        WINDOW,
        _portfolio({A: 1.0}),
        _market(factors=pd.DataFrame({"mkt": _monthly([0.0, 0.0, 0.0, 0.0])}).iloc[2:],
                betas=pd.DataFrame({"mkt": [1.0]}, index=[A.code])),
    )  # fmt: skip
    assert short_factors.not_covered_weight == 1.0


# --------------------------------------------------------------------------- hypothetical
def test_hypothetical_factor_shock_hand_example() -> None:
    scenario = HypotheticalScenario("crash", "Market -30 %", {"mkt": -0.30}, {}, {})
    betas = pd.DataFrame({"mkt": [0.8, 1.1]}, index=[A.code, B.code])
    result = run_scenario(scenario, _portfolio({A: 0.5, B: 0.3}, {EUR: 0.2}), _market(betas=betas))
    assert result.portfolio_return == pytest.approx(-0.219)
    assert (result.first_date, result.last_date) == (None, None)


def test_hypothetical_position_currency_and_uncovered() -> None:
    scenario = HypotheticalScenario("mix", "Mixed shocks", {"mkt": -0.1}, {A: -0.5}, {USD: -0.10})
    betas = pd.DataFrame({"mkt": [1.0]}, index=[B.code])
    portfolio = _portfolio({A: 0.2, B: 0.4, C: 0.2}, {USD: 0.2}, {B: USD})
    result = run_scenario(scenario, portfolio, _market(betas=betas))
    methods = {r.holding: r.method for r in result.rows}
    assert methods == {A.code: "shock", B.code: "proxy", C.code: "not covered", "cash USD": "cash"}
    expected = 0.2 * -0.5 + 0.4 * (0.9 * 0.9 - 1) + 0.2 * -0.1
    assert result.portfolio_return == pytest.approx(expected)
    fx_only = HypotheticalScenario("usd", "USD -10 %", {}, {}, {USD: -0.10})
    plain = run_scenario(fx_only, _portfolio({C: 0.5}, {EUR: 0.5}, {C: USD}), _market())
    assert plain.rows[0].method == "currency only"
    assert plain.portfolio_return == pytest.approx(-0.05)


def test_hypothetical_validation() -> None:
    with pytest.raises(ValidationError, match="no betas for factors"):
        run_scenario(
            HypotheticalScenario("x", "X", {"mkt": -0.1}, {}, {}), _portfolio({A: 1.0}), _market()
        )
    with pytest.raises(ValidationError, match="base currency"):
        run_scenario(
            HypotheticalScenario("x", "X", {}, {}, {EUR: -0.1}), _portfolio({A: 1.0}), _market()
        )
    for bad in (-1.0, float("nan"), True, "0.1"):
        with pytest.raises(ValidationError):
            HypotheticalScenario("x", "X", {"mkt": bad}, {}, {})  # type: ignore[dict-item]
    with pytest.raises(ValidationError, match="missing values"):
        run_scenario(
            HypotheticalScenario("x", "X", {}, {}, {}),
            _portfolio({A: 1.0}),
            _market(betas=pd.DataFrame({"mkt": [np.nan]}, index=[A.code])),
        )


def test_portfolio_and_window_validation() -> None:
    with pytest.raises(ValidationError, match="sum to 1"):
        _portfolio({A: 0.5})
    with pytest.raises(ValidationError, match="exposure currency"):
        StressPortfolio(date(2026, 6, 30), Money.of("1", "EUR"), {A: 1.0}, {}, {})
    with pytest.raises(ValidationError, match="not after"):
        HistoricalScenario("x", "X", date(2020, 3, 1), date(2020, 3, 1))
    with pytest.raises(ValidationError, match="dates"):
        HistoricalScenario("x", "X", "2020-01-01", date(2020, 3, 1))  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="description"):
        HistoricalScenario("x", " ", date(2020, 1, 1), date(2020, 3, 1))


# --------------------------------------------------------------------------- files
def test_example_scenarios_load() -> None:
    scenarios = load_scenarios(ROOT / "configs" / "scenarios" / "example.toml")
    assert [s.id for s in scenarios] == [
        "gfc_2008", "covid_2020", "rates_2022", "equity_minus_30", "usd_minus_10",
    ]  # fmt: skip
    gfc = scenarios[0]
    assert isinstance(gfc, HistoricalScenario)
    assert (gfc.start, gfc.end) == (date(2007, 10, 9), date(2009, 3, 9))
    usd = scenarios[-1]
    assert isinstance(usd, HypotheticalScenario)
    assert usd.currencies == {USD: -0.10}


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("x = 1", "must be a table"),
        ('[x]\nkind = "other"', "kind must be"),
        ('[x]\nkind = "historical"\ndescription = "d"\nstart = 2020-01-01', "keys"),
        (
            '[x]\nkind = "hypothetical"\ndescription = "d"\nfactors = 1\n'
            "positions = {}\ncurrencies = {}",
            "factors must be a table",
        ),
        ("", "no scenarios"),
    ],
)
def test_scenario_files_are_validated(tmp_path: Path, text: str, match: str) -> None:
    path = tmp_path / "s.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        load_scenarios(path)


def test_hypothetical_positions_load_as_isins(tmp_path: Path) -> None:
    path = tmp_path / "s.toml"
    path.write_text(
        f'[x]\nkind = "hypothetical"\ndescription = "d"\nfactors = {{}}\n'
        f"positions = {{ {A.code} = -0.2 }}\ncurrencies = {{}}\n",
        encoding="utf-8",
    )
    (scenario,) = load_scenarios(path)
    assert isinstance(scenario, HypotheticalScenario)
    assert scenario.positions == {A: -0.2}
