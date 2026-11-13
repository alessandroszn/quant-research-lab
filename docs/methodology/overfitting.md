# Overfitting and multiple testing

Trying many strategies, parameters or predictors and reporting the best one makes noise look
like skill. A single test at the 5 % level is wrong one time in twenty by design; the best of
many tries is wrong far more often. Results that ignore how many configurations were tried,
or that mix in-sample fits with out-of-sample checks, overstate the evidence.

## How it goes wrong

A researcher tests 20 variants of a strategy on 120 months of data. None has any true edge.

```python
p_at_least_one_false_positive = 1 - 0.95**20  # 0.64 with 20 independent tests
# Expected best monthly Sharpe ratio among 20 trials of pure noise, taking the variance
# of an estimated Sharpe ratio as about 1 / 120:
expected_best = 0.1735  # about 0.60 annualised
```

Now suppose the best variant shows a monthly Sharpe ratio of 0.25 (0.87 annualised) with
normal returns. Its probabilistic Sharpe ratio against zero is 0.996, which looks decisive.
Against the expected best of 20 noise trials (the deflated Sharpe ratio) it is 0.794; against
100 trials it is 0.581. The same number means much less once the search is counted.

P-values need the same care. With p-values 0.01, 0.02 and 0.04 among 20 tests (the other 17
at 0.5), all three are "significant" one at a time. Holm's adjusted p-values are 0.20, 0.38
and 0.72; Benjamini-Hochberg's are 0.20, 0.20 and 0.27. None survives at 5 %.

## How qrlab prevents it

- **A ledger of configurations tried.** Every run through
  {py:func}`qrlab.experiments.run_experiment` (the path used by scripts, the CLI and the app)
  appends a line to `trials.jsonl` in the parent of the output folder: experiment name, config
  hash, time and status. `record.json` stores `configurations_tried`, the number of distinct
  config hashes recorded under that name ({py:func}`qrlab.experiments.count_trials`). The hash
  ({py:func}`qrlab.experiments.config_hash`) covers every table except `[output]`, so re-running
  the same config or moving its results is not a new trial. Failed runs are recorded too.
- **A stated hypothesis.** Every config needs a non-empty `hypothesis` in `[experiment]`.
- **Deflated Sharpe ratio.** {py:func}`qrlab.metrics.deflated_sharpe_ratio` is the
  probabilistic Sharpe ratio measured against {py:func}`qrlab.metrics.expected_max_sharpe` of
  the trials. It needs `n_trials` and either the trials' Sharpe ratios or their variance; it
  has no default. The volatility-managed and 1/N studies compute it for their best variant
  with `n_trials` = variants in the run x configurations tried
  ({py:func}`qrlab.experiments.configurations_tried`), and record `dsr_probability` and
  `dsr_trials`.
- **Multiple-testing corrections.** {py:func}`qrlab.stats.adjust_pvalues` applies
  {py:class}`qrlab.stats.Correction` `HOLM` (family-wise error), `BENJAMINI_HOCHBERG` or
  `BENJAMINI_YEKUTIELI` (false discovery rate); method and `alpha` are required. The factor-zoo
  study counts significant predictors under all three and under a t-statistic threshold
  (`hlz_threshold`, 3.0 in the shipped configs), next to the single-test count. The 1/N and volatility-managed studies add Holm and BH columns within
  each family of comparisons.
- **In-sample and out-of-sample are tagged.** Each table and scalar a kind returns is a
  {py:class}`qrlab.experiments.Tagged` value. The tag must be one of
  {py:data}`qrlab.experiments.TAGS` (`in_sample`, `out_of_sample`, `descriptive`), or it raises.
  The runner writes the tag of every output into `record.json`. The `backtest` kind tags
  walk-forward results `out_of_sample` and every other strategy `in_sample`. The
  volatility-managed and factor-zoo studies write in-sample and out-of-sample results to
  separate tables.

## What guards it

- `tests/unit/experiments/test_runner.py`: `test_trial_counting` (same config twice counts
  once; a changed parameter counts; moving the output does not), `test_run_writes_outputs_and_record`,
  `test_kind_output_rules` (an unknown tag raises), `test_config_errors` (empty hypothesis).
- `tests/unit/metrics/test_sharpe_inference.py`: `test_dsr_hand_example`,
  `test_psr_and_dsr_from_returns`, `test_psr_and_dsr_errors`.
- `tests/unit/stats/test_multiple_testing.py`: `test_holm_hand_example`,
  `test_benjamini_hochberg_hand_example`, `test_benjamini_yekutieli_hand_example`,
  `test_matches_statsmodels`, `test_single_hypothesis_and_ties`, `test_input_errors`.
- `tests/unit/studies/test_volatility_managed.py`: `test_best_deflated_sharpe`,
  `test_tables_apply_holm_and_bh_within_each_family`;
  `tests/unit/studies/test_one_over_n.py`: `test_tables_and_deflated_sharpe`.
- `tests/unit/experiments/test_study_volatility_managed.py`:
  `test_study_runs_end_to_end_through_the_cli` (a second configuration doubles `dsr_trials`),
  `test_single_variant_has_no_deflated_sharpe`.
- `tests/unit/experiments/test_study_one_over_n.py` and
  `tests/unit/experiments/test_study_factor_zoo.py`: `test_study_runs_end_to_end_through_the_cli`
  (tags, `dsr_trials`, `configurations_tried`).
- `tests/unit/experiments/test_kinds.py`: `test_backtest_strategies` (in- or out-of-sample tag).

## Limits

- **The ledger counts only what goes through the runner.** Exploration in notebooks or
  scripts that call the library directly is not counted. Renaming the experiment, writing to
  a folder with a different parent, or deleting `trials.jsonl` starts the count again.
- **The hash covers the config text, not the data.** Changing the contents of an input file at
  the same path is not a new configuration (the file hashes are in `record.json`, but not in
  the count). Conversely, editing only the hypothesis text counts as a new configuration.
- **The count is used in only two places.** Only the volatility-managed and 1/N studies feed
  `configurations_tried` into a deflated Sharpe ratio. The `backtest` and `optimisation` kinds
  report no deflated Sharpe ratio; the factor-zoo and rebalancing studies record
  `configurations_tried` as a descriptive number only. Holm and BH corrections apply within one
  run, not across runs.
- The deflated Sharpe ratio assumes independent trials. Variants are usually correlated, so
  `variants x configurations` overstates the effective number of trials (conservative), while
  the trials' variance is estimated from the current run's variants only.
- Tags are set by each experiment kind. The runner checks that a tag is valid, not that an
  `out_of_sample` table really is out of sample. Figures and HTML reports are always tagged
  `descriptive`, even when they show in-sample results; the reports label those sections.
- Looking at out-of-sample results and then changing the config turns them, in effect, into
  in-sample results. The ledger records the extra trial but cannot undo that.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
