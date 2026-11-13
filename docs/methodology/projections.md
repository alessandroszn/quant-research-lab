# Projection overconfidence

A projection of future wealth depends on assumed returns, volatility, inflation, costs and
taxes, none of which are known. A single "expected" number hides how wide the outcomes are and
how much they move when an assumption changes. A projection is a set of scenarios from stated
assumptions, not a forecast.

## How it goes wrong

Take 100,000 EUR invested for 20 years, with yearly log returns that are independent and
normal, with mean 5 % and volatility 15 %. A spreadsheet compounding at the mean gives one
number: 100,000 × e^(0.05 × 20) = 271,828 EUR. Under these assumptions that number is the
median. The distribution around it is wide:

| Terminal wealth | EUR |
|---|---:|
| 5th percentile | 90,176 |
| 25th percentile | 172,899 |
| median | 271,828 |
| 75th percentile | 427,362 |
| 95th percentile | 819,399 |
| mean | 340,417 |

There is a 6.8 % chance of ending below the starting 100,000, and a 67.6 % chance of reaching
200,000. Quoting the mean instead of the median overstates the typical outcome by a quarter,
because the right tail pulls it up. These values are exact for the stated model. A Monte Carlo
run with 10,000 paths (seed 42) estimates the probability of reaching 200,000 as
66.95 % ± 0.47 %. The estimate carries its own error, and the result depends on the assumptions.

## How qrlab prevents it

- {py:func}`qrlab.simulation.project` returns wealth per path, nominal and real, never one
  path. {py:func}`qrlab.simulation.summarize` turns it into a fan chart of chosen percentiles,
  terminal percentiles (real, nominal and after the tax of selling everything), the probability
  of reaching a goal, the probability of running out, and sequence-of-returns risk (median
  outcome of the worst and best deciles of early returns).
- Probabilities carry their Monte Carlo standard error, √(p(1 − p)/N), and the mean carries
  s/√N. A summary needs at least 10 paths.
- {py:class}`qrlab.simulation.Plan` has no defaults: initial wealth, currency, weights (which
  must sum to 1 and are never rescaled), periods per year, flows and their timing, rebalancing,
  annual cost, inflation and the {py:class}`qrlab.simulation.TaxModel` are all stated.
- The return engine is a choice: {py:func}`qrlab.simulation.normal_returns`,
  {py:func}`qrlab.simulation.student_t_returns` (fatter tails, same covariance) or
  {py:func}`qrlab.simulation.bootstrap_returns` (blocks of history). Each takes an explicit
  random generator and a cell limit. The same seed gives the same paths.
- {py:func}`qrlab.simulation.sensitivity` re-runs the plan with mean return ±1 point a year,
  volatility ×0.8 and ×1.2, inflation ±1 point and costs ±0.5 point, on common random numbers,
  so differences come from the assumptions and not from simulation noise.
- In the HTML portfolio report ({py:func}`qrlab.reporting.build_portfolio_report`), the
  projection section shows the assumptions table, the terminal percentiles, every probability
  with "±" its standard error, the sensitivity table and a note that projections are scenarios
  from assumptions, "not forecasts or advice". The report ends with "Analytics, not investment
  advice."
- The `projection` experiment kind takes no data files: every return assumption is written in
  the config, and a seed is required. Its outputs are tagged descriptive, and the run record
  stores the whole config.

## What guards it

- `tests/unit/simulation/test_engines.py`: `test_normal_engine_matches_the_lognormal_closed_form`,
  `test_student_t_keeps_the_covariance_and_fattens_the_tails`,
  `test_monte_carlo_error_halves_with_four_times_the_paths`, `test_same_seed_same_paths`,
  `test_sizes_and_generator_are_checked`.
- `tests/unit/simulation/test_outcomes.py`: `test_summary_on_hand_built_paths` (percentiles,
  probabilities and their standard errors by hand), `test_depletion_probability`,
  `test_sequence_risk_shows_with_withdrawals`, `test_sensitivity_with_common_random_numbers`,
  `test_quarterly_dates_and_validation`.
- `tests/unit/simulation/test_plan.py`: `test_plan_validation`,
  `test_projection_on_simulated_paths_is_reproducible`.
- `tests/unit/reporting/test_report_projection.py`: `test_section_with_a_projection` (the
  note, the assumptions and the "±" errors are printed), `test_section_without_projection_says_so`.
- `tests/unit/experiments/test_runner.py`: `test_tables_must_be_tables_and_seed_rules` (a kind
  that needs a seed refuses a config without one).
- `tests/unit/experiments/test_kinds.py`: `test_projection_kind` (same seed, same numbers),
  `test_projection_config_errors`.
- `tests/integration/test_examples.py`: `test_projection_example_runs_deterministically`.

## Limits

- The sensitivity table is optional. The `projection` kind accepts `sensitivity = false`, and
  the report accepts a projection without sensitivity rows.
- The disclaimer is not attached to every output. The `projection` kind writes CSV tables, a
  PNG fan chart and the run record, none of which carries a "not a forecast" note. The
  `portfolio_report` kind never includes a projection, so its projection section always reads
  "No projection was computed for this report." The section with the note is reached only by
  calling {py:func}`qrlab.reporting.build_portfolio_report` from Python. The desktop app shows a
  general "not investment advice" notice on its Home and Settings screens.
- The `projection` kind offers only the normal and Student-t engines. The block bootstrap is
  available from the library only.
- The normal and Student-t engines draw independent returns with fixed parameters: no
  volatility clustering, mean reversion or regime changes. The parameters are treated as known;
  estimation error appears only through the one-at-a-time sensitivity rows. Inflation is a
  constant.
- Sensitivity changes one assumption at a time. Joint changes and changes of correlation are
  not shown.
- Standard errors are given for probabilities and the mean, not for percentiles.
- The tax model uses one blended rate and does not carry losses forward; costs are a flat
  yearly rate. Both are illustrations, not tax advice.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
