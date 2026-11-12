"""Volatility-managed factors (study 1): hand-calculated cases first, then properties."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from qrlab.core.errors import ValidationError
from qrlab.studies.volatility_managed import (
    BootstrapSettings,
    InSampleResult,
    OutOfSampleResult,
    best_deflated_sharpe,
    full_sample_scale,
    in_sample_spanning,
    in_sample_table,
    inverse_variance_signal,
    out_of_sample_comparison,
    out_of_sample_table,
    real_time_weights,
    realized_variance,
    turnover_costs,
)

BOOT = BootstrapSettings(mean_block_length=3.0, n_resamples=200, confidence=0.9)


def _months(n: int, start: str = "2000-01-31") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="ME")


def _alternating(month: str, size: float, days: int = 20) -> pd.Series:
    index = pd.bdate_range(f"{month}-01", periods=days)
    return pd.Series([size if i % 2 == 0 else -size for i in range(days)], index=index)


def _simulate(rng: np.random.Generator, n_months: int, *, vol_of_vol: float) -> pd.Series:
    """Daily returns with a constant mean and a persistent monthly volatility (AR(1) log-vol)."""
    pieces = []
    state = 0.0
    for month in _months(n_months, "1950-01-31"):
        state = 0.9 * state + vol_of_vol * rng.standard_normal()
        days = pd.bdate_range(month - pd.offsets.MonthBegin(1), month)[:21]
        pieces.append(
            pd.Series(0.0005 + 0.01 * math.exp(state) * rng.standard_normal(len(days)), days)
        )
    return pd.concat(pieces)


def _monthly_sum(daily: pd.Series) -> pd.Series:
    return daily.groupby(pd.DatetimeIndex(daily.index) + pd.offsets.MonthEnd(0)).sum()


# ------------------------------------------------------------------------- realised variance
def test_realized_variance_by_hand() -> None:
    # 20 days of +-1 %: 20 x 0.0001 = 0.0020; 20 days of +-2 %: 20 x 0.0004 = 0.0080.
    daily = pd.concat([_alternating("2000-01", 0.01), _alternating("2000-02", 0.02)])
    rv = realized_variance(daily, demean=False)
    assert list(rv.index) == list(_months(2))
    assert rv.to_numpy() == pytest.approx([0.0020, 0.0080])
    # The +- days have mean zero: demeaning changes nothing.
    assert realized_variance(daily, demean=True).to_numpy() == pytest.approx([0.0020, 0.0080])


def test_realized_variance_demeaned_by_hand() -> None:
    daily = pd.Series([0.01, 0.03], index=pd.to_datetime(["2000-01-03", "2000-01-04"]))
    # Raw: 0.0001 + 0.0009 = 0.0010. Demeaned (mean 0.02): 0.0001 + 0.0001 = 0.0002.
    assert realized_variance(daily, demean=False).iloc[0] == pytest.approx(0.0010)
    assert realized_variance(daily, demean=True).iloc[0] == pytest.approx(0.0002)


def test_realized_variance_rejects_bad_input() -> None:
    one_day = pd.Series([0.01], index=pd.to_datetime(["2000-01-03"]))
    with pytest.raises(ValidationError, match="at least 2 daily"):
        realized_variance(one_day, demean=False)
    flat = pd.Series([0.0, 0.0], index=pd.to_datetime(["2000-01-03", "2000-01-04"]))
    with pytest.raises(ValidationError, match="zero realised variance"):
        realized_variance(flat, demean=False)
    with_nan = pd.Series([0.01, np.nan], index=pd.to_datetime(["2000-01-03", "2000-01-04"]))
    with pytest.raises(ValidationError):
        realized_variance(with_nan, demean=False)
    with pytest.raises(ValidationError, match="demean"):
        realized_variance(one_day, demean=1)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------------ signal
def test_signal_uses_previous_month_by_hand() -> None:
    rv = pd.Series([0.0020, 0.0080], index=_months(2))
    signal = inverse_variance_signal(rv, lag=1)
    # Weight of February uses January's variance (1/0.002), March uses February's (1/0.008).
    assert list(signal.index) == list(_months(2, "2000-02-29"))
    assert signal.to_numpy() == pytest.approx([500.0, 125.0])


def test_signal_shifts_by_calendar_month_not_by_row() -> None:
    rv = pd.Series([0.0020, 0.0080], index=pd.to_datetime(["2000-01-31", "2000-03-31"]))
    signal = inverse_variance_signal(rv, lag=1)
    assert list(signal.index) == list(pd.to_datetime(["2000-02-29", "2000-04-30"]))
    assert list(inverse_variance_signal(rv, lag=2).index) == list(
        pd.to_datetime(["2000-03-31", "2000-05-31"])
    )


def test_signal_rejects_bad_lag_and_variance() -> None:
    rv = pd.Series([0.002], index=_months(1))
    for lag in (0, 1.0, True):
        with pytest.raises(ValidationError, match="lag"):
            inverse_variance_signal(rv, lag=lag)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="positive"):
        inverse_variance_signal(pd.Series([0.0], index=_months(1)), lag=1)
    with pytest.raises(ValidationError, match="month-end"):
        inverse_variance_signal(pd.Series([0.002], index=pd.to_datetime(["2000-01-15"])), lag=1)


# ------------------------------------------------------------------------- full-sample scale
F3 = pd.Series([0.01, -0.01, 0.02], index=_months(3))
S3 = pd.Series([1.0, 2.0, 1.0], index=_months(3))


def test_full_sample_scale_by_hand() -> None:
    # var(f) = 7/30000 and var(s f) = 13/30000 (ddof 1), so c = sqrt(7/13).
    c = full_sample_scale(F3, S3)
    assert c == pytest.approx(math.sqrt(7.0 / 13.0))
    managed = c * S3 * F3
    assert float(managed.std(ddof=1)) == pytest.approx(float(F3.std(ddof=1)), rel=1e-12)


def test_alignment_rejects_gaps_and_short_overlap() -> None:
    gap = pd.Series(
        [1.0, 1.0, 1.0], index=pd.to_datetime(["2000-01-31", "2000-02-29", "2000-04-30"])
    )
    factor = pd.Series([0.01, 0.02, 0.03, 0.04], index=_months(4))
    with pytest.raises(ValidationError, match="consecutive"):
        full_sample_scale(factor, gap)
    with pytest.raises(ValidationError, match="overlap"):
        full_sample_scale(factor, pd.Series([1.0, 2.0], index=_months(2, "2010-01-31")))
    with pytest.raises(ValidationError, match="zero variance"):
        full_sample_scale(pd.Series([0.01, 0.01, 0.01], index=_months(3)), S3)


# --------------------------------------------------------------------------- real-time weights
F5 = pd.Series([0.01, -0.01, 0.02, 0.03, -0.02], index=_months(5))
S5 = pd.Series([1.0, 2.0, 1.0, 1.0, 4.0], index=_months(5))


def test_real_time_weights_by_hand() -> None:
    weights = real_time_weights(F5, S5, burn_in=3, cap=math.inf)
    # Month 4: c from months 1-3 = sqrt(7/13), times s = 1.
    # Month 5: c from months 1-4 = sqrt(8.75e-4 / 1.4e-3) = sqrt(0.625), times s = 4 = sqrt(10).
    assert list(weights.index) == list(_months(5)[3:])
    assert weights.to_numpy() == pytest.approx([math.sqrt(7.0 / 13.0), math.sqrt(10.0)])
    capped = real_time_weights(F5, S5, burn_in=3, cap=2.0)
    assert capped.to_numpy() == pytest.approx([math.sqrt(7.0 / 13.0), 2.0])


def test_real_time_weights_do_not_look_ahead(rng: np.random.Generator) -> None:
    n = 60
    factor = pd.Series(rng.normal(0.005, 0.04, n), index=_months(n))
    signal = pd.Series(rng.uniform(50.0, 500.0, n), index=_months(n))
    base = real_time_weights(factor, signal, burn_in=24, cap=5.0)
    values = factor.to_numpy().copy()
    values[40:] = rng.normal(0.0, 0.2, n - 40)
    changed = pd.Series(values, index=factor.index)
    after = real_time_weights(changed, signal, burn_in=24, cap=5.0)
    # The weight of month t uses factor returns up to t-1 only: weights through month 41 agree.
    pd.testing.assert_series_equal(base.iloc[: 41 - 24], after.iloc[: 41 - 24])
    assert not np.allclose(base.iloc[41 - 24 :], after.iloc[41 - 24 :])


def test_real_time_weights_respect_cap(rng: np.random.Generator) -> None:
    n = 80
    factor = pd.Series(rng.normal(0.005, 0.04, n), index=_months(n))
    signal = pd.Series(rng.lognormal(5.0, 1.0, n), index=_months(n))
    weights = real_time_weights(factor, signal, burn_in=12, cap=5.0)
    assert weights.max() <= 5.0
    assert (weights > 0).all()


def test_real_time_weights_reject_bad_settings() -> None:
    with pytest.raises(ValidationError, match="burn_in"):
        real_time_weights(F5, S5, burn_in=1, cap=5.0)
    with pytest.raises(ValidationError, match="burn_in"):
        real_time_weights(F5, S5, burn_in=5, cap=5.0)
    for cap in (0.0, -1.0, math.nan, 1):
        with pytest.raises(ValidationError, match="cap"):
            real_time_weights(F5, S5, burn_in=3, cap=cap)
    flat = pd.Series([0.01, 0.01, 0.01, 0.02, 0.03], index=_months(5))
    with pytest.raises(ValidationError, match="zero variance"):
        real_time_weights(flat, S5, burn_in=3, cap=5.0)


# ------------------------------------------------------------------------------ turnover costs
def test_turnover_costs_by_hand() -> None:
    weights = pd.Series([1.0, 1.5, 0.5], index=_months(3))
    costs = turnover_costs(weights, cost_per_unit=0.001)
    # The initial position is not charged; then 0.5 x 10 bp and 1.0 x 10 bp.
    assert costs.to_numpy() == pytest.approx([0.0, 0.0005, 0.0010])
    assert (turnover_costs(weights, cost_per_unit=0.0) == 0.0).all()
    for bad in (-0.001, math.inf, 1):
        with pytest.raises(ValidationError, match="cost_per_unit"):
            turnover_costs(weights, cost_per_unit=bad)


# ------------------------------------------------------------------------- in-sample spanning
def test_spanning_matches_the_closed_form(rng: np.random.Generator) -> None:
    n = 120
    factor = pd.Series(rng.normal(0.006, 0.045, n), index=_months(n))
    signal = pd.Series(rng.uniform(100.0, 900.0, n), index=_months(n))
    result = in_sample_spanning(factor, signal, hac_lags=6, periods_per_year=12)
    managed = result.scale * signal * factor
    beta = float(np.cov(managed, factor, ddof=1)[0, 1] / factor.var(ddof=1))
    alpha = float(managed.mean() - beta * factor.mean())
    residuals = managed - alpha - beta * factor
    assert result.beta == pytest.approx(beta)
    assert result.alpha == pytest.approx(alpha)
    assert result.alpha_annual == pytest.approx(12 * alpha)
    sigma = math.sqrt(float((residuals**2).sum()) / (n - 2))
    assert result.appraisal_ratio == pytest.approx(alpha / sigma * math.sqrt(12))
    assert result.n == n
    assert (result.start, result.end) == (factor.index[0], factor.index[-1])
    assert result.sharpe_factor == pytest.approx(
        float(factor.mean() / factor.std(ddof=1)) * math.sqrt(12)
    )
    # Equal volatility by construction: the Sharpe ratios differ only through the means.
    assert result.sharpe_managed / result.sharpe_factor == pytest.approx(
        float(managed.mean() / factor.mean())
    )
    assert 0.0 <= result.alpha_pvalue <= 1.0


def test_volatility_timing_gives_positive_alpha_on_persistent_volatility(
    rng: np.random.Generator,
) -> None:
    daily = _simulate(rng, 900, vol_of_vol=0.45)
    signal = inverse_variance_signal(realized_variance(daily, demean=False), lag=1)
    result = in_sample_spanning(_monthly_sum(daily), signal, hac_lags=6, periods_per_year=12)
    assert result.alpha > 0
    assert result.alpha_pvalue < 0.05


def test_constant_volatility_gives_no_significant_alpha(rng: np.random.Generator) -> None:
    daily = _simulate(rng, 600, vol_of_vol=0.0)
    signal = inverse_variance_signal(realized_variance(daily, demean=False), lag=1)
    result = in_sample_spanning(_monthly_sum(daily), signal, hac_lags=6, periods_per_year=12)
    assert result.alpha_pvalue > 0.05


def test_spanning_rejects_bad_conventions() -> None:
    with pytest.raises(ValidationError, match="periods_per_year"):
        in_sample_spanning(F5, S5, hac_lags=1, periods_per_year=0)
    with pytest.raises(ValidationError, match="hac_lags"):
        in_sample_spanning(F5, S5, hac_lags=-1, periods_per_year=12)


# ------------------------------------------------------------------------ out-of-sample test
def test_out_of_sample_comparison_is_consistent(rng: np.random.Generator) -> None:
    daily = _simulate(rng, 240, vol_of_vol=0.45)
    factor = _monthly_sum(daily)
    signal = inverse_variance_signal(realized_variance(daily, demean=False), lag=1)
    result = out_of_sample_comparison(
        factor,
        signal,
        burn_in=60,
        cap=5.0,
        cost_per_unit=0.001,
        hac_lags=6,
        periods_per_year=12,
        bootstrap=BOOT,
        rng=np.random.default_rng(1),
    )
    weights = real_time_weights(factor, signal, burn_in=60, cap=5.0)
    expected = weights * factor.reindex(weights.index) - turnover_costs(
        weights, cost_per_unit=0.001
    )
    pd.testing.assert_series_equal(result.managed_net, expected, check_names=False)
    pd.testing.assert_series_equal(result.factor, factor.reindex(weights.index), check_names=False)
    assert result.n == len(weights) == 240 - 1 - 60
    assert result.mean_weight == pytest.approx(float(weights.mean()))
    assert result.max_weight == pytest.approx(float(weights.max()))
    assert result.annual_turnover == pytest.approx(float(weights.diff().abs().mean()) * 12)
    assert result.sharpe_managed == pytest.approx(
        float(expected.mean() / expected.std(ddof=1)) * math.sqrt(12)
    )
    assert result.test.pvalue == pytest.approx(
        2 * (1 - __import__("scipy").stats.norm.cdf(abs(result.test.z)))
    )
    assert result.interval.low <= result.interval.estimate <= result.interval.high
    again = out_of_sample_comparison(
        factor,
        signal,
        burn_in=60,
        cap=5.0,
        cost_per_unit=0.001,
        hac_lags=6,
        periods_per_year=12,
        bootstrap=BOOT,
        rng=np.random.default_rng(1),
    )
    assert again.interval == result.interval


def test_bootstrap_settings_are_validated() -> None:
    with pytest.raises(ValidationError, match="mean_block_length"):
        BootstrapSettings(mean_block_length=0.5, n_resamples=200, confidence=0.9)
    with pytest.raises(ValidationError, match="n_resamples"):
        BootstrapSettings(mean_block_length=2.0, n_resamples=10, confidence=0.9)
    with pytest.raises(ValidationError, match="confidence"):
        BootstrapSettings(mean_block_length=2.0, n_resamples=200, confidence=1.0)


# ----------------------------------------------------------------- tables and multiple testing
def _results(
    rng: np.random.Generator,
) -> tuple[dict[str, InSampleResult], list[tuple[str, OutOfSampleResult]]]:
    in_sample: dict[str, InSampleResult] = {}
    out: list[tuple[str, OutOfSampleResult]] = []
    for i, name in enumerate(["A", "B", "C"]):
        daily = _simulate(rng, 200, vol_of_vol=0.2 * i)
        factor = _monthly_sum(daily)
        signal = inverse_variance_signal(realized_variance(daily, demean=False), lag=1)
        in_sample[name] = in_sample_spanning(factor, signal, hac_lags=3, periods_per_year=12)
        for cap in (5.0, math.inf):
            out.append(
                (
                    name,
                    out_of_sample_comparison(
                        factor,
                        signal,
                        burn_in=60,
                        cap=cap,
                        cost_per_unit=0.0,
                        hac_lags=3,
                        periods_per_year=12,
                        bootstrap=BOOT,
                        rng=rng,
                    ),
                )
            )
    return in_sample, out


def test_tables_apply_holm_and_bh_within_each_family(rng: np.random.Generator) -> None:
    in_sample, out = _results(rng)
    table = in_sample_table(in_sample, significance=0.05)
    assert list(table.index) == ["A", "B", "C"]
    p = table["alpha_pvalue"].sort_values()
    # Holm by hand on the sorted p-values: 3 p1, max(., 2 p2), max(., p3), capped at 1.
    holm = np.maximum.accumulate(np.minimum(1.0, np.array([3, 2, 1]) * p.to_numpy()))
    assert table.loc[p.index, "alpha_holm"].to_numpy() == pytest.approx(holm)
    assert (table["alpha_bh"] <= table["alpha_holm"] + 1e-15).all()
    assert set(table.columns) >= {"alpha_annual", "alpha_t", "appraisal_ratio", "r_squared"}

    oos = out_of_sample_table(out, significance=0.05)
    assert len(oos) == 6
    assert list(oos.columns[:3]) == ["factor", "cap", "cost_per_unit"]
    for _, group in oos.groupby(["cap", "cost_per_unit"]):
        assert len(group) == 3
        g = group.set_index("factor")
        p = g["pvalue_hac"].sort_values()
        holm = np.maximum.accumulate(np.minimum(1.0, np.array([3, 2, 1]) * p.to_numpy()))
        assert g.loc[p.index, "holm"].to_numpy() == pytest.approx(holm)
    assert oos["cap"].isin([5.0, math.inf]).all()


def test_tables_reject_empty_input() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        in_sample_table({}, significance=0.05)
    with pytest.raises(ValidationError, match="at least one"):
        out_of_sample_table([], significance=0.05)


def test_best_deflated_sharpe(rng: np.random.Generator) -> None:
    _, out = _results(rng)
    best = best_deflated_sharpe(out, configurations=2)
    assert best is not None
    label, dsr, n_trials = best
    assert n_trials == 6 * 2
    sharpes = {
        f"{name} | cap {r.cap:g} | cost {r.cost_per_unit * 1e4:g} bp": r.managed_net
        for name, r in out
    }
    per_period = {k: float(v.mean() / v.std(ddof=1)) for k, v in sharpes.items()}
    assert label == max(per_period, key=per_period.__getitem__)
    assert dsr.sharpe == pytest.approx(per_period[label])
    assert 0.0 <= dsr.probability <= 1.0
    # One variant: the variance across trials cannot be estimated, so no DSR.
    assert best_deflated_sharpe(out[:1], configurations=3) is None
    with pytest.raises(ValidationError, match="configurations"):
        best_deflated_sharpe(out, configurations=0)
