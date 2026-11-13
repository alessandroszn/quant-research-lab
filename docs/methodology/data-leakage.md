# Data leakage in validation

Data leakage in validation means the test window is not truly unseen: the model was fitted
with information from it. Out-of-sample results then overstate what the model can do. With
time series this happens through shuffled splits, through labels that overlap the test window,
and through estimation on the full sample.

## How it goes wrong

Take 12 month-end dates from January to December 2020. The label of each month is a 3-month
forward return, so it is known only 3 months later: the label of April 2020 ends in July 2020.

A naive split trains on positions 0–5 (January–June) and tests on 6–8 (July–September). It
looks time-ordered, but the labels of April, May and June end in July, August and September.
These are the test months. Three of the six training labels contain test-window returns.

qrlab removes them (purging):

```python
import pandas as pd
from qrlab.validation import expanding_splits

months = pd.date_range("2020-01-31", periods=12, freq="ME")
ends = pd.Series(months + pd.offsets.MonthEnd(3), index=months)
splits = expanding_splits(months, min_train=6, test_size=3, step=3, embargo=0, label_ends=ends)
first = splits.splits[0]
# first.train -> [0, 1, 2], first.test -> [6, 7, 8], first.purged -> 3
# first.last_label_end -> 2020-06-30, before first.test_start -> 2020-07-31
```

Without `label_ends` the same call trains on [0–5] and purges nothing. A random K-fold split
would be worse: it would train on months after the test window.

## How qrlab prevents it

- **Only walk-forward splits.** {py:mod}`qrlab.validation` provides
  {py:func}`qrlab.validation.expanding_splits` and {py:func}`qrlab.validation.rolling_splits`.
  There are no random, shuffled or K-fold splits. Combinatorial purged cross-validation is left
  out on purpose (see `docs/IDEAS.md`), because it trains on data after the test window.
- **The rule is checked on every split.** Constructing a {py:class}`qrlab.validation.Split`
  raises {py:class}`qrlab.core.ValidationError` if any training label ends on or after the
  first test date, if train and test positions overlap, or if either is empty.
- **Purging.** With `label_ends`, training observations whose label ends on or after the first
  test date are removed and counted in `Split.purged`. A label end before its own date raises.
  A split emptied by purging raises instead of returning an empty training set.
- **Embargo.** `embargo` positions are skipped between the end of training and the start of
  the test window. It is a required argument (an int ≥ 0).
- **No overlapping test windows.** `step` smaller than `test_size` raises. A final test window
  that does not fit is not shortened; the leftover count is reported in `Splits.unused`.
- **No silent re-indexing.** {py:func}`qrlab.validation.take` raises if the data are not on
  the exact index the splits were built on.
- **Results carry a sample tag.** Every table and scalar of an experiment is a
  {py:class}`qrlab.experiments.Tagged` value with tag `in_sample`, `out_of_sample` or
  `descriptive`; any other tag raises. In the `backtest` kind, only the `walk_forward`
  strategy, which re-estimates on past returns at each decision, is tagged `out_of_sample`.
  Rule-based strategies are tagged `in_sample`, because their rules may have been chosen
  after seeing the same history.
- **Studies keep the two apart.** The volatility-managed study (`qrlab.studies`) reports the
  spanning test with a full-sample scale as in sample. Its out-of-sample comparison uses a
  scale estimated only from months before *t*.

## What guards it

- `tests/unit/validation/test_splits.py`: `test_expanding_hand_example`,
  `test_embargo_hand_example`, `test_rolling_hand_example`, `test_purging_hand_example`,
  `test_no_training_label_reaches_the_test_window` (500 seeded random configurations),
  `test_take_checks_the_index`, `test_errors`, `test_label_end_errors`,
  `test_split_rejects_leakage_directly`.
- `tests/unit/experiments/test_kinds.py`: `test_backtest_strategies` (checks the
  `in_sample` / `out_of_sample` tag of each strategy).
- `tests/unit/experiments/test_runner.py`: `test_kind_output_rules` (an unknown tag raises).
- `tests/unit/studies/test_volatility_managed.py`: `test_real_time_weights_do_not_look_ahead`
  (the out-of-sample weight of month *t* uses factor returns up to *t − 1* only).

## Limits

- **No library code uses `qrlab.validation` yet.** The 4.1 design note says optimisation,
  backtests and studies should share these splits. In the code, the `walk_forward` backtest
  strategy and the studies use their own trailing or expanding windows instead. These are
  time-ordered and tested, but they do not go through the `Split` check.
- **"Estimation inside training folds only" is not enforced.** The splits are positions. The
  caller fits the model on the training rows; nothing stops a caller from fitting on the full
  sample.
- **Features can leak.** Splits cannot see how features were built. A feature computed on the
  whole sample before splitting (for example a full-sample z-score) still leaks.
- **Model selection across splits** is not tracked by the splits. Trying many settings and
  keeping the best is a multiple-testing problem (see, for example,
  {py:func}`qrlab.metrics.deflated_sharpe_ratio`), outside the scope of this module.
- **Tags are set by each experiment kind.** The runner checks that a tag is valid, not that it
  is correct.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
