# Return misalignment

Return misalignment means two series are combined period by period, but their rows do not
refer to the same periods. Typical causes are a one-period shift, different date labels for
the same month, or a silent intersection of indexes. Active returns, excess returns, betas and
correlations are then computed on mismatched pairs, often without any error.

## How it goes wrong

A fund has monthly returns from January to April 2024. Its benchmark file also contains
December 2023. Both are labelled by month end.

| Month | Fund | Benchmark |
|---|---:|---:|
| Dec 2023 | – | 1.5 % |
| Jan 2024 | 2.0 % | 1.8 % |
| Feb 2024 | −1.0 % | −1.2 % |
| Mar 2024 | 3.0 % | 2.7 % |
| Apr 2024 | 1.0 % | 1.2 % |

Matched by month, the active returns are 0.2, 0.2, 0.3 and −0.2 percentage points. The
annualised tracking error (`ddof=1`, 12 periods per year) is **0.77 %**.

Pairing the first four values by position instead (fund January with benchmark December, and
so on) gives active returns of 0.5, −2.8, 4.2 and −1.7 points and a tracking error of
**10.70 %**, about fourteen times too large.

A label mismatch fails in another way. With pandas, subtracting a risk-free series labelled at
month start (`2024-01-01`) from returns labelled at month end (`2024-01-31`) gives eight NaN
values, one per label, and no error.

```python
import pandas as pd
from qrlab.core import ReturnKind, excess_returns
from qrlab.metrics import tracking_error

fund = pd.Series(
    [0.020, -0.010, 0.030, 0.010], index=pd.date_range("2024-01-31", periods=4, freq="ME")
)
benchmark = pd.Series(
    [0.015, 0.018, -0.012, 0.027, 0.012], index=pd.date_range("2023-12-31", periods=5, freq="ME")
)
rf_month_start = pd.Series(0.003, index=pd.date_range("2024-01-01", periods=4, freq="MS"))

fund - rf_month_start  # 8 NaN, no error (pandas)
tracking_error(fund, benchmark, periods_per_year=12)  # AlignmentError: 5 vs 4 labels
tracking_error(fund, benchmark.iloc[1:], periods_per_year=12)  # 0.00768
excess_returns(fund, rf_month_start, kind=ReturnKind.SIMPLE)  # AlignmentError
```

## How qrlab prevents it

- **One conventions module.** {py:mod}`qrlab.core` holds the return conventions
  (`qrlab.core.returns`). Every function there takes the return kind as a required
  {py:class}`qrlab.core.ReturnKind`. {py:func}`qrlab.core.prices_to_returns` labels each return
  with the later date of its price pair (the end of the period) and drops the first date.
- **Validated indexes.** {py:func}`qrlab.core.validate_series` and
  {py:func}`qrlab.core.validate_frame` require a `DatetimeIndex` without `NaT`, strictly
  increasing, with no duplicates. An unsorted index raises; it is never sorted silently.
- **Explicit alignment only.** {py:func}`qrlab.core.require_same_index` raises
  {py:class}`qrlab.core.AlignmentError` unless all indexes are equal element by element and
  have the same time zone. The same instants in two time zones count as different.
- **Used where series meet.** It guards, among others, {py:func}`qrlab.core.excess_returns`,
  {py:func}`qrlab.core.convert_return_currency` (the FX series must have the returns' dates
  plus one earlier date), {py:func}`qrlab.metrics.tracking_error`,
  {py:func}`qrlab.metrics.information_ratio`, {py:func}`qrlab.metrics.capm_regression`, the
  capture ratios, {py:func}`qrlab.stats.ols`, {py:func}`qrlab.stats.rolling_ols`,
  {py:func}`qrlab.lookthrough.tracking_difference` and
  {py:func}`qrlab.attribution.brinson_fachler`. Indexes are never intersected for the caller.
- **Calendar shifts, not row shifts.** The volatility-managed study (`qrlab.studies`) shifts its
  signal by calendar months and raises on a gap in the monthly series, so a missing month
  cannot move later values into the wrong row.

## What guards it

- `tests/unit/core/test_series.py`: `test_unsorted_index_raises`,
  `test_duplicated_index_raises`, `test_nat_in_index_raises`, `test_different_index_raises`,
  `test_tz_mismatch_raises_even_for_same_instants`, `test_naive_vs_aware_raises`.
- `tests/unit/core/test_returns.py`: `test_prices_to_simple_returns_hand_example` (labels),
  `test_kind_must_be_enum`, `test_excess_returns_refuse_misaligned_inputs`,
  `test_convert_return_currency_index_must_follow_fx`.
- `tests/unit/metrics/test_relative.py`: `test_benchmark_must_share_the_index`.
- `tests/unit/stats/test_regression.py`: `test_misaligned_and_nan_inputs_raise`.
- `tests/unit/lookthrough/test_tracking.py`: `test_series_must_be_comparable`.
- `tests/unit/studies/test_volatility_managed.py`:
  `test_signal_shifts_by_calendar_month_not_by_row`,
  `test_alignment_rejects_gaps_and_short_overlap`.

## Limits

- **Equal labels are not proof of equal periods.** A file that labels months by their first
  day passes validation. Two series measured at different times of day, or one shifted and
  then relabelled by the user, also pass. qrlab checks labels, not what they mean.
- **The kind is not carried by a series.** Metrics and the backtest engine take simple returns
  by contract and have no `ReturnKind` argument. A log-return series passed to them is not
  detected. {py:class}`qrlab.data.Dataset` records `return_kind` for return data, but
  nothing checks it downstream.
- **A few explicit intersections exist.** The diversification check (average correlation of
  positions) uses only dates common to all positions. The rebalancing study joins equity and
  bond returns on common months, then raises if a month is missing. These joins are written in
  the code, not done by pandas implicitly, but they drop dates.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
