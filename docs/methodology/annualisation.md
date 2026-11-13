# Wrong annualisation

Annualisation turns per-period statistics into yearly figures. It goes wrong when the number of
periods per year does not match the data, or when an arithmetic average is reported as if it
were a compound growth rate. Both errors change returns, volatilities and Sharpe ratios by
large factors, and neither raises an error by itself.

## How it goes wrong

Take twelve monthly returns: 5, −3, 4, −2, 3, −1 % and the same six again. The mean is
1.00 % per month and the sample standard deviation (`ddof=1`) is 3.25 %.

| Statistic | `periods_per_year=12` (right) | `periods_per_year=252` (daily convention) |
|---|---:|---:|
| Annualised arithmetic return | 12.00 % | 252.00 % |
| Annualised geometric return (CAGR) | 12.04 % | 989.18 % |
| Annualised volatility | 11.25 % | 51.55 % |
| Sharpe ratio (series read as excess returns) | 1.07 | 4.89 |

Arithmetic and geometric returns also differ in meaning. Two yearly returns of +50 % and
−50 % have an arithmetic annual mean of **0.0 %**, but 100 invested ends at 75: the compound
annual growth rate is **−13.40 %**.

```python
import pandas as pd
from qrlab.metrics import annualised_arithmetic_return, annualised_geometric_return

r = pd.Series([0.5, -0.5], index=pd.date_range("2022-12-31", periods=2, freq="YE"))
annualised_arithmetic_return(r, periods_per_year=1)  # 0.0
annualised_geometric_return(r, periods_per_year=1)  # -0.1339745962
```

## How qrlab prevents it

- **`periods_per_year` is always explicit.** Every function in {py:mod}`qrlab.metrics` that
  annualises takes `periods_per_year` as a keyword-only argument with no default. Zero,
  negative, infinite, NaN, boolean and string values raise
  {py:class}`qrlab.core.ValidationError`.
- **Conventions are reference only.** `qrlab.core.CONVENTIONAL_PERIODS_PER_YEAR` (252, 52, 12,
  4, 1) is a read-only table that no function applies by default.
  {py:func}`qrlab.core.infer_frequency` is a diagnostic; metrics never use it to choose a
  factor.
- **Geometric and arithmetic are separate functions.**
  {py:func}`qrlab.metrics.annualised_arithmetic_return` is the mean times *P* and is documented
  as not a growth rate. {py:func}`qrlab.metrics.annualised_geometric_return` is
  $W_n^{P/n} - 1$ and raises {py:class}`qrlab.metrics.UndefinedMetricError` when final wealth
  is zero or negative.
- **Volatility and Sharpe scale by √P**, with the sample standard deviation (`ddof=1`). The
  assumption of no serial correlation is stated in the module docstring.
- **No annualising short periods.** {py:func}`qrlab.backtest.summarize_backtest` requires an
  int `periods_per_year` and gives an annualised return only when the backtest covers at least
  one year; otherwise it is `None`. {py:func}`qrlab.lookthrough.tracking_difference`
  annualises only periods of at least 365 days, and its calendar-year figures cover complete
  years only.
- **Day counts are labelled.** The money-weighted return from {py:func}`qrlab.portfolio.xirr`
  carries the label `MWR (XIRR, ACT/365)`.
- **Configs and data declare frequency.** The `backtest`, `optimisation` and `risk_report`
  experiment kinds require `periods_per_year` in the config. A price CSV read with
  {py:func}`qrlab.data.parse_price_csv` raises if the declared frequency does not match the
  spacing of its dates.

## What guards it

- `tests/unit/metrics/test_metrics_public_api.py`:
  `test_conventions_are_keyword_only_without_defaults`.
- `tests/unit/metrics/test_performance.py`: `test_returns_and_volatility_hand_example`,
  `test_geometric_return_consistent_with_core_compound`, `test_volatility_matches_numpy`,
  `test_periods_per_year_must_be_positive_finite_number`, `test_undefined_metrics_raise`
  (case `cagr-wiped-out`).
- `tests/unit/core/test_calendar.py`: `test_conventional_periods_per_year`,
  `test_conventional_table_is_read_only`, `test_infer_frequency`,
  `test_infer_frequency_returns_none_when_unknown`.
- `tests/unit/backtest/test_summary.py`: `test_summary_of_the_toy` (three months are never
  annualised), `test_annualised_figures_over_two_years`,
  `test_single_period_has_no_volatility_and_bad_frequency_raises`.
- `tests/unit/experiments/test_kinds.py`: `test_short_backtests_have_no_annualised_figures`.
- `tests/unit/lookthrough/test_tracking.py`: `test_short_period_is_never_annualised`,
  `test_two_year_annualisation`, `test_calendar_years_are_complete_years_only`.
- `tests/unit/portfolio/test_performance.py`: `test_xirr_closed_form`, `test_mwr_hand_example`
  (checks the label).
- `tests/unit/data/test_user_csv.py`: `test_declared_frequency_must_match_data`.

## Limits

- **`periods_per_year` is not checked against the data.** Metrics, the backtest summary and
  the experiment kinds accept any positive value. Passing 252 for monthly data gives the wrong
  numbers in the table above without an error. Only the price CSV parser compares a declared
  frequency with the dates, and that frequency is not passed on to the metrics.
- **√P assumes serially uncorrelated returns.** Smoothed or autocorrelated series (for
  example appraisal-based NAVs) get a misstated annual volatility and Sharpe ratio. There is no
  autocorrelation adjustment of the scaling. The HAC test
  {py:func}`qrlab.metrics.sharpe_difference_hac` addresses inference on Sharpe differences,
  not the annualisation itself.
- **Different day counts coexist.** Return statistics use the caller's *P*. XIRR, the
  tracking difference and the trading-cost check use 365 days; the fund-age check uses 365.25.
  Each is documented where it is used, but they are not unified.
- **Years in a backtest are counted in periods.** The backtest summary divides the number of
  periods by `periods_per_year`; it does not look at calendar dates.
- **Choosing the measure is the caller's job.** qrlab computes both arithmetic and geometric
  returns; it does not decide which one a report should show.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
