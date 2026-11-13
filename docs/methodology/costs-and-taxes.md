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
- Tax is one flat rate on realised gains, with an average cost basis per asset. A loss on one
  asset does not offset a gain on another, and losses are not carried forward, so tax is
  slightly overstated. Tax on dividends and coupons is not modelled.
- The backtest ignores the wealth-tax rate of the tax model. Its net value does not deduct the
  tax on gains still unrealised at the end; `final_basis` lets the caller compute it, as the
  rebalancing study does.
- In projections, `annual_cost` is a flat yearly drag. Rebalancing pays tax but no trading cost,
  and contributions and withdrawals pay no trading cost. A projection does not show a pre-cost
  path next to the net one: costs appear as an assumption and in the sensitivity table.
- The factor-zoo study reports gross returns of paper portfolios with no trading costs; its
  report states this. The volatility-managed study does not charge the initial position.

Related: [risk register](../ARCHITECTURE.md#quantitative-risk-register)
