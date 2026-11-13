# Wrong performance measure (TWR vs MWR)

A portfolio with deposits and withdrawals has two different returns. The time-weighted return
(TWR) measures the investments and neutralises the timing of external flows. The
money-weighted return (MWR, an internal rate of return) measures the investor's experience,
including when money went in and out. Reporting one under the name of the other, or comparing
them, leads to wrong conclusions about skill or about the investor's outcome.

## How it goes wrong

An investor deposits EUR 10,000 on 1 January 2025. By 31 December 2025 the portfolio is worth
12,000 (+20 %). After that close the investor deposits another 50,000. During 2026 the
portfolio falls 10 %, to 55,800 on 31 December 2026.

```python
twr = (1 + 0.20) * (1 - 0.10) - 1  # 0.0800 over two years (about 3.93 % a year)
# MWR: the rate r that solves
#   -10,000 - 50,000 / (1 + r) ** (364 / 365) + 55,800 / (1 + r) ** (729 / 365) = 0
mwr = -0.0605  # -6.05 % a year (ACT/365)
```

The investments gained 8.0 %; the investor lost EUR 4,200 of the 60,000 deposited, because
most of the money arrived just before the fall. Both numbers are correct. Each answers a
different question. Showing "+8.0 %" as "your return", or ranking a manager on the -6.05 %,
would be wrong.

The flow-timing convention also matters. With valuation dates only at year ends, treating the
50,000 as invested from the start of the period that ends on 31 December 2025
(`START_OF_DAY`) gives a TWR of -7.0 % instead of +8.0 %.

## How qrlab prevents it

- **Separate functions and result types.** {py:func}`qrlab.portfolio.time_weighted_returns`
  returns a {py:class}`qrlab.portfolio.TwrResult` whose series is named `"TWR"`.
  {py:func}`qrlab.portfolio.xirr` and {py:func}`qrlab.portfolio.money_weighted_return` return a
  {py:class}`qrlab.portfolio.XirrResult` with the fixed label `"MWR (XIRR, ACT/365)"`.
- **Flow timing is a required argument.** `flow_timing` must be a
  {py:class}`qrlab.portfolio.FlowTiming` (`START_OF_DAY` or `END_OF_DAY`); there is no default.
  The result records the convention used.
- **Flows must match valuation dates.** A flow on a date that is not a valuation date raises,
  so the TWR is never chain-linked across an unvalued flow. Periods with zero starting capital
  are skipped and listed in `TwrResult.skipped`.
- **External versus internal flows are fixed.** Only deposits, withdrawals and transfers of
  securities (at market value) are external
  ({py:func}`qrlab.portfolio.external_flows_by_date`). Dividends, interest, fees and taxes are
  part of the return.
- **Non-unique MWR is reported.** `xirr` scans a grid of rates and keeps every root.
  `XirrResult.candidates` lists them, `sign_changes` counts the sign changes of the flows, and
  `unique_root_guaranteed` is true only with one sign change. Without both a negative and a
  positive flow, `xirr` raises {py:class}`qrlab.metrics.UndefinedMetricError`.
- **The report labels both and says they differ.** The summary of
  {py:func}`qrlab.reporting.build_portfolio_report` shows "Time-weighted return (TWR)" and
  "Money-weighted return (MWR, XIRR, a year)" on separate rows, with one sentence defining each
  and the note "TWR and MWR measure different things and are not comparable." The TWR is
  annualised only for periods of at least 365 days. Several MWR roots produce a warning.

## What guards it

- `tests/unit/portfolio/test_performance.py`: `test_twr_hand_example_start_of_day`,
  `test_twr_end_of_day_skips_zero_starting_capital`, `test_twr_flows_must_fall_on_valuation_dates`,
  `test_twr_needs_flow_timing_enum`, `test_twr_equals_simple_return_without_flows`,
  `test_xirr_closed_form`, `test_mwr_hand_example` (checks the label),
  `test_xirr_matches_independent_bisection`, `test_xirr_undefined_without_both_signs`,
  `test_xirr_reports_several_sign_changes`, `test_mwr_end_must_be_a_valuation_date`.
- `tests/unit/portfolio/test_ledger.py`: `test_transaction_flow_classification`,
  `test_transfers_in_and_out_are_external_flows_at_market_value`.
- `tests/unit/reporting/test_portfolio_report.py`:
  `test_toy_report_shows_the_hand_values_in_italian` (TWR 3.17 %, MWR 15.73 % and the
  "not comparable" sentence), `test_short_period_is_not_annualised_and_volatility_omitted`,
  `test_long_period_is_annualised`, `test_mwr_with_several_roots_warns`,
  `test_skipped_dates_after_the_start_warn`.

## Limits

- **The MWR is always an annual rate, even for short periods.** The TWR is not annualised under
  one year, but the MWR is. In the toy report a TWR of 3.17 % over three months stands next to
  an MWR of 15.73 % a year. The labels state this, but the two figures sit in the same "Value"
  column of the summary table, on separate rows. The register's "never mixed" means separate
  labelled rows and a printed warning, not separate tables.
- When the MWR has several roots, `rate` is the root closest to zero. That choice is a
  convention, not a property of the flows.
- The TWR is only as accurate as the valuation dates. With sparse dates, the choice of
  `FlowTiming` can change the result a lot, as in the example above.
- The MWR uses calendar days (ACT/365). When `xirr` cannot define it (for example, no money
  paid in, or no root in its search range) the report shows "n/a" instead of a number.
- The `portfolio_report` experiment kind records only the TWR (`twr_total`) as a scalar in
  `record.json`. The MWR appears only in the HTML report.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
