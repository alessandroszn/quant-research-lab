"""Factor risk model, Cornish-Fisher and filtered-historical VaR, forecasts and backtests.

Hand values (design note 3.1):

- Cornish-Fisher with S = -0.5, K = 1 at 95 %: z = -1.644854, z_cf = -1.762106; with mean 0 and
  standard deviation 1 %, VaR = 1.762106 %;
- Kupiec with n = 250, p = 1 % and 5 exceedances: LR = 1.956810, p-value 0.1619;
- Christoffersen with hits 0 0 1 1 0 0 0 1 0 0: n00 = 4, n01 = 2, n10 = 2, n11 = 1,
  pi0 = pi1 = 1/3, LR_ind = 0.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import integrate, stats

from qrlab.core.errors import AlignmentError, ValidationError
from qrlab.core.returns import ReturnKind
from qrlab.core.series import NanPolicy
from qrlab.metrics.errors import UndefinedMetricError
from qrlab.metrics.risk import historical_es, historical_var, parametric_es, parametric_var
from qrlab.risk import (
    cornish_fisher,
    factor_contributions,
    filtered_historical,
    fit_factor_model,
    sample_covariance,
    var_backtest,
    var_forecasts,
    var_methods,
    volatility_contributions,
)

SIMPLE = ReturnKind.SIMPLE
RAISE = NanPolicy.RAISE


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2000-01-03", periods=n, freq="B")


def _standardised(rng: np.random.Generator, n: int, std: float) -> pd.Series:
    raw = rng.standard_normal(n)
    raw = (raw - raw.mean()) / raw.std(ddof=1) * std
    return pd.Series(raw, index=_index(n))


def _sample_cov(frame: pd.DataFrame):  # type: ignore[no-untyped-def]
    return sample_covariance(frame, kind=SIMPLE, missing=RAISE)


# --------------------------------------------------------------------------- factor model
def test_factor_model_recovers_betas_and_adds_up(rng: np.random.Generator) -> None:
    n = 2000
    f = pd.DataFrame(rng.normal(0.0, 0.01, size=(n, 2)), index=_index(n), columns=["mkt", "val"])
    noise = rng.normal(0.0, 0.002, size=(n, 2))
    assets = pd.DataFrame(
        {
            "a": 0.0001 + 1.2 * f["mkt"] - 0.5 * f["val"] + noise[:, 0],
            "b": 0.8 * f["mkt"] + noise[:, 1],
        }
    )
    model = fit_factor_model(assets, f, kind=SIMPLE, missing=RAISE, factor_covariance=_sample_cov)
    np.testing.assert_allclose(model.betas.to_numpy(), [[1.2, -0.5], [0.8, 0.0]], atol=0.02)
    assert model.specific_variance.to_list() == pytest.approx([0.002**2] * 2, rel=0.1)
    assert (model.r_squared > 0.9).all()
    assert (model.n_obs, model.dropped_rows) == (n, 0)
    weights = pd.Series({"a": 0.6, "b": 0.4})
    split = factor_contributions(model, weights)
    assert float(split.factor.sum() + split.specific.sum()) == pytest.approx(split.total)
    assert split.total == pytest.approx(volatility_contributions(model.covariance(), weights).total)
    assert split.exposures["mkt"] == pytest.approx(
        float(np.array([0.6, 0.4]) @ model.betas["mkt"].to_numpy())
    )
    with pytest.raises(UndefinedMetricError, match="zero"):
        factor_contributions(model, pd.Series({"a": 0.0, "b": 0.0}))


def test_factor_model_inputs_are_checked(rng: np.random.Generator) -> None:
    n = 30
    f = pd.DataFrame(rng.normal(0.0, 0.01, size=(n, 1)), index=_index(n), columns=["mkt"])
    assets = pd.DataFrame({"a": rng.normal(0.0, 0.01, n)}, index=_index(n))
    with pytest.raises(ValidationError, match="overlap"):
        fit_factor_model(assets.rename(columns={"a": "mkt"}), f, kind=SIMPLE, missing=RAISE,
                         factor_covariance=_sample_cov)  # fmt: skip
    with pytest.raises(AlignmentError):
        fit_factor_model(assets.iloc[1:], f, kind=SIMPLE, missing=RAISE,
                         factor_covariance=_sample_cov)  # fmt: skip
    gappy = assets.copy()
    gappy.iloc[3, 0] = np.nan
    model = fit_factor_model(gappy, f, kind=SIMPLE, missing=NanPolicy.DROP,
                             factor_covariance=_sample_cov)  # fmt: skip
    assert (model.n_obs, model.dropped_rows) == (n - 1, 1)


# --------------------------------------------------------------------------- Cornish-Fisher
def test_cornish_fisher_hand_example(
    rng: np.random.Generator, monkeypatch: pytest.MonkeyPatch
) -> None:
    returns = _standardised(rng, 500, 0.01)
    monkeypatch.setattr(var_methods, "skewness", lambda r: -0.5)
    monkeypatch.setattr(var_methods, "excess_kurtosis", lambda r: 1.0)
    result = cornish_fisher(returns, confidence=0.95)
    assert result.z == pytest.approx(-1.644854, abs=1e-6)
    assert result.z_cf == pytest.approx(-1.762106, abs=1e-6)
    assert result.var == pytest.approx(0.01762106, abs=1e-8)
    tail = integrate.quad(
        lambda u: -0.01 * var_methods._quantile(float(stats.norm.ppf(1 - u)), -0.5, 1.0), 0.95, 1
    )[0]
    assert result.es == pytest.approx(tail / 0.05, rel=1e-8)


def test_cornish_fisher_without_skew_or_kurtosis_is_normal(
    rng: np.random.Generator, monkeypatch: pytest.MonkeyPatch
) -> None:
    returns = _standardised(rng, 300, 0.02) + 0.001
    monkeypatch.setattr(var_methods, "skewness", lambda r: 0.0)
    monkeypatch.setattr(var_methods, "excess_kurtosis", lambda r: 0.0)
    result = cornish_fisher(returns, confidence=0.99)
    assert result.var == pytest.approx(parametric_var(returns, confidence=0.99))
    assert result.es == pytest.approx(parametric_es(returns, confidence=0.99))


def test_cornish_fisher_uses_the_sample_moments(rng: np.random.Generator) -> None:
    returns = pd.Series(rng.standard_t(8, 1000) * 0.01, index=_index(1000))
    result = cornish_fisher(returns, confidence=0.99)
    assert result.skewness == pytest.approx(float(stats.skew(returns, bias=False)))
    assert result.excess_kurtosis == pytest.approx(float(stats.kurtosis(returns, bias=False)))
    assert result.es > result.var > 0


@pytest.mark.parametrize(("s", "k"), [(0.0, -3.0), (0.6, 0.48), (2.0, 6.0)])
def test_cornish_fisher_refuses_a_non_monotone_expansion(
    s: float, k: float, rng: np.random.Generator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(var_methods, "skewness", lambda r: s)
    monkeypatch.setattr(var_methods, "excess_kurtosis", lambda r: k)
    with pytest.raises(UndefinedMetricError, match="not a quantile"):
        cornish_fisher(_standardised(rng, 50, 0.01), confidence=0.99)


# --------------------------------------------------------------------------- filtered HS
def test_filtered_historical_hand_example() -> None:
    returns = pd.Series([0.01, -0.01, 0.02, 0.0, -0.03], index=_index(5))
    result = filtered_historical(returns, confidence=0.5, decay=0.5, warmup=2)
    var = 2e-4  # ddof=1 variance of 0.01 and -0.01
    z = []
    for r in (0.02, 0.0, -0.03):
        z.append(r / math.sqrt(var))
        var = 0.5 * var + 0.5 * r * r
    zs = pd.Series(z, index=_index(3))
    assert result.next_volatility == pytest.approx(math.sqrt(var))
    assert result.var == pytest.approx(math.sqrt(var) * historical_var(zs, confidence=0.5))
    assert result.es == pytest.approx(math.sqrt(var) * historical_es(zs, confidence=0.5))
    assert result.n_filtered == 3


def test_filtered_historical_inputs() -> None:
    returns = pd.Series([0.01, 0.01, 0.02, 0.0], index=_index(4))
    with pytest.raises(UndefinedMetricError, match="zero variance"):
        filtered_historical(returns, confidence=0.5, decay=0.9, warmup=2)
    for decay, warmup in ((1.0, 2), (0.9, 1), (0.9, 2.0)):
        with pytest.raises(ValidationError):
            filtered_historical(returns, confidence=0.5, decay=decay, warmup=warmup)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="confidence"):
        filtered_historical(returns, confidence=1.5, decay=0.9, warmup=2)


# --------------------------------------------------------------------------- forecasts
def test_forecasts_use_only_earlier_returns(rng: np.random.Generator) -> None:
    returns = pd.Series(rng.normal(0.0, 0.01, 60), index=_index(60))
    model = lambda r: historical_var(r, confidence=0.9)  # noqa: E731
    forecasts = var_forecasts(returns, window=20, model=model)
    assert forecasts.index[0] == returns.index[20]
    assert len(forecasts) == 40
    assert forecasts.iloc[0] == historical_var(returns.iloc[:20], confidence=0.9)
    shocked = returns.copy()
    shocked.iloc[30] = -0.5  # a crash on day 30 cannot change the forecast for day 30
    after = var_forecasts(shocked, window=20, model=model)
    pd.testing.assert_series_equal(
        forecasts.loc[: returns.index[30]], after.loc[: returns.index[30]]
    )
    assert after.loc[returns.index[31]] > forecasts.loc[returns.index[31]]
    with pytest.raises(ValidationError, match="window"):
        var_forecasts(returns, window=1, model=model)
    with pytest.raises(ValidationError, match="no forecast"):
        var_forecasts(returns, window=60, model=model)


# --------------------------------------------------------------------------- backtests
def _hits_to_returns(hits: list[int]) -> tuple[pd.Series, pd.Series]:
    index = _index(len(hits))
    returns = pd.Series([-0.05 if h else 0.01 for h in hits], index=index)
    return returns, pd.Series(0.02, index=index)


def test_kupiec_hand_example() -> None:
    hits = [1 if i % 50 == 0 else 0 for i in range(250)]
    assert sum(hits) == 5
    result = var_backtest(*_hits_to_returns(hits), confidence=0.99)
    assert (result.n, result.exceedances) == (250, 5)
    assert result.expected == pytest.approx(2.5)
    assert result.kupiec_lr == pytest.approx(1.956810, abs=1e-6)
    assert result.kupiec_pvalue == pytest.approx(0.1619, abs=1e-4)


def test_christoffersen_hand_example() -> None:
    result = var_backtest(*_hits_to_returns([0, 0, 1, 1, 0, 0, 0, 1, 0, 0]), confidence=0.9)
    assert result.transitions == (4, 2, 2, 1)
    assert result.independence_lr == pytest.approx(0.0, abs=1e-12)
    assert result.conditional_coverage_lr == pytest.approx(result.kupiec_lr)
    clustered = var_backtest(*_hits_to_returns([0, 0, 0, 0, 1, 1, 1, 0, 0, 0]), confidence=0.9)
    assert clustered.transitions == (5, 1, 1, 2)
    pi0, pi1, pi = 1 / 6, 2 / 3, 1 / 3
    expected = -2 * (
        6 * math.log(1 - pi) + 3 * math.log(pi)
        - 5 * math.log(1 - pi0) - math.log(pi0) - math.log(1 - pi1) - 2 * math.log(pi1)
    )  # fmt: skip
    assert clustered.independence_lr == pytest.approx(expected)


def test_backtest_edges() -> None:
    none = var_backtest(*_hits_to_returns([0] * 100), confidence=0.99)
    assert none.exceedances == 0
    assert none.kupiec_lr == pytest.approx(-2 * 100 * math.log(0.99))
    assert none.independence_lr == 0.0
    assert none.notes
    every = var_backtest(*_hits_to_returns([1] * 10), confidence=0.99)
    assert every.hit_rate == 1.0
    assert every.notes
    returns, forecasts = _hits_to_returns([0, 1, 0])
    with pytest.raises(AlignmentError):
        var_backtest(returns, forecasts.iloc[1:], confidence=0.99)
    with pytest.raises(ValidationError, match="two forecasts"):
        var_backtest(returns.iloc[:1], forecasts.iloc[:1], confidence=0.99)
    with pytest.raises(ValidationError, match="confidence"):
        var_backtest(returns, forecasts, confidence=99)


def test_simulated_exceedance_rate_matches_the_confidence(rng: np.random.Generator) -> None:
    n = 10_000
    returns = pd.Series(rng.standard_normal(n), index=_index(n))
    true_var = pd.Series(-float(stats.norm.ppf(0.01)), index=returns.index)
    result = var_backtest(returns, true_var, confidence=0.99)
    standard_error = math.sqrt(0.01 * 0.99 / n)
    assert abs(result.hit_rate - 0.01) < 3 * standard_error
    assert result.kupiec_pvalue > 0.05
