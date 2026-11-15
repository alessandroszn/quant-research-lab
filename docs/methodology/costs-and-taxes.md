# Unrealistic costs and taxes

A strategy that trades often can look good before costs and poor after them. Capital-gains tax
on rebalancing sales has the same effect for a taxable investor. If costs and taxes are left
out, or set silently to zero, the reported return is one nobody could have earned.

## How it goes wrong

A 10,000 EUR portfolio holds two assets at 50/50. Asset A gains 20 % in one month and B is flat,
so the holdings are 6,000 and 5,000. Rebalancing back to 50/50 sells 500 of A and buys 500 of B.

- Gross (no costs, no tax): 11,000.00 EUR, a return of 10.00 %.
- Costs, at 0.10 % of the amount traded plus 1 EUR per asset traded:
  0.001 × 1,000 + 2 × 1 = 3.00 EUR.
- Tax, at 26 % on the realised gain: selling 500 of 6,000 sells 1/12 of A, whose unrealised
  gain is 1,000, so the realised gain is 83.33 and the tax is 21.67 EUR.
- Net: 11,000 − 3.00 − 21.67 = 10,975.33 EUR, a return of 9.75 %.

The same numbers from the backtest engine:

```python
import pandas as pd
from qrlab.backtest import run_backtest
from qrlab.core import Money
from qrlab.optimization import CalendarPolicy, CostModel
from qrlab.simulation import TaxModel

returns = pd.DataFrame({"A": [0.20], "B": [0.0]}, index=pd.DatetimeIndex(["2026-01-31"]))
result = run_backtest(
    returns,
    lambda history: None,
    decide_every=1,
    execution_lag=1,
    policy=CalendarPolicy(1),
    costs=CostModel(0.001, 1.0),
    taxes=TaxModel(0.26, 0.0),
    initial_weights=pd.Series({"A": 0.5, "B": 0.5}),
    initial_value=Money.of("10000", "EUR"),
    long_only=True,
)
# gross 11,000.00; net 10,975.33; costs_paid 3.00; taxes_paid 21.67
```

One rebalance costs 0.25 % here. A rule that rebalances every month pays this again and again,
and the gap between gross and net compounds.

## How qrlab prevents it

- {py:func}`qrlab.backtest.run_backtest` and {py:func}`qrlab.backtest.run_backtest_targets`
  take `costs` and `taxes` as keyword arguments with no default. A {py:class}`qrlab.optimization.CostModel`
  needs both `proportional` (rate on the amount traded) and `fixed` (fee per asset traded);
  negative, infinite or NaN values raise.
- Every backtest keeps two ledgers. The gross ledger has neither costs nor tax. The net ledger
  pays them after each trade. {py:class}`qrlab.backtest.BacktestResult` holds both value paths,
  every execution with its cost and tax, and the cost and tax settings used.
- {py:func}`qrlab.backtest.summarize_backtest` returns gross and net statistics side by side,
  with turnover, costs paid and taxes paid.
- The `backtest` experiment kind requires a `costs` table with both keys and a
  `capital_gains_tax` key. It writes gross and net values to the same table and reports
  `gross_*` and `net_*` scalars together.
- {py:class}`qrlab.simulation.Plan` requires `annual_cost` and a {py:class}`qrlab.simulation.TaxModel`.
  Projections pay capital-gains tax on withdrawals and on rebalancing sales, and report terminal
  wealth after the tax of selling everything at the end.
- The studies take costs from their configs, never from code. The 1/N and volatility-managed
  configs run a grid that includes zero (0, 10 and 50 basis points; 0, 10 and 25), so the
  zero-cost result is reported next to the costed ones. The rebalancing study runs a low and a
  high cost scenario.
- For a real portfolio, transactions carry their own fees and taxes as money
  ({py:class}`qrlab.portfolio.Transaction`), and the health checks report the weighted TER and
  the trading-cost drag. An unknown TER is excluded and reported, never counted as zero.
- **The Italian tax position of a real account** ({py:func}`qrlab.tax.italian_tax_position`,
  phase 8.6a).
  - It recomputes the tax of each sale under the Italian rules, with their sources and the
    date they were checked: capital income versus other income, the losses balance with its
    four-year expiry, and the 48.08 % share of government bonds.
  - It then compares the result with the tax the broker withheld. A difference is shown,
    never absorbed. Its report section is titled "analytics, not tax advice".
- **Tax regimes by country** ({py:class}`qrlab.tax.TaxRegime`, phase 9.1).
  - Every country reads its own keys of `[parameters.tax]`, after `country`, and returns a
    {py:class}`qrlab.tax.TaxReport`: sentences, typed tables, sources in each report
    language, and the date its rules were checked.
  - The CSV tables and the report section are written from that description alone. A new
    country adds rules, not presentation code.
  - Italy is the first country (`country = "it"`).
- **Switzerland, private investor** ({py:mod}`qrlab.tax.switzerland`, phase 9.2,
  `country = "ch"`).
  - **Gains are tax-free,** and the five ESTV Circular 36 criteria are checked every year.
    The holding period is taken first in, first out, the most cautious reading under average
    cost.
  - **The report never says "professional trader".** It says whether the safe haven is met,
    and that the tax office judges the whole case.
  - **Estimates use your rates.** Income and wealth taxes are estimated at the rates you
    state, and the report labels them as estimates.
  - **Accumulating funds:** their yearly income comes from the ESTV price-list values you
    give.
- **A yearly income tax in projections** (`TaxModel.income_tax_rate × taxable_yield`, phase
  9.2) is paid each year like the wealth tax. It is exact for accumulating funds and an
  approximation for distributing ones, because projections use total returns.
- **Italian losses in projections and backtests** ({py:class}`qrlab.simulation.LossRules`,
  phase 8.6b), an optional field of {py:class}`qrlab.simulation.TaxModel`.
  - Gains on the assets named in `fund_assets` are capital income: taxed in full, never
    reduced by losses.
  - Every realised loss, on any asset, joins a balance by year. Gains on the other assets
    are reduced first by the losses of the same sale, then by the balance, oldest year
    first, until `carry_years` after the year a loss was realised (4 in Italy).
  - Projections keep one balance per path, with years from `periods_per_year`. Backtests
    keep one, by calendar year of the execution date. Withdrawals still pay the stated net
    amount: the gross sale is solved in closed form with the offset.
  - For funds only, the rules change no number, bit for bit; the tests check it.

## What guards it

- `tests/unit/optimization/test_rebalancing.py`: `test_trade_cost_hand_example`,
  `test_validation` (negative and NaN costs raise).
- `tests/unit/backtest/test_engine.py`: `test_costs_hit_the_net_ledger_only`,
  `test_capital_gains_tax_on_rebalancing_sales`, `test_final_basis_by_hand`.
- `tests/unit/backtest/test_summary.py`: `test_summary_of_the_toy`.
- `tests/unit/experiments/test_kinds.py`: `test_backtest_config_errors` (a missing cost key
  raises), `test_backtest_kind_matches_the_library`.
- `tests/unit/simulation/test_plan.py`: `test_costs_hand_example`,
  `test_withdrawal_tax_hand_example`, `test_wealth_tax_is_charged_pro_rata`,
  `test_rebalancing_keeps_basis_for_the_liquidation_tax`.
- `tests/unit/simulation/test_losses.py`: `test_the_notes_case_by_hand` (156 on a fund gain,
  a share gain covered by the balance, expiry in year 6),
  `test_rebalancing_carries_a_share_loss_by_hand`,
  `test_a_withdrawal_beyond_the_carried_losses_by_hand`,
  `test_backtest_carries_the_share_loss_by_hand`, and the two funds-only byte-identity tests.
- `tests/unit/tax/test_switzerland.py`:
  - `test_the_years_by_hand`: income 2,200, tax 660, wealth 245,780, tax 737.34;
  - `test_the_safe_haven_check_by_hand`;
  - `test_shortest_holding_is_first_in_first_out`;
  - `test_splits_and_transfers_out_in_the_holding_period`.
- `tests/unit/simulation/test_income_tax.py`: `test_two_years_by_hand` (1,000, 994,
  988.036).
- `tests/unit/simulation/test_outcomes.py`: `test_after_tax_and_nominal_terminal_values`,
  `test_sensitivity_with_common_random_numbers` (costs ±0.5 point rows).
- `tests/unit/checks/test_checks_concentration_costs_data.py`: `test_weighted_ter_hand_example`,
  `test_unknown_ter_is_excluded_not_zero`, `test_trading_drag_hand_example`.
- `tests/integration/test_examples.py`: `test_backtest_example_shows_gross_and_net`.

## Limits

- "Required" means "no default", not "realistic". `CostModel(0.0, 0.0)` and `taxes=None` are
  accepted, and the `backtest` kind turns `capital_gains_tax = 0` into no tax. The values are
  the user's assumptions.
- The cost model is linear: a proportional rate plus a fixed fee per asset traded. There is no
  bid-ask spread that changes over time, no market impact, no minimum commission, no currency
  conversion fee and no borrowing cost for short positions.
- Costs and tax are paid pro rata from all holdings, not from a cash account.
- In backtests and projections, tax is one flat rate on realised gains, with an average cost
  basis per asset. Tax on dividends and coupons is not modelled.
  - **Without `LossRules`,** a loss on one asset does not offset a gain on another, and
    losses are not carried forward, so tax is slightly overstated when the portfolio holds
    shares, bonds or ETCs.
  - **With `LossRules`,** the 48.08 % share of government bonds is not applied: it is an
    analytics input of the tax position, not a projection assumption.
  - **`LossRules` is a library option only.** The `backtest`, `projection` and report
    configs do not set it yet; it is listed in `docs/IDEAS.md`.
- **Limits of the Italian tax analytics.**
  - Dividends and interest are listed with their withheld tax, not recomputed.
  - Stamp duty and IVAFE are not computed.
  - Foreign currency held as *redditi diversi* is not treated.
  - There is one account per report.
  - The regime and the government-bond shares are declared by the user, not read from the
    broker.
- The backtest ignores the wealth-tax rate of the tax model. Its net value does not deduct the
  tax on gains still unrealised at the end; `final_basis` lets the caller compute it, as the
  rebalancing study does.
- In projections, `annual_cost` is a flat yearly drag. Rebalancing pays tax but no trading cost,
  and contributions and withdrawals pay no trading cost. A projection does not show a pre-cost
  path next to the net one: costs appear as an assumption and in the sensitivity table.
- The factor-zoo study reports gross returns of paper portfolios with no trading costs; its
  report states this. The volatility-managed study does not charge the initial position.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
