"""Diversification, risk, ETF-quality, currency and drift checks.

Hand values (design note):

- diversification ratio with sigma 20 % / 10 %, rho 0.5 and equal weights:
  0.15 / sqrt(0.25 * 0.04 + 0.25 * 0.01 + 2 * 0.25 * 0.5 * 0.02) = 0.15 / 0.132288 = 1.133893;
- drift: current 0.6 / 0.4 against targets 0.5 / 0.5 gives max deviation 0.10 and total 0.10;
- a USD fund at 30 % of a EUR portfolio gives unhedged foreign exposure 0.30;
- returns 0.10, -0.10, 0.05, -0.05: wealth 1.1, 0.99, 1.0395, 0.987525, so the maximum
  drawdown is 0.987525 / 1.1 - 1 = -0.102250; the series is symmetric, so skewness is 0;
- a USD 125m fund at EUR/USD 1.25 is EUR 100m; inception 2024-06-30 to 2026-06-30 is
  730 / 365.25 = 1.998631 years (2024-02-29 is before the start).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from qrlab.checks import currency_drift, diversification, etf_quality, risk
from qrlab.checks.engine import ALL_CHECKS, CheckConfig, run_checks
from qrlab.checks.framework import Measurement, NotApplicable, Severity, Thresholds
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money
from qrlab.instruments.master import Distribution, InstrumentType, Replication
from support.checks import AS_OF, A, B, C, fund, weighted_context
from support.portfolio import EUR, FixedRates

USD = Currency("USD")
NO_PARAMS: Mapping[str, object] = {}
WINDOW = 24


def _one(outcome: list[Measurement] | NotApplicable) -> Measurement:
    assert not isinstance(outcome, NotApplicable), outcome
    (measurement,) = outcome
    return measurement


def _monthly(values: list[float]) -> pd.Series:
    index = pd.date_range(end=pd.Timestamp(AS_OF), periods=len(values), freq="ME")
    return pd.Series(values, index=index, dtype=float)


def _orthonormal(rng: np.random.Generator, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Two series with sample mean 0, sample std 1 (ddof 1) and sample correlation 0."""
    raw = rng.standard_normal((n, 2))
    raw -= raw.mean(axis=0)
    q, _ = np.linalg.qr(raw)
    q *= math.sqrt(n - 1)
    return q[:, 0], q[:, 1]


def _prices_from_returns(returns: np.ndarray) -> pd.Series:
    """Price path ending on AS_OF whose simple returns are exactly ``returns``."""
    path = np.concatenate([[100.0], 100.0 * np.cumprod(1.0 + returns)])
    index = pd.date_range(end=pd.Timestamp(AS_OF), periods=len(path), freq="D")
    return pd.Series(path, index=index)


def _two_assets(rng: np.random.Generator, rho: float, n: int = WINDOW) -> dict[object, pd.Series]:
    z1, z2 = _orthonormal(rng, n)
    x = 0.002 + 0.02 * z1
    y = 0.001 + 0.01 * (rho * z1 + math.sqrt(1 - rho**2) * z2)
    return {A: _prices_from_returns(x), B: _prices_from_returns(y)}


# --------------------------------------------------------------------------- diversification
def test_diversification_ratio_and_correlation_hand_example(rng: np.random.Generator) -> None:
    ctx = weighted_context({A: "0.45", B: "0.45"}, prices=_two_assets(rng, 0.5))  # type: ignore[arg-type]
    params = {"window": WINDOW}
    ratio = _one(diversification.diversification_ratio(ctx, params))
    assert ratio.observed == pytest.approx(0.15 / math.sqrt(0.0175), rel=1e-9)
    assert ratio.observed == pytest.approx(1.133893, abs=1e-6)
    corr = _one(diversification.average_correlation(ctx, params))
    assert corr.observed == pytest.approx(0.5, abs=1e-12)
    assert corr.details == {"pairs": "1"}


def test_effective_bets_hand_example(rng: np.random.Generator) -> None:
    # uncorrelated, sigma 2 % and 1 %, equal weights: variance shares 0.8 / 0.2,
    # ENB = exp(-(0.8 ln 0.8 + 0.2 ln 0.2)) = 1.649385
    ctx = weighted_context({A: "0.45", B: "0.45"}, prices=_two_assets(rng, 0.0))  # type: ignore[arg-type]
    measured = _one(diversification.effective_bets(ctx, {"window": WINDOW}))
    assert measured.observed == pytest.approx(1.649385, abs=1e-6)
    assert measured.details == {"positions": "2"}
    single = weighted_context({A: "1"})
    assert isinstance(diversification.effective_bets(single, {"window": WINDOW}), NotApplicable)


def test_diversification_uses_only_the_last_window(rng: np.random.Generator) -> None:
    prices = _two_assets(rng, 0.9, n=WINDOW + 10)
    ctx = weighted_context({A: "0.5", B: "0.5"}, prices=prices)  # type: ignore[arg-type]
    returns = diversification.position_returns(ctx, WINDOW)
    assert isinstance(returns, pd.DataFrame)
    assert len(returns) == WINDOW
    assert returns.index[-1] == pd.Timestamp(AS_OF)


def test_diversification_not_applicable_cases(rng: np.random.Generator) -> None:
    params = {"window": WINDOW}
    single = weighted_context({A: "1"})
    assert isinstance(diversification.average_correlation(single, params), NotApplicable)
    no_series = weighted_context({A: "0.5", B: "0.5"}, prices={A: _two_assets(rng, 0.5)[A]})
    reason = diversification.diversification_ratio(no_series, params)
    assert isinstance(reason, NotApplicable)
    assert "IE0000000053" in reason.reason
    short = weighted_context({A: "0.5", B: "0.5"}, prices=_two_assets(rng, 0.5, n=WINDOW - 1))  # type: ignore[arg-type]
    assert isinstance(diversification.average_correlation(short, params), NotApplicable)
    flat = _two_assets(rng, 0.5)
    flat[B] = pd.Series(100.0, index=flat[B].index)
    zero_var = weighted_context({A: "0.5", B: "0.5"}, prices=flat)  # type: ignore[arg-type]
    outcome = diversification.diversification_ratio(zero_var, params)
    assert isinstance(outcome, NotApplicable)
    assert "zero return variance" in outcome.reason


def test_diversification_ignores_prices_after_as_of_and_rows_with_gaps(
    rng: np.random.Generator,
) -> None:
    prices = _two_assets(rng, 0.5, n=WINDOW + 2)
    later = pd.Timestamp(AS_OF) + pd.Timedelta(days=1)
    prices[A] = pd.concat([prices[A], pd.Series([1.0], index=[later])])
    prices[B] = pd.concat([prices[B], pd.Series([1000.0], index=[later])])
    prices[B].iloc[0] = np.nan  # its first two returns are missing: still WINDOW + 1 common rows
    ctx = weighted_context({A: "0.5", B: "0.5"}, prices=prices)  # type: ignore[arg-type]
    returns = diversification.position_returns(ctx, WINDOW)
    assert isinstance(returns, pd.DataFrame)
    assert returns.index[-1] == pd.Timestamp(AS_OF)
    assert not returns.isna().to_numpy().any()


def test_diversification_reads_return_levels_when_given(rng: np.random.Generator) -> None:
    """Design note 11.1: an entry in ``return_levels`` replaces the position's prices."""
    prices = _two_assets(rng, 0.5)
    ctx = weighted_context({A: "0.5", B: "0.5"}, prices=prices)  # type: ignore[arg-type]
    before = diversification.position_returns(ctx, WINDOW)
    assert isinstance(before, pd.DataFrame)
    # B paid 1.0 on its last date: its level rises by 1 % more than its price there.
    levels = prices[B] * np.where(prices[B].index == pd.Timestamp(AS_OF), 1.01, 1.0)
    with_levels = replace(ctx, return_levels={B: levels})
    after = diversification.position_returns(with_levels, WINDOW)
    assert isinstance(after, pd.DataFrame)
    pd.testing.assert_series_equal(after[A.code], before[A.code])  # no entry: its prices
    assert after[B.code].iloc[-1] == pytest.approx((1.0 + before[B.code].iloc[-1]) * 1.01 - 1.0)
    assert after[B.code].iloc[:-1].equals(before[B.code].iloc[:-1])
    assert ctx.return_levels is None  # the default keeps today's behaviour


@pytest.mark.parametrize("window", [1, 2.0, True, "24"])
def test_diversification_rejects_bad_window(window: object) -> None:
    ctx = weighted_context({A: "0.5", B: "0.5"})
    with pytest.raises(ValidationError, match="window"):
        diversification.position_returns(ctx, window)


# --------------------------------------------------------------------------- risk
def test_risk_checks_hand_example() -> None:
    returns = _monthly([0.10, -0.10, 0.05, -0.05])
    ctx = weighted_context({A: "1"}, portfolio_returns=returns)
    expected_vol = float(np.std([0.10, -0.10, 0.05, -0.05], ddof=1)) * math.sqrt(12)
    vol = _one(risk.volatility(ctx, {"periods_per_year": 12}))
    assert vol.observed == pytest.approx(expected_vol)
    assert _one(risk.max_drawdown(ctx, NO_PARAMS)).observed == pytest.approx(-0.10225)
    assert _one(risk.skewness(ctx, NO_PARAMS)).observed == pytest.approx(0.0, abs=1e-12)


def test_expected_shortfall_is_the_worst_return_at_95_with_20_observations() -> None:
    values = [0.01] * 19 + [-0.08]
    ctx = weighted_context({A: "1"}, portfolio_returns=_monthly(values))
    measured = _one(risk.expected_shortfall(ctx, {"confidence": 0.95}))
    assert measured.observed == pytest.approx(0.08)


def test_beta_against_benchmark() -> None:
    bench = _monthly([0.01, -0.02, 0.03, 0.00, -0.01])
    portfolio = 0.001 + 2.0 * bench
    ctx = weighted_context({A: "1"}, portfolio_returns=portfolio, benchmark_returns=bench)
    measured = _one(risk.beta(ctx, NO_PARAMS))
    assert measured.observed == pytest.approx(2.0)
    assert measured.details == {"r_squared": "1.0000"}
    no_bench = weighted_context({A: "1"}, portfolio_returns=portfolio)
    assert risk.beta(no_bench, NO_PARAMS) == NotApplicable("no benchmark given")


def test_beta_works_at_any_frequency() -> None:
    """Regression (7.1): beta passed periods_per_year=1 whatever the dates' frequency."""
    for freq in ("B", "W-FRI", "ME"):
        index = pd.date_range("2024-01-05", periods=6, freq=freq)
        bench = pd.Series([0.01, -0.02, 0.03, 0.00, -0.01, 0.02], index=index)
        ctx = weighted_context({A: "1"}, portfolio_returns=2 * bench, benchmark_returns=bench)
        assert _one(risk.beta(ctx, NO_PARAMS)).observed == pytest.approx(2.0)
    irregular = pd.DatetimeIndex(["2024-01-01", "2024-01-11", "2024-01-21", "2024-01-31"])
    bench = pd.Series([0.01, -0.02, 0.03, 0.01], index=irregular)
    ctx = weighted_context({A: "1"}, portfolio_returns=2 * bench, benchmark_returns=bench)
    assert _one(risk.beta(ctx, NO_PARAMS)).observed == pytest.approx(2.0)


def test_risk_checks_not_applicable() -> None:
    no_series = weighted_context({A: "1"})
    params: dict[str, Mapping[str, object]] = {
        "volatility": {"periods_per_year": 12},
        "expected_shortfall": {"confidence": 0.95},
    }
    for name in ("volatility", "max_drawdown", "expected_shortfall", "beta", "skewness"):
        check = getattr(risk, name)
        assert isinstance(check(no_series, params.get(name, NO_PARAMS)), NotApplicable)
    one_obs = weighted_context(
        {A: "1"}, portfolio_returns=_monthly([0.01]), benchmark_returns=_monthly([0.01])
    )
    for name in ("volatility", "expected_shortfall", "beta", "skewness"):
        check = getattr(risk, name)
        assert isinstance(check(one_obs, params.get(name, NO_PARAMS)), NotApplicable), name
    empty = weighted_context({A: "1"}, portfolio_returns=_monthly([]))
    assert isinstance(risk.max_drawdown(empty, NO_PARAMS), NotApplicable)
    # one return already has a defined drawdown: 0 when it is a gain
    assert _one(risk.max_drawdown(one_obs, NO_PARAMS)).observed == 0.0


def test_risk_checks_reject_bad_params() -> None:
    ctx = weighted_context({A: "1"}, portfolio_returns=_monthly([0.01, 0.02, -0.01]))
    with pytest.raises(ValidationError, match="periods_per_year"):
        risk.volatility(ctx, {"periods_per_year": True})
    with pytest.raises(ValidationError, match="confidence"):
        risk.expected_shortfall(ctx, {"confidence": 1})


# --------------------------------------------------------------------------- ETF quality
def _quality_context() -> object:
    return weighted_context(
        {A: "0.3", B: "0.4", C: "0.2"},
        instruments={
            A: fund(A, replication=Replication.SYNTHETIC, domicile="FR"),
            B: fund(B, distribution=Distribution.DISTRIBUTING),
            C: fund(C, replication=None, domicile=None, distribution=None),
        },
    )


def test_etf_shares_with_unknown_fields() -> None:
    ctx = _quality_context()
    synthetic = _one(etf_quality.synthetic_share(ctx, NO_PARAMS))  # type: ignore[arg-type]
    assert synthetic.observed == pytest.approx(0.3)
    assert synthetic.details == {"funds": "IE0000000046", "unknown_weight": "0.200000"}
    domicile = _one(etf_quality.domicile(ctx, {"preferred": ["IE", "LU"]}))  # type: ignore[arg-type]
    assert domicile.observed == pytest.approx(0.3)
    policy = _one(etf_quality.distribution(ctx, {"preferred": "accumulating"}))  # type: ignore[arg-type]
    assert policy.observed == pytest.approx(0.4)
    assert policy.details["funds"] == "IE0000000053"


def test_etf_shares_pass_and_not_applicable() -> None:
    clean = weighted_context({A: "0.5", B: "0.5"})
    assert _one(etf_quality.synthetic_share(clean, NO_PARAMS)).observed == 0.0
    stock = weighted_context(
        {A: "1"}, instruments={A: fund(A, instrument_type=InstrumentType.STOCK, ter=None,
                                       replication=None, distribution=None, benchmark=None,
                                       fund_size=None)}
    )  # fmt: skip
    for outcome in (
        etf_quality.synthetic_share(stock, NO_PARAMS),
        etf_quality.fund_size(stock, NO_PARAMS),
        etf_quality.fund_age(stock, NO_PARAMS),
    ):
        assert isinstance(outcome, NotApplicable)


def test_etf_quality_rejects_bad_params() -> None:
    ctx = weighted_context({A: "1"})
    with pytest.raises(ValidationError, match="preferred"):
        etf_quality.domicile(ctx, {"preferred": []})
    with pytest.raises(ValidationError):
        etf_quality.domicile(ctx, {"preferred": ["XX1"]})
    with pytest.raises(ValidationError, match="accumulating or distributing"):
        etf_quality.distribution(ctx, {"preferred": "reinvesting"})


def test_fund_size_in_base_currency_and_fund_age() -> None:
    ctx = weighted_context(
        {A: "0.5", B: "0.5"},
        to_base=FixedRates({AS_OF: "1.25"}),
        instruments={
            A: fund(A, fund_size=Money.of("125000000", "USD"), inception=date(2024, 6, 30)),
            B: fund(B, fund_size=None, inception=None),
        },
    )
    (size,) = etf_quality.fund_size(ctx, NO_PARAMS)  # type: ignore[misc]
    assert size == Measurement("IE0000000046", 100_000_000.0)
    (age,) = etf_quality.fund_age(ctx, NO_PARAMS)  # type: ignore[misc]
    assert age.subject == "IE0000000046"
    assert age.observed == pytest.approx(730 / 365.25)


# --------------------------------------------------------------------------- currency and drift
def test_unhedged_foreign_exposure() -> None:
    rates = FixedRates({AS_OF: "1.25"})
    ctx = weighted_context(
        {A: "0.3", B: "0.6"},
        currencies={A: USD},
        to_base=rates,
        instruments={A: fund(A, currency=USD), B: fund(B)},
    )
    assert _one(currency_drift.unhedged_foreign(ctx, NO_PARAMS)).observed == pytest.approx(0.3)
    hedged = weighted_context(
        {A: "0.3", B: "0.6"},
        currencies={A: USD},
        to_base=rates,
        instruments={A: fund(A, currency=USD, hedged_to=EUR), B: fund(B)},
    )
    assert _one(currency_drift.unhedged_foreign(hedged, NO_PARAMS)).observed == 0.0


def test_drift_hand_example() -> None:
    ctx = weighted_context(
        {A: "0.6", B: "0.4"}, target_weights={"IE0000000046": 0.5, "IE0000000053": 0.5}
    )
    largest = _one(currency_drift.max_deviation(ctx, NO_PARAMS))
    assert largest.observed == pytest.approx(0.10)
    assert largest.details == {"holding": "IE0000000053", "deviation": "-0.100000"}
    assert _one(currency_drift.total_drift(ctx, NO_PARAMS)).observed == pytest.approx(0.10)


def test_drift_counts_cash_and_untargeted_holdings() -> None:
    ctx = weighted_context(
        {A: "0.5", B: "0.3", C: "0.1"},  # 10 % cash
        target_weights={"IE0000000046": 0.6, "IE0000000053": 0.3, "cash": 0.1},
    )
    assert current_weights_close(currency_drift.current_weights(ctx))
    total = _one(currency_drift.total_drift(ctx, NO_PARAMS))
    assert total.observed == pytest.approx(0.10)  # A -0.1, C +0.1
    largest = _one(currency_drift.max_deviation(ctx, NO_PARAMS))
    assert largest.observed == pytest.approx(0.10)
    no_targets = weighted_context({A: "1"})
    assert currency_drift.total_drift(no_targets, NO_PARAMS) == NotApplicable(
        "no target weights given"
    )
    assert isinstance(currency_drift.max_deviation(no_targets, NO_PARAMS), NotApplicable)


def current_weights_close(weights: Mapping[str, float]) -> bool:
    expected = {"IE0000000046": 0.5, "IE0000000053": 0.3, "IE0000000061": 0.1, "cash": 0.1}
    return set(weights) == set(expected) and all(
        math.isclose(weights[k], v, abs_tol=1e-12) for k, v in expected.items()
    )


# --------------------------------------------------------------------------- engine boundaries
def _config(**overrides: Thresholds) -> CheckConfig:
    defaults = {
        spec.id: Thresholds(False, 0.0, None, dict.fromkeys(spec.params, 0)) for spec in ALL_CHECKS
    }
    return CheckConfig({**defaults, **overrides})


def test_boundaries_are_strict_through_the_engine() -> None:
    ctx = weighted_context(
        {A: "0.6", B: "0.4"}, target_weights={"IE0000000046": 0.5, "IE0000000053": 0.5}
    )
    above = run_checks(ctx, _config(**{"drift.total": Thresholds(True, 0.09, 0.20, {})}))
    assert [f.severity for f in above.findings] == [Severity.WARNING]
    below = run_checks(
        weighted_context({A: "0.5", B: "0.5"}),
        _config(**{"etf_quality.fund_size": Thresholds(True, 2e9, 1e9, {})}),
    )
    assert [(f.subject, f.severity) for f in below.findings] == [
        ("IE0000000046", Severity.WARNING),
        ("IE0000000053", Severity.WARNING),
    ]
    exact = run_checks(
        weighted_context({A: "1"}),
        _config(**{"etf_quality.fund_size": Thresholds(True, 1e9, None, {})}),
    )
    assert exact.findings == ()
    assert exact.passed == ("etf_quality.fund_size",)


def test_registry_covers_every_category_once() -> None:
    ids = [spec.id for spec in ALL_CHECKS]
    assert len(ids) == len(set(ids)) == 37
