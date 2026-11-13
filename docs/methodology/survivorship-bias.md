# Survivorship bias

Survivorship bias means the sample contains only the instruments that still exist today. Funds
that closed and stocks that were delisted, often after losses, are missing. Averages,
backtests and fund comparisons built on survivors are too optimistic.

## How it goes wrong

Five funds start a year. Two lose money and are closed before the next data download, so a
list of "funds available today" has only three.

| Fund | Return over the year | Still listed today |
|---|---:|---|
| A | +8 % | yes |
| B | +6 % | yes |
| C | +4 % | yes |
| D | −15 % | no (closed) |
| E | −25 % | no (merged) |

The average of the survivors is (8 + 6 + 4) / 3 = **+6.0 %**. The average of all five funds
that an investor could have bought at the start is (8 + 6 + 4 − 15 − 25) / 5 = **−4.4 %**.
The sign of the result changes.

The same happens in a backtest when the asset list is chosen today, or when assets with
missing data at the end are dropped to get a complete panel.

## How qrlab prevents it

qrlab has no survivorship correction. What it does is refuse to hide missing history:

- **Missing returns are never filled.** {py:func}`qrlab.backtest.run_backtest` validates the
  returns with `NanPolicy.RAISE`: any NaN raises {py:class}`qrlab.core.ValidationError`. A
  delisted asset is not silently given a return of 0 or turned into cash.
- **No forward fill in conventions.** {py:func}`qrlab.core.prices_to_returns` makes both
  returns next to a missing price NaN. {py:func}`qrlab.core.aggregate_returns` returns NaN for
  a bucket that contains a NaN; a missing return is never treated as zero.
- **Stress tests report missing history.** In {py:func}`qrlab.scenarios.run_scenario` a
  position whose own series does not cover the window (for example an ETF launched after the
  crisis replayed) uses factor betas, labelled `proxy`. Without betas it is `not covered`: its
  weight is reported and excluded, never assumed to lose 0.
- **Studies use provider-built portfolios.** The studies work on portfolio and factor returns
  from Ken French and Open Asset Pricing, not on a list of today's constituents. The
  composition of those portfolios is the provider's.
- **Closure risk of held funds is shown.** The ETF health checks report each fund's age since
  inception and its size; the fund-size check is described as a warning that small funds are
  more likely to be closed or merged. This is a forward-looking warning about the funds held,
  not a correction of past data.

## What guards it

There is no test of survivorship handling as such, because there is none to test. The tests
below check the related rules on missing data:

- `tests/unit/backtest/test_engine.py`: `test_input_validation` (a NaN return raises).
- `tests/unit/core/test_series.py`: `test_nan_policy_raise`, `test_all_nan_under_each_policy`.
- `tests/unit/core/test_returns.py`:
  `test_nan_price_propagates_to_both_adjacent_returns_and_is_not_filled`,
  `test_aggregate_nan_inside_bucket_gives_nan_not_zero`,
  `test_aggregate_empty_bucket_in_gap_is_nan`.
- `tests/unit/scenarios/test_scenarios.py`: `test_uncovered_positions_are_excluded_not_zeroed`,
  `test_proxy_compounds_period_by_period`.
- `tests/unit/checks/test_checks_library.py`: `test_fund_size_in_base_currency_and_fund_age`.

## Limits

- **The risk register promises more than the code does.** It lists "point-in-time universes"
  and "closed/delisted instruments retained". Neither exists in qrlab 1.0:
  - there is no universe object with membership by date;
  - {py:class}`qrlab.instruments.Instrument` has an `inception` date but no closure,
    delisting or end date, and no status;
  - there is no handling of delisting returns.
- **The backtest needs a fixed, complete panel.** Every asset must have a return in every
  period, so assets cannot enter or leave during a run. A user who drops assets with
  incomplete history builds a survivor universe. Assets entering and leaving the universe are
  listed in `docs/IDEAS.md`.
- **User data are taken as given.** A price CSV loaded with {py:func}`qrlab.data.parse_price_csv`
  contains whatever instruments the user chose. qrlab cannot know which instruments existed
  but are missing.
- **Provider data are not verified.** How Ken French and Open Asset Pricing treat delisted
  stocks is their construction. qrlab does not check it.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
