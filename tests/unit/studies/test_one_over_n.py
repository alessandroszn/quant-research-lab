"""Study 2 (1/N against optimised portfolios): hand-calculated cases first, then properties."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.studies.one_over_n import (
    STRATEGIES,
    BootstrapSettings,
    best_deflated_sharpe,
    certainty_equivalent,
    compare,
    comparison_table,
    last_trading_days,
    market_weights,
    monthly_excess_returns,
    monthly_net_excess,
    pair_table,
    performance,
    rolling_targets,
    run_targets,
)

BOOT = BootstrapSettings(mean_block_length=3.0, n_resamples=200, confidence=0.9)
ASSETS = ["a", "b", "c"]


def _months(n: int, start: str = "2000-01-31") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="ME")


def _excess(rng: np.random.Generator, n: int = 48) -> pd.DataFrame:
    means = np.array([0.006, 0.004, 0.008])
    vols = np.array([0.04, 0.03, 0.06])
    values = means + vols * rng.standard_normal((n, 3))
    return pd.DataFrame(values, index=_months(n), columns=ASSETS)


def _market(n: int = 48) -> pd.DataFrame:
    return pd.DataFrame(np.tile([0.5, 0.3, 0.2], (n, 1)), index=_months(n), columns=ASSETS)


# ------------------------------------------------------------------------------ data helpers
def test_monthly_excess_by_hand() -> None:
    monthly = pd.DataFrame({"a": [0.0302, 0.01]}, index=_months(2))
    rf = pd.Series([0.002, 0.003, 0.001], index=_months(3))
    excess = monthly_excess_returns(monthly, rf)
    assert excess["a"].to_numpy() == pytest.approx([0.0282, 0.007])
    with pytest.raises(ValidationError, match="risk-free"):
        monthly_excess_returns(monthly, rf.iloc[:1])


def test_market_weights_by_hand() -> None:
    firms = pd.DataFrame({"a": [10.0], "b": [20.0]}, index=_months(1))
    size = pd.DataFrame({"a": [5.0], "b": [1.0]}, index=_months(1))
    weights = market_weights(firms, size)
    # Caps 50 and 20: weights 50/70 and 20/70.
    assert weights.iloc[0].to_numpy() == pytest.approx([50 / 70, 20 / 70])
    with pytest.raises(ValidationError, match="same dates and assets"):
        market_weights(firms, size.rename(columns={"b": "c"}))


def test_market_weights_leave_incomplete_months_missing() -> None:
    firms = pd.DataFrame({"a": [10.0, 0.0], "b": [20.0, 5.0]}, index=_months(2))
    size = pd.DataFrame({"a": [5.0, np.nan], "b": [1.0, 2.0]}, index=_months(2))
    weights = market_weights(firms, size)
    assert weights.iloc[1].isna().all()


def test_last_trading_days() -> None:
    daily = pd.bdate_range("2000-01-03", "2000-03-31")
    found = last_trading_days(daily, _months(3))
    assert list(found) == list(pd.to_datetime(["2000-01-31", "2000-02-29", "2000-03-31"]))
    with pytest.raises(ValidationError, match="no daily data"):
        last_trading_days(daily, _months(4))


def test_certainty_equivalent_by_hand() -> None:
    # Two months with mean 1 % and variance (ddof 1) 0.0016: returns 1 % +- 2.828 %.
    d = math.sqrt(0.0016 / 2.0)
    series = pd.Series([0.01 + d, 0.01 - d], index=_months(2))
    assert certainty_equivalent(series, risk_aversion=1.0) == pytest.approx(0.0092)
    with pytest.raises(ValidationError, match="risk_aversion"):
        certainty_equivalent(series, risk_aversion=0.0)


# ---------------------------------------------------------------------------------- targets
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_gives_long_only_full_weights(
    rng: np.random.Generator, strategy: str
) -> None:
    excess = _excess(rng)
    targets = rolling_targets(
        excess,
        strategy=strategy,
        window=24,
        market=_market(),
        bl_risk_aversion=2.5,
        first=excess.index[30],
    )
    assert targets.weights.index[0] == excess.index[30]
    assert len(targets.weights) == 48 - 30
    assert (targets.weights >= 0).all().all()
    assert targets.weights.sum(axis=1).to_numpy() == pytest.approx(1.0)
    assert targets.strategy == strategy


def test_simple_strategies_by_hand(rng: np.random.Generator) -> None:
    excess = _excess(rng)
    ew = rolling_targets(
        excess, strategy="ew", window=24, market=None, bl_risk_aversion=2.5, first=None
    )
    assert ew.weights.index[0] == excess.index[23]
    assert ew.weights.to_numpy() == pytest.approx(1 / 3)
    market = _market()
    market.iloc[30] = [0.2, 0.2, 0.6]
    vw = rolling_targets(
        excess, strategy="vw", window=24, market=market, bl_risk_aversion=2.5, first=None
    )
    # The decision at month 31 uses the market weights of month 30 (lagged one month).
    assert vw.weights.loc[excess.index[31]].to_numpy() == pytest.approx([0.2, 0.2, 0.6])
    assert vw.weights.loc[excess.index[30]].to_numpy() == pytest.approx([0.5, 0.3, 0.2])


def test_rolling_window_and_no_look_ahead(rng: np.random.Generator) -> None:
    excess = _excess(rng)
    base = rolling_targets(
        excess, strategy="minvar_sample", window=24, market=None, bl_risk_aversion=2.5, first=None
    )
    changed = excess.copy()
    changed.iloc[40:] = rng.normal(0.0, 0.2, (8, 3))
    after = rolling_targets(
        changed, strategy="minvar_sample", window=24, market=None, bl_risk_aversion=2.5, first=None
    )
    pd.testing.assert_frame_equal(base.weights.iloc[: 40 - 23], after.weights.iloc[: 40 - 23])
    # The target at month 30 depends on months 7..30 only: changing month 6 leaves it unchanged.
    early = excess.copy()
    early.iloc[6] = [0.3, -0.3, 0.3]
    moved = rolling_targets(
        early, strategy="minvar_sample", window=24, market=None, bl_risk_aversion=2.5, first=None
    )
    pd.testing.assert_series_equal(
        base.weights.loc[excess.index[30]], moved.weights.loc[excess.index[30]]
    )
    assert not np.allclose(base.weights.loc[excess.index[29]], moved.weights.loc[excess.index[29]])


def test_max_sharpe_falls_back_to_min_variance(rng: np.random.Generator) -> None:
    excess = _excess(rng) - 0.5  # every mean negative
    targets = rolling_targets(
        excess,
        strategy="maxsharpe_sample",
        window=24,
        market=None,
        bl_risk_aversion=2.5,
        first=None,
    )
    minvar = rolling_targets(
        excess, strategy="minvar_sample", window=24, market=None, bl_risk_aversion=2.5, first=None
    )
    assert targets.fallbacks == len(targets.weights)
    pd.testing.assert_frame_equal(targets.weights, minvar.weights)


def test_targets_reject_bad_settings(rng: np.random.Generator) -> None:
    excess = _excess(rng)
    with pytest.raises(ValidationError, match="unknown strategy"):
        rolling_targets(
            excess, strategy="x", window=24, market=None, bl_risk_aversion=2.5, first=None
        )
    with pytest.raises(ValidationError, match="window"):
        rolling_targets(
            excess, strategy="ew", window=1, market=None, bl_risk_aversion=2.5, first=None
        )
    with pytest.raises(ValidationError, match="window"):
        rolling_targets(
            excess, strategy="ew", window=49, market=None, bl_risk_aversion=2.5, first=None
        )
    with pytest.raises(ValidationError, match="market weights"):
        rolling_targets(
            excess, strategy="vw", window=24, market=None, bl_risk_aversion=2.5, first=None
        )
    with pytest.raises(ValidationError, match="first"):
        rolling_targets(
            excess,
            strategy="ew",
            window=24,
            market=None,
            bl_risk_aversion=2.5,
            first=excess.index[5],
        )
    market = _market()
    market.iloc[29] = np.nan
    with pytest.raises(ValidationError, match="no market weights"):
        rolling_targets(
            excess, strategy="vw", window=24, market=market, bl_risk_aversion=2.5, first=None
        )


# ------------------------------------------------------------------------- engine and returns
def _daily(rng: np.random.Generator, months: int = 6) -> pd.DataFrame:
    days = pd.bdate_range("2000-01-03", _months(months)[-1])
    return pd.DataFrame(
        0.0003 + 0.01 * rng.standard_normal((len(days), 3)), index=days, columns=ASSETS
    )


def test_run_targets_and_monthly_excess(rng: np.random.Generator) -> None:
    daily = _daily(rng)
    targets = pd.DataFrame(np.full((3, 3), 1 / 3), index=_months(3), columns=ASSETS)
    result = run_targets(daily, targets, cost=0.001)
    assert result.settings["execution_lag"] == 1.0
    assert result.net_returns.index[0] == pd.Timestamp("2000-01-31")
    rf = pd.Series(0.001, index=_months(6))
    excess = monthly_net_excess(result, rf)
    # The decision month (January) is excluded; February to June remain.
    assert list(excess.index) == list(_months(6)[1:])
    feb = result.net_returns.loc["2000-02-01":"2000-02-29"]
    assert excess.iloc[0] == pytest.approx(float(np.prod(1 + feb)) - 1 - 0.001)
    with pytest.raises(ValidationError, match="cost"):
        run_targets(daily, targets, cost=-0.001)


def test_performance_and_comparison(rng: np.random.Generator) -> None:
    a = pd.Series(rng.normal(0.008, 0.04, 120), index=_months(120))
    b = pd.Series(rng.normal(0.006, 0.05, 120), index=_months(120))
    perf = performance(a, turnover=0.25, ceq_risk_aversion=1.0, fallbacks=0)
    assert perf.sharpe == pytest.approx(float(a.mean() / a.std(ddof=1)) * math.sqrt(12))
    assert perf.ceq == pytest.approx(12 * certainty_equivalent(a, risk_aversion=1.0))
    assert perf.mean == pytest.approx(12 * float(a.mean()))
    assert perf.n == 120
    result = compare(
        a, b, hac_lags=3, bootstrap=BOOT, rng=np.random.default_rng(1), ceq_risk_aversion=1.0
    )
    assert result.hac.difference == pytest.approx(result.jkm.difference, rel=0.05)
    assert result.ceq_interval.estimate == pytest.approx(
        certainty_equivalent(a, risk_aversion=1.0) - certainty_equivalent(b, risk_aversion=1.0)
    )
    assert result.sharpe_interval.low <= result.sharpe_interval.high


def test_tables_and_deflated_sharpe(rng: np.random.Generator) -> None:
    months = _months(120)
    series = {
        name: pd.Series(rng.normal(0.005 + 0.001 * i, 0.04, 120), index=months)
        for i, name in enumerate(["ew", "minvar_sample", "minvar_lw", "hrp"])
    }
    comparisons = {
        ("D", 60, 0.0, name): compare(
            s, series["ew"], hac_lags=3, bootstrap=BOOT, rng=rng, ceq_risk_aversion=1.0
        )
        for name, s in series.items()
        if name != "ew"
    }
    table = comparison_table(comparisons, significance=0.05)
    assert len(table) == 3
    p = table["pvalue_hac"].sort_values()
    holm = np.maximum.accumulate(np.minimum(1.0, np.array([3, 2, 1]) * p.to_numpy()))
    assert table.loc[p.index, "holm"].to_numpy() == pytest.approx(holm)
    pairs = pair_table(
        {("D", 60, 0.0, "minvar_lw", "minvar_sample"): comparisons[("D", 60, 0.0, "minvar_lw")]},
        significance=0.05,
    )
    assert pairs.loc[0, "holm"] == pytest.approx(pairs.loc[0, "pvalue_hac"])
    best = best_deflated_sharpe(series, configurations=2)
    assert best is not None
    label, dsr, n_trials = best
    assert n_trials == 8
    assert label == max(series, key=lambda k: float(series[k].mean() / series[k].std(ddof=1)))
    assert 0.0 <= dsr.probability <= 1.0
    assert best_deflated_sharpe({"ew": series["ew"]}, configurations=1) is None
    with pytest.raises(ValidationError, match="configurations"):
        best_deflated_sharpe(series, configurations=0)
    with pytest.raises(ValidationError, match="at least one"):
        comparison_table({}, significance=0.05)
    with pytest.raises(ValidationError, match="at least one"):
        pair_table({}, significance=0.05)


def test_guards(rng: np.random.Generator) -> None:
    from qrlab.studies.one_over_n import _clean

    assert _clean(pd.Series({"a": 0.6, "b": 0.4 + 1e-12, "c": -1e-12})).sum() == pytest.approx(1.0)
    with pytest.raises(ValidationError, match="negative long-only"):
        _clean(pd.Series({"a": 1.1, "b": -0.1}))
    daily = _daily(rng)
    targets = pd.DataFrame(np.full((1, 3), 1 / 3), index=_months(1), columns=ASSETS)
    result = run_targets(daily, targets, cost=0.0)
    with pytest.raises(ValidationError, match="no risk-free rate"):
        monthly_net_excess(result, pd.Series(0.001, index=_months(2)))
    flat = pd.Series(0.0, index=_months(12))
    with pytest.raises(ValidationError, match="zero variance"):
        performance(flat, turnover=0.0, ceq_risk_aversion=1.0, fallbacks=0)
