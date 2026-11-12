"""Study 4 (rebalancing): hand-calculated cases first, then properties."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.optimization import CostModel
from qrlab.studies.rebalancing import (
    POLICIES,
    compare_to_reference,
    equity_returns_eur,
    historical_runs,
    hypotheses,
    liquidation_value,
    month_end_observations,
    path_metrics,
    run_policy,
    simulate,
    summarize_runs,
    zero_coupon_returns,
)

TARGET = pd.Series({"equity": 0.6, "bond": 0.4})
FREE = CostModel(0.0, 0.0)


def _months(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2020-01-31", periods=n, freq="ME")


# ------------------------------------------------------------------------------- conversions
def test_equity_in_eur_by_hand() -> None:
    # 1 % in USD while the euro rises from 1.10 to 1.12 dollars: 1.01 x 1.10 / 1.12 - 1.
    returns = pd.Series([0.0, 0.01], index=_months(2))
    rates = pd.Series([1.10, 1.12], index=_months(2))
    eur = equity_returns_eur(returns, rates)
    assert list(eur.index) == [_months(2)[1]]
    assert eur.iloc[0] == pytest.approx(1.01 * 1.10 / 1.12 - 1)
    assert eur.iloc[0] == pytest.approx(-0.008036, abs=1e-6)
    with pytest.raises(ValidationError, match="positive"):
        equity_returns_eur(returns, rates * 0.0)
    with pytest.raises(ValidationError, match="no month"):
        equity_returns_eur(returns.iloc[:1], rates.iloc[1:])


def _curve(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    days = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {"SR_6Y": [r[1] for r in rows], "SR_7Y": [r[2] for r in rows], "observed": days},
        index=days + pd.offsets.MonthEnd(0),
    )


def test_zero_coupon_flat_curve_by_hand() -> None:
    # Observations 30 days apart (delta = 30/365.25, about 1/12); flat 3 %:
    # exp(0.03 x 30/365.25) - 1 = 0.2467 % (with delta = 1/12 exactly it would be 0.2503 %).
    curve = _curve([("2021-01-31", 0.03, 0.03), ("2021-03-02", 0.03, 0.03)])
    curve.index = pd.to_datetime(["2021-01-31", "2021-02-28"])
    delta = 30 / 365.25
    r = zero_coupon_returns(curve, short="SR_6Y", long="SR_7Y", maturity=7.0)
    assert r.iloc[0] == pytest.approx(math.exp(0.03 * delta) - 1)
    assert r.iloc[0] == pytest.approx(0.002467, abs=1e-6)
    # Rates up from 3 % to 4 %: exp(0.21 - 0.04 x (7 - delta)) - 1, about -6.45 %.
    curve.loc[curve.index[1], ["SR_6Y", "SR_7Y"]] = [0.04, 0.04]
    up = zero_coupon_returns(curve, short="SR_6Y", long="SR_7Y", maturity=7.0)
    assert up.iloc[0] == pytest.approx(math.exp(0.21 - 0.04 * (7 - delta)) - 1)
    assert up.iloc[0] == pytest.approx(-0.0645, abs=2e-4)


def test_zero_coupon_interpolates_between_maturities() -> None:
    curve = _curve([("2020-01-31", 0.02, 0.03), ("2020-02-28", 0.02, 0.03)])
    r = zero_coupon_returns(curve, short="SR_6Y", long="SR_7Y", maturity=7.0)
    delta = 28 / 365.25
    z_end = 0.03 - delta * (0.03 - 0.02)
    assert r.iloc[0] == pytest.approx(math.exp(0.03 * 7 - z_end * (7 - delta)) - 1)


def test_zero_coupon_inputs_are_validated() -> None:
    curve = _curve([("2020-01-31", 0.02, 0.03), ("2020-02-28", 0.02, 0.03)])
    with pytest.raises(ValidationError, match="maturity"):
        zero_coupon_returns(curve, short="SR_6Y", long="SR_7Y", maturity=1.0)
    with pytest.raises(ValidationError, match="lacks column"):
        zero_coupon_returns(
            curve.drop(columns="observed"), short="SR_6Y", long="SR_7Y", maturity=7.0
        )
    with pytest.raises(ValidationError, match="two month ends"):
        zero_coupon_returns(curve.iloc[:1], short="SR_6Y", long="SR_7Y", maturity=7.0)
    backwards = curve.assign(observed=curve["observed"].iloc[::-1].to_numpy())
    with pytest.raises(ValidationError, match="less than a year apart"):
        zero_coupon_returns(backwards, short="SR_6Y", long="SR_7Y", maturity=7.0)


def test_month_end_observations() -> None:
    days = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-27", "2020-03-31"])
    daily = pd.DataFrame({"x": [1.0, 2.0, 3.0, np.nan], "y": [1.0, 1.0, 1.0, 1.0]}, index=days)
    # January and February, then April: March has no observation.
    gap_days = pd.to_datetime(["2020-01-31", "2020-02-27", "2020-04-30"])
    with pytest.raises(ValidationError, match="no observation in month 2020-03-31"):
        month_end_observations(pd.DataFrame({"x": [1.0, 2.0, 3.0]}, index=gap_days))
    out = month_end_observations(daily.iloc[:3])
    assert list(out.index) == list(pd.to_datetime(["2020-01-31", "2020-02-29"]))
    assert out["x"].tolist() == [2.0, 3.0]
    assert out["observed"].iloc[1] == pd.Timestamp("2020-02-27")
    with pytest.raises(ValidationError, match="no complete daily"):
        month_end_observations(daily.iloc[3:])


# ---------------------------------------------------------------------------------- policies
def test_band_rule_by_hand() -> None:
    # Equity +20 %: 72/40 -> 64.3 % equity, inside a 5-point band: no trade.
    inside = pd.DataFrame({"equity": [0.2], "bond": [0.0]}, index=_months(1))
    result = run_policy(
        inside,
        weights=TARGET,
        policy="band_5_target",
        costs=FREE,
        tax_rate=0.0,
        initial_value=100.0,
    )
    assert result.executions == ()
    assert result.weights["equity"].iloc[0] == pytest.approx(72 / 112)
    # Equity +30 %: 78/40 -> 66.1 %, outside: back to 60/40.
    outside = pd.DataFrame({"equity": [0.3], "bond": [0.0]}, index=_months(1))
    result = run_policy(
        outside,
        weights=TARGET,
        policy="band_5_target",
        costs=FREE,
        tax_rate=0.0,
        initial_value=100.0,
    )
    assert len(result.executions) == 1
    assert result.weights["equity"].iloc[0] == pytest.approx(0.6)


def test_calendar_rules_trade_on_schedule(rng: np.random.Generator) -> None:
    frame = pd.DataFrame(
        {"equity": rng.normal(0.01, 0.04, 12), "bond": rng.normal(0.002, 0.01, 12)},
        index=_months(12),
    )
    quarterly = run_policy(
        frame,
        weights=TARGET,
        policy="calendar_quarterly",
        costs=FREE,
        tax_rate=0.0,
        initial_value=100.0,
    )
    assert [e.executed.month for e in quarterly.executions] == [3, 6, 9, 12]
    hold = run_policy(
        frame, weights=TARGET, policy="buy_and_hold", costs=FREE, tax_rate=0.0, initial_value=100.0
    )
    assert hold.executions == ()
    with pytest.raises(ValidationError, match="unknown policy"):
        run_policy(
            frame, weights=TARGET, policy="daily", costs=FREE, tax_rate=0.0, initial_value=100.0
        )
    assert set(POLICIES) == {
        "buy_and_hold",
        "calendar_monthly",
        "calendar_quarterly",
        "calendar_annual",
        "band_5_target",
        "band_10_target",
        "band_5_edge",
    }


def test_liquidation_by_hand() -> None:
    # All in one asset bought at 100, now 150: tax 26 % x 50 = 13, after-tax 137.
    frame = pd.DataFrame({"equity": [0.5], "bond": [0.0]}, index=_months(1))
    result = run_policy(
        frame,
        weights=pd.Series({"equity": 1.0, "bond": 0.0}),
        policy="buy_and_hold",
        costs=FREE,
        tax_rate=0.26,
        initial_value=100.0,
    )
    value, tax = liquidation_value(result, tax_rate=0.26)
    assert (value, tax) == pytest.approx((137.0, 13.0))
    with pytest.raises(ValidationError, match="tax_rate"):
        liquidation_value(result, tax_rate=1.0)


def test_losses_do_not_offset_gains() -> None:
    # 50/50 of 100: equity +40 % (gain 20), bond -20 % (loss 10). Tax on 20 only: 5.2.
    frame = pd.DataFrame({"equity": [0.4], "bond": [-0.2]}, index=_months(1))
    result = run_policy(
        frame,
        weights=pd.Series({"equity": 0.5, "bond": 0.5}),
        policy="buy_and_hold",
        costs=FREE,
        tax_rate=0.26,
        initial_value=100.0,
    )
    value, tax = liquidation_value(result, tax_rate=0.26)
    assert tax == pytest.approx(0.26 * 20)
    assert value == pytest.approx(110 - 5.2)


def test_path_metrics(rng: np.random.Generator) -> None:
    frame = pd.DataFrame(
        {"equity": rng.normal(0.01, 0.04, 24), "bond": rng.normal(0.002, 0.01, 24)},
        index=_months(24),
    )
    result = run_policy(
        frame,
        weights=TARGET,
        policy="calendar_monthly",
        costs=CostModel(0.001, 2.0),
        tax_rate=0.26,
        initial_value=100_000.0,
    )
    m = path_metrics(result, target=TARGET, equity="equity", tax_rate=0.26, initial_value=100_000.0)
    after, deferred = liquidation_value(result, tax_rate=0.26)
    assert m.after_tax_wealth == pytest.approx(after)
    assert m.deferred_tax == pytest.approx(deferred)
    assert m.after_tax_return == pytest.approx((after / 100_000.0) ** 0.5 - 1)
    assert m.trades == 2 * 24
    assert m.costs == pytest.approx(result.costs_paid)
    assert m.max_abs_deviation == pytest.approx(0.0, abs=1e-9)  # rebalanced every month
    assert m.volatility == pytest.approx(float(result.net_returns.std(ddof=1)) * math.sqrt(12))


# -------------------------------------------------------------------------------- simulation
def _history(rng: np.random.Generator, n: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {"equity": rng.normal(0.008, 0.045, n), "bond": rng.normal(0.002, 0.012, n)},
        index=_months(n),
    )


def test_simulation_uses_the_same_paths_for_every_policy(rng: np.random.Generator) -> None:
    history = _history(rng)
    runs = simulate(
        history,
        weights=TARGET,
        equity="equity",
        policies=list(POLICIES),
        cost_scenarios={"low": CostModel(0.0005, 2.0)},
        tax_rate=0.26,
        initial_value=100_000.0,
        horizon=48,
        n_paths=6,
        mean_block_length=6.0,
        rng=np.random.default_rng(3),
    )
    assert len(runs) == 6 * 7
    again = simulate(
        history,
        weights=TARGET,
        equity="equity",
        policies=["buy_and_hold"],
        cost_scenarios={"low": CostModel(0.0005, 2.0)},
        tax_rate=0.26,
        initial_value=100_000.0,
        horizon=48,
        n_paths=6,
        mean_block_length=6.0,
        rng=np.random.default_rng(3),
    )
    hold = runs[runs["policy"] == "buy_and_hold"].reset_index(drop=True)
    pd.testing.assert_series_equal(hold["after_tax_wealth"], again["after_tax_wealth"])
    comparison = compare_to_reference(runs, reference="calendar_annual")
    assert set(comparison["policy"]) == set(POLICIES) - {"calendar_annual"}
    row = comparison.set_index("policy").loc["buy_and_hold"]
    by = runs.set_index(["policy", "path"])["after_tax_wealth"]
    diff = by["buy_and_hold"] - by["calendar_annual"]
    assert row["after_tax_wealth_median"] == pytest.approx(float(diff.median()))
    assert row["share_wealth_higher"] == pytest.approx(float((diff > 0).mean()))
    verdicts = hypotheses(runs, support_share=2 / 3)
    assert set(verdicts["hypothesis"]) == {"H1", "H2", "H3"}
    h2 = verdicts[verdicts["hypothesis"] == "H2"].iloc[0]
    monthly = runs[runs["policy"] == "calendar_monthly"].set_index("path")["after_tax_wealth"]
    annual = runs[runs["policy"] == "calendar_annual"].set_index("path")["after_tax_wealth"]
    assert h2["share"] == pytest.approx(float((monthly < annual).mean()))
    assert h2["supported"] == (h2["share"] >= 2 / 3)


def test_simulation_and_comparison_validation(rng: np.random.Generator) -> None:
    history = _history(rng, 24)
    kwargs = {
        "weights": TARGET,
        "equity": "equity",
        "policies": ["buy_and_hold"],
        "cost_scenarios": {"low": FREE},
        "tax_rate": 0.26,
        "initial_value": 100.0,
        "mean_block_length": 3.0,
        "rng": rng,
    }
    with pytest.raises(ValidationError, match="horizon"):
        simulate(history, horizon=25, n_paths=2, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="n_paths"):
        simulate(history, horizon=24, n_paths=0, **kwargs)  # type: ignore[arg-type]
    runs = simulate(history, horizon=24, n_paths=2, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="reference policy"):
        compare_to_reference(runs, reference="calendar_annual")
    with pytest.raises(ValidationError, match="hypotheses need"):
        hypotheses(runs, support_share=2 / 3)
    with pytest.raises(ValidationError, match="support_share"):
        hypotheses(runs, support_share=0.5)


def test_historical_runs_and_summary(rng: np.random.Generator) -> None:
    history = _history(rng, 36)
    runs = historical_runs(
        history,
        weights=TARGET,
        equity="equity",
        policies=["buy_and_hold", "calendar_annual"],
        cost_scenarios={"low": CostModel(0.0005, 2.0), "high": CostModel(0.002, 10.0)},
        tax_rate=0.26,
        initial_value=100_000.0,
    )
    assert len(runs) == 4
    assert (runs["path"] == 0).all()
    hold = runs[(runs["policy"] == "buy_and_hold") & (runs["scenario"] == "low")].iloc[0]
    direct = path_metrics(
        run_policy(
            history,
            weights=TARGET,
            policy="buy_and_hold",
            costs=CostModel(0.0005, 2.0),
            tax_rate=0.26,
            initial_value=100_000.0,
        ),
        target=TARGET,
        equity="equity",
        tax_rate=0.26,
        initial_value=100_000.0,
    )
    assert hold["after_tax_wealth"] == pytest.approx(direct.after_tax_wealth)
    summary = summarize_runs(runs)
    assert len(summary) == 4
    assert (summary["paths"] == 1).all()
    with pytest.raises(ValidationError, match="no runs"):
        summarize_runs(runs.iloc[0:0])
