# Stale look-through data

Look-through combines a portfolio's weights in funds with the holdings each fund reports.
Funds publish holdings with a delay, and their composition changes after the reporting date.
Old holdings give exposures that look exact but describe a past portfolio. Holdings dated after
the analysis date are worse: they use information that was not yet available.

## How it goes wrong

A portfolio has 60 % in an equity fund. The report is as of 30 September 2026. The only
holdings file on hand is dated 31 March 2026, 183 days earlier, and shows 25 % in technology.
Since then the fund's index has moved to 30 % technology.

```python
fund_weight = 0.60
reported_tech = 0.25  # holdings as of 2026-03-31
current_tech = 0.30  # what the fund holds on 2026-09-30
lookthrough = fund_weight * reported_tech  # 0.150: shown as 15.0 % technology
actual = fund_weight * current_tech  # 0.180: actual exposure 18.0 %
```

The exposure is understated by 3 percentage points, and nothing in the number itself says it
is six months old. The opposite error is to analyse 30 September with a holdings file dated
31 December: the result looks current but uses data from the future.

## How qrlab prevents it

- **Holdings carry their date.** {py:class}`qrlab.instruments.HoldingsSnapshot` requires
  `as_of`, the date the fund reported the holdings, and a provenance record.
  {py:func}`qrlab.instruments.parse_holdings_csv` takes `as_of` as a required argument.
- **Future holdings raise.** {py:func}`qrlab.lookthrough.look_through` raises when a snapshot is
  dated after the analysis date (look-ahead). It records the date of every snapshot used in
  {py:class}`qrlab.lookthrough.LookThrough` (`snapshot_dates`).
- **Stale holdings are flagged.** {py:func}`qrlab.instruments.holdings_issues` reports an
  {py:class}`qrlab.instruments.IssueKind` `STALE` issue for a snapshot older than
  `max_age_days`, and `FUTURE` for one dated after the check date. The limit has no default.
- **A health check counts them.** The `data_quality.stale_holdings` check counts snapshots
  older than its `max_age_days` on the check date and names each fund with its date. A
  {py:class}`qrlab.checks.CheckConfig` must list every registered check with its parameters,
  so the limit cannot be forgotten; a check can only be switched off explicitly, and then it is
  listed as disabled. The example config uses 100 days.
- **Master data has the same rule.** {py:class}`qrlab.instruments.Instrument` has an `as_of`
  date; {py:func}`qrlab.instruments.master_data_issues` and the `data_quality.stale_master`
  check flag records older than an explicit limit.
- **The report shows the age.** The look-through section of the portfolio report has a
  "Holdings dates" table with each fund's holdings date and age in days.
- **Dates must agree.** {py:class}`qrlab.lookthrough.LookThroughInputs` raises unless its
  snapshots are exactly the ones the exposures were built from. The health checks and the
  report raise if the look-through is dated differently from them.
- **The experiment kind declares every date.** In the `portfolio_report` kind, each holdings
  file needs `[parameters.holdings.<ISIN>] as_of`; nothing is read from the file name or
  guessed. Holdings dated after the last valuation date make the run fail, and so does a
  holdings file for a fund the portfolio does not hold on that date.
- **Missing holdings are visible.** A fund without a snapshot goes to a "not looked through"
  bucket instead of being dropped or redistributed.

## What guards it

- `tests/unit/instruments/test_holdings.py`: `test_stale_and_future_snapshots`.
- `tests/unit/instruments/test_master.py`: `test_staleness_uses_the_callers_threshold`,
  `test_future_as_of_is_reported`.
- `tests/unit/lookthrough/test_exposures_overlap.py`: `test_snapshot_checks` (future snapshot
  raises; only funds held are recorded).
- `tests/unit/checks/test_checks_holdings.py`: `test_stale_holdings_boundary` (30 days old is
  stale with a 29-day limit, not with a 30-day limit), `test_lookthrough_inputs_are_validated`.
- `tests/unit/checks/test_checks_concentration_costs_data.py`: `test_missing_and_stale_master_data`.
- `tests/unit/checks/test_engine.py`: `test_example_config_covers_every_check`,
  `test_config_validation`, `test_disabled_checks_do_not_run`.
- `tests/unit/experiments/test_portfolio_report_lookthrough.py`:
  `test_exposures_as_reported_by_hand` (24.0 / 15.0 / 12.0 / 8.4 % and 0.6 % unexplained),
  `test_exposures_normalised_by_hand`, `test_the_kind_matches_the_library`,
  `test_run_errors` (a fund not held; holdings dated after the report).
- `tests/unit/reporting/test_report_lookthrough.py`:
  `test_section_with_holdings_overlap_and_tracking` (holdings date and age in the table),
  `test_lookthrough_for_another_date_raises`.

## Limits

- **Staleness is flagged, not refused.** `look_through` accepts a snapshot of any age that is
  not in the future. Only the health check and the report table point out its age. Whether a
  warning appears depends on the threshold the user sets.
- **Only with holdings files.** The `portfolio_report` experiment kind runs look-through only
  when holdings files are given (phase 7.4b). Without them, the report states that
  look-through was not done, and `data_quality.stale_holdings` is "not applicable".
- `as_of` is the holdings date, not the publication date. A snapshot dated 30 September but
  published in late October passes the look-ahead check for a 15 October analysis. For
  historical analyses, the user must pick snapshots that were available at the time.
- Holdings are used as reported. qrlab does not roll them forward with security returns or
  estimate changes since `as_of`.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
