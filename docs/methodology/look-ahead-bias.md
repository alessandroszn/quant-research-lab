# Look-ahead bias

Look-ahead bias means a decision uses information that was not available when the decision
was made. It makes a backtest or a study look better than anything that could have been
traded. Even a small leak can turn noise into an impressive result.

## How it goes wrong

A common mistake in a vectorised backtest is to apply the signal of month *t* to the return of
the same month *t*. The example below uses pure noise: three assets with independent normal
monthly returns (seed 0, 120 months). The rule "hold the asset that did best" has no edge.

```python
import numpy as np
import pandas as pd

rng = np.random.default_rng(0)
index = pd.date_range("2015-01-31", periods=120, freq="ME")
returns = pd.DataFrame(rng.normal(0.005, 0.04, (120, 3)), index=index, columns=["A", "B", "C"])

# Wrong: the winner of month t is known only at the close of t, but it earns month t's return.
signal = returns.eq(returns.max(axis=1), axis=0).astype(float)
naive = (signal * returns).sum(axis=1)
(1 + naive).prod() - 1  # 74.2564, i.e. +7,425.6 % in ten years
```

The same rule run through {py:func}`qrlab.backtest.run_backtest` with `execution_lag=1`
(decide at the close of *t*, trade at the close of *t + 1*) ends at **+108.5 %**, no costs.
The data are noise, so that number is luck too. What matters is the gap: the naive figure
comes only from the leak.

## How qrlab prevents it

- **Execution lag is required and at least 1.** {py:func}`qrlab.backtest.run_backtest` and
  {py:func}`qrlab.backtest.run_backtest_targets` take `execution_lag` as a keyword without a
  default. `0`, a negative number or a non-int raises
  {py:class}`qrlab.core.ValidationError`. A decision at the close of *t* trades at the close
  of *t + L*, so new weights earn returns from *t + L + 1* on.
- **The strategy sees a truncated copy.** A strategy (type `qrlab.backtest.Strategy`) is called with
  `returns.iloc[:t].copy()`. It cannot index a later row, and mutating the copy does not
  change the backtest.
- **Timing is recorded.** Each {py:class}`qrlab.backtest.Execution` stores the `decided` and
  `executed` dates. A decision whose execution would fall after the last period is listed in
  `BacktestResult.not_executed`, not silently dropped or executed early.
- **Availability metadata in data.** Every {py:class}`qrlab.data.Dataset` carries a required
  `availability` text. Some parsers also fill `available_from`, the date each value became
  public: ECB FX rates (same day), €STR (next TARGET2 business day) and HICP
  ({py:func}`qrlab.data.parse_hicp` requires `publication_lag_days`, with no default).
  `available_from` earlier than the reference date raises.
- **Trailing windows only.** {py:func}`qrlab.stats.rolling_ols` labels each estimate with the
  last date of its window. In the studies (`qrlab.studies`), the 1/N strategies use a rolling
  window that ends at the decision month, and the volatility-managed signal is shifted by
  calendar months (`lag >= 1`).
- **As-of checks elsewhere.** {py:func}`qrlab.lookthrough.look_through` raises for a holdings
  snapshot dated after `as_of`. {py:class}`qrlab.scenarios.RiskSummary` raises when the
  estimation window ends after `as_of`.

## What guards it

- `tests/unit/backtest/test_engine.py`: `test_lag_zero_is_refused`,
  `test_strategy_cannot_see_the_future`, `test_lag_hand_example_and_precomputed_targets`,
  `test_late_decisions_are_reported_not_executed`,
  `test_a_leaked_signal_gives_a_different_result`.
- `tests/unit/experiments/test_kinds.py`: `test_backtest_config_errors` (a config with
  `execution_lag = 0` is refused).
- `tests/unit/data/test_ecb.py`: `test_fx_metadata_and_availability`,
  `test_estr_is_available_on_next_target2_business_day`,
  `test_hicp_values_status_and_availability`,
  `test_hicp_publication_lag_must_be_non_negative_int`,
  `test_available_from_cannot_precede_reference_date`.
- `tests/unit/stats/test_factors.py`: `test_rolling_has_no_look_ahead`.
- `tests/unit/studies/test_one_over_n.py`: `test_rolling_window_and_no_look_ahead`.
- `tests/unit/studies/test_volatility_managed.py`: `test_signal_uses_previous_month_by_hand`,
  `test_signal_shifts_by_calendar_month_not_by_row`, `test_real_time_weights_do_not_look_ahead`.
- `tests/unit/lookthrough/test_exposures_overlap.py`: `test_snapshot_checks`.
- `tests/unit/reporting/test_report_risk.py`: `test_summary_is_validated`.

## Limits

- **Closures can still leak.** A strategy that captured the full returns frame, or any other
  data, before the run can read the future. The engine cannot detect this. The test
  `test_a_leaked_signal_gives_a_different_result` does not catch such a leak; it shows that a
  leaky closure gives a very different result. It is documented, not enforced.
- **Precomputed targets are trusted.** {py:func}`qrlab.backtest.run_backtest_targets` applies
  the lag, but it cannot check how the targets were computed. The result only records
  `targets = "precomputed"`.
- **`available_from` is metadata only.** No backtest, metric or study reads it. Aligning a
  signal to its publication date is the caller's job. It is not set for the ECB yield curve,
  Ken French, Open Asset Pricing or user CSV data, where only the `availability` text exists.
- **Revisions are not modelled.** The data are the latest vintage at download time. Ken French
  and Open Asset Pricing files are revised between releases, and HICP flash estimates are
  revised. Only the provenance (download time, checksum) is stored.
- **Intraday timing is out of scope.** The engine works on closes. One period of lag is a
  convention, not a model of when an order can really be filled.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
