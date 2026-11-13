# Numerical and silent pandas errors

pandas is built to keep going: it aligns on labels, skips missing values and fills empty groups
without saying so. In financial series these defaults can produce a clean-looking number from
broken data. Floating-point rounding can also flip a discrete choice, such as which observation
falls in a tail.

## How it goes wrong

Two common cases, with the numbers pandas returns:

```python
import numpy as np
import pandas as pd

# 1. A missing day inside a month is skipped, not flagged.
r = pd.Series(
    [0.01, np.nan, 0.01, 0.02, 0.02],
    index=pd.DatetimeIndex(["2026-01-28", "2026-01-29", "2026-01-30", "2026-02-02", "2026-02-03"]),
)
(1 + r).resample("ME").prod() - 1  # January 0.0201, February 0.0404
# A month with no data at all would come out as exactly 0.0.

# 2. Labels shifted by one month are aligned silently.
p = pd.Series(
    [0.01, 0.02, 0.03], index=pd.DatetimeIndex(["2026-01-31", "2026-02-28", "2026-03-31"])
)
b = pd.Series(
    [0.01, 0.02, 0.03], index=pd.DatetimeIndex(["2026-02-28", "2026-03-31", "2026-04-30"])
)
active = p - b  # [NaN, 0.01, 0.01, NaN]
active.mean(), active.std()  # 0.01 and about 2e-18
```

In the first case January reports 2.01 % although one of its three daily returns is unknown. In
the second, the same three returns stored with labels one month apart look like one point a
month of outperformance with no tracking error. Half the rows were dropped without a message.

With qrlab, {py:func}`qrlab.core.aggregate_returns` returns NaN for January (and NaN, not 0, for
an empty month), and {py:func}`qrlab.metrics.tracking_error` on `p` and `b` raises
`AlignmentError: object 1 has a different index from object 0 (3 vs 3 labels); align
explicitly before combining`.

## How qrlab prevents it

- {py:func}`qrlab.core.validate_series` and {py:func}`qrlab.core.validate_frame` check every
  time series at the boundary: a `DatetimeIndex` without `NaT`, strictly increasing, without
  duplicates; real numeric values (booleans refused) copied to `float64`; no infinite values;
  unique column labels. An unsorted or duplicated index raises instead of being sorted.
- Missing values follow an explicit {py:class}`qrlab.core.NanPolicy` (`RAISE`, `DROP` or
  `KEEP`). It is a required keyword argument, and anything other than the enum raises. The risk
  models take it as a `missing` argument (`RAISE` or `DROP` only), and covariance estimates
  report how many rows were dropped.
- {py:func}`qrlab.core.require_same_index` compares indexes element by element, including the
  time zone, and raises `AlignmentError`. The relative metrics, the Sharpe-ratio tests,
  attribution, tracking, regression, the factor risk model and the return conversions call it
  instead of aligning.
- {py:func}`qrlab.core.aggregate_returns` makes a bucket NaN if it contains a NaN or has fewer
  than `min_periods` observations, and returns the observation count of every bucket.
- The metrics refuse NaN. Too few observations or a zero variance raise
  {py:class}`qrlab.metrics.UndefinedMetricError` instead of returning `inf` or NaN.
- Inputs are never modified: validation returns a copy.
- Tolerances are explicit and weights are never rescaled silently (for example, weights must
  sum to 1 within 1e-9). Known floating-point traps are handled in code: the tail size of
  historical VaR is rounded before taking the ceiling, and optimiser noise of order 1e-16 is
  snapped to zero.
- Money in the portfolio ledger is {py:class}`qrlab.core.Money`, a `Decimal` amount with a
  currency. Monte Carlo projections work in floating point.

## What guards it

- `pyproject.toml`, `[tool.pytest.ini_options]`: `filterwarnings = ["error"]`, so any warning
  raised during the tests (pandas, NumPy, SciPy) fails the test run. The same file sets mypy to
  strict and enables Ruff's pandas-vet (`PD`) and NumPy (`NPY`) rules.
- `tests/unit/core/test_series.py`: `test_nan_policy_raise`, `test_nan_policy_drop`,
  `test_nan_policy_keep`, `test_all_nan_under_each_policy`, `test_nan_policy_must_be_enum`,
  `test_unsorted_index_raises`, `test_duplicated_index_raises`, `test_nat_in_index_raises`,
  `test_infinite_values_raise`, `test_non_real_numeric_dtypes_raise`,
  `test_input_is_not_mutated`, `test_different_index_raises`,
  `test_tz_mismatch_raises_even_for_same_instants`.
- `tests/unit/core/test_returns.py`: `test_aggregate_nan_inside_bucket_gives_nan_not_zero`,
  `test_aggregate_empty_bucket_in_gap_is_nan`, `test_aggregate_flags_partial_periods_as_nan`,
  `test_aggregate_matches_independent_groupby`, `test_nan_price_propagates_to_both_adjacent_returns_and_is_not_filled`.
- `tests/unit/metrics/test_relative.py`: `test_benchmark_must_share_the_index`.
- `tests/unit/metrics/test_risk.py`: `test_floating_point_tail_size_regression`, `test_nan_refused`.
- `tests/unit/optimization/test_mean_variance.py`:
  `test_solver_noise_is_snapped_and_tiny_volatility_is_zero`.
- Cross-checks against independent implementations: `test_capm_matches_statsmodels`
  (`tests/unit/metrics/test_relative.py`), `test_matches_statsmodels` and
  `test_newey_west_matches_independent_formula` (`tests/unit/stats/test_regression.py`),
  `test_matches_statsmodels` (`tests/unit/stats/test_multiple_testing.py`),
  `test_moments_match_scipy` (`tests/unit/metrics/test_performance.py`),
  `test_parametric_es_matches_numerical_integration` (`tests/unit/metrics/test_risk.py`),
  `test_ledoit_wolf_matches_scikit_learn` and
  `test_sample_covariance_matches_numpy_and_reports_dropped_rows`
  (`tests/unit/risk/test_covariance_decomposition.py`).
- All randomness in tests comes from the seeded `rng` fixture in `tests/conftest.py`.

## Limits

- Warnings are errors only under pytest. When the CLI or the desktop app runs, warnings are
  not escalated.
- The Monte Carlo plan code (`qrlab.simulation.plan`) silences NumPy divide and invalid-value
  warnings in four places with `np.errstate`; the affected values are replaced through
  `np.where` right after.
- `NanPolicy.KEEP` passes NaN downstream on purpose, and `NanPolicy.DROP` shortens the sample.
  The caller chooses; the code does not judge whether the choice is sensible.
- {py:func}`qrlab.core.require_same_index` catches different labels, not wrong ones. Two
  series that are both mislabelled in the same way pass.
- Cross-checks cover the regression, covariance, moment and multiple-testing code listed above,
  not every function.
- Calculations are in `float64`, apart from the `Decimal` amounts in the ledger. The
  tolerances (such as 1e-9 for weights) are fixed constants, not tuned to the data.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
