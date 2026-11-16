# Benchmark mismatch

A portfolio or fund is only comparable with a benchmark measured the same way: same dates and
frequency, same currency and hedging, and the same return type (total return with dividends, or
price only). A mismatch turns a currency move, missing dividends or a shifted date into apparent
outperformance or tracking error.

## How it goes wrong

A EUR fund tracks a world equity index. Over one year the fund's NAV rises 4.50 % in EUR. The
index total return is 10.00 % in USD, and the dollar weakens from 1.10 to 1.155 USD per EUR.

- Naive comparison (EUR fund against the USD index): 4.50 % − 10.00 % = −5.50 points.
- The index in EUR: 1.10 × 1.10 / 1.155 − 1 = 4.76 %.
- Correct tracking difference: 4.50 % − 4.76 % = −0.26 points.

Almost all of the naive gap is the currency, not the fund. A price-only index makes the opposite
error: it leaves out the dividends the fund received, and the fund appears to beat its index.

```python
import pandas as pd
from qrlab.core import Currency, ReturnKind, convert_return_currency
from qrlab.data import PriceType
from qrlab.lookthrough import TrackingSeries, tracking_difference

dates = pd.DatetimeIndex(["2025-12-31", "2026-12-31"])
fund = TrackingSeries(pd.Series([100.0, 104.5], index=dates), PriceType.NAV, Currency("EUR"), None)
usd_index = TrackingSeries(
    pd.Series([100.0, 110.0], index=dates), PriceType.TOTAL_RETURN, Currency("USD"), None
)
tracking_difference(fund, usd_index)
# ValidationError: fund in EUR (hedged to none) and index in USD (hedged to none):
# a currency effect would be read as tracking

eur_per_usd = pd.Series([1 / 1.10, 1 / 1.155], index=dates)
index_eur = convert_return_currency(
    pd.Series([0.10], index=dates[1:]), eur_per_usd, kind=ReturnKind.SIMPLE
)
# index_eur.iloc[0] = 0.047619; against a EUR total-return index the difference is -0.002619
```

## How qrlab prevents it

- {py:func}`qrlab.lookthrough.tracking_difference` and {py:func}`qrlab.lookthrough.tracking_error`
  take {py:class}`qrlab.lookthrough.TrackingSeries`, which carry the price type, the currency and
  the hedge currency. The fund must be NAV or total return and the index total return; currency
  and hedging must match; the dates must be identical. Otherwise they raise. A tracking
  difference is never annualised from less than 365 days.
- The benchmark-relative metrics {py:func}`qrlab.metrics.tracking_error`,
  {py:func}`qrlab.metrics.information_ratio`, {py:func}`qrlab.metrics.capm_regression`,
  {py:func}`qrlab.metrics.up_capture` and {py:func}`qrlab.metrics.down_capture` call
  {py:func}`qrlab.core.require_same_index`. Portfolio and benchmark must have exactly the same
  dates and time zone, or an `AlignmentError` is raised. Nothing is aligned silently, so a daily
  series cannot be compared with a monthly one. NaN values are refused.
- {py:func}`qrlab.attribution.brinson_fachler` requires the same index on all four inputs and
  the same segments in the same order.
- Changing currency is an explicit step: {py:func}`qrlab.core.convert_return_currency` uses
  dated exchange rates, one per return date plus the start of the first period.
  {py:func}`qrlab.attribution.currency_attribution` splits an active return into local-market,
  currency and cross terms.
- Changing frequency is an explicit step too: {py:func}`qrlab.core.aggregate_returns` compounds
  returns into the target {py:class}`qrlab.core.Frequency`.
- `periods_per_year` is a required argument of every annualised relative metric.
- **The portfolio report's benchmark** (phase 11.2):
  - **Total return only:** it must be a total-return series, because the portfolio's TWR
    includes the income received. An accumulating fund's price qualifies and is declared so.
  - **Currency and dates:** it is valued in the base currency with the ECB rate of each
    valuation date, and its last level and rate may be no older than the staleness limits.
  - **The periods:** it is compared on the TWR periods between two valuation dates only.
  - **What the report shows:** the benchmark's name, the window and the conventions next to
    the numbers.

## What guards it

- `tests/unit/lookthrough/test_tracking.py`: `test_series_must_be_comparable` (price-only
  series, different currencies, different hedging and different dates all raise),
  `test_one_year_hand_example`, `test_short_period_is_never_annualised`.
- `tests/unit/metrics/test_relative.py`: `test_benchmark_must_share_the_index`.
- `tests/unit/experiments/test_portfolio_benchmark.py`: the three-month hand case, the
  constant risk-free rate, a USD benchmark valued in EUR, carried and refused values, the
  cross-check against NumPy.
- `tests/unit/experiments/test_portfolio_report_risk.py`: `test_benchmark_by_hand` (with the
  `risk.beta` check), `test_bad_benchmarks_fail_the_run` (two columns, a price index, a
  foreign currency without rates), `test_the_benchmark_inputs_go_together`.
- `tests/unit/core/test_series.py`: `test_different_index_raises`,
  `test_tz_mismatch_raises_even_for_same_instants`, `test_naive_vs_aware_raises`.
- `tests/unit/core/test_returns.py`: `test_convert_return_currency_hand_example`,
  `test_convert_return_currency_index_must_follow_fx`,
  `test_excess_returns_refuse_misaligned_inputs`.
- `tests/unit/attribution/test_brinson.py`: `test_input_errors`.
- `tests/unit/attribution/test_factor_currency.py`: `test_currency_hand_example`,
  `test_currency_active_parts_add_up`.

## Limits

- The risk register says matching frequency, currency and return type are enforced. That is
  fully true only for the tracking functions in `qrlab.lookthrough`, whose inputs carry this
  information.
- The functions in `qrlab.metrics` and `qrlab.attribution` take plain pandas objects. They
  enforce identical dates, and so the same frequency, but they cannot check currency or total
  versus price return. The module docstring of `qrlab.metrics.relative` states that this is the
  caller's responsibility. {py:class}`qrlab.data.Dataset` records a currency and a return kind,
  but these functions do not read it.
- `periods_per_year` is not checked against the dates: monthly data annualised with 252 is
  accepted.
- Two series with identical but wrong dates (for example both shifted by one month) pass every
  check.
- Whether a benchmark is the right one (same universe, same risk) is a research judgement. The
  code does not assess it.
- The `portfolio_report` experiment kind passes no benchmark returns to the health checks, so
  the beta check is not applicable in config runs, and the report has no benchmark comparison.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
